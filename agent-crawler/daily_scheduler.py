#!/usr/bin/env python3
"""
独立的每日论文调度器服务

这是一个独立运行的后台服务，负责：
1. 每日定时自动抓取最新AI论文
2. 智能处理重要引用
3. 将数据存储到Neo4j和Qdrant
4. 生成处理报告和统计

运行方式：
    python daily_scheduler.py --daemon  # 后台运行
    python daily_scheduler.py --run-now # 立即执行一次
    python daily_scheduler.py --status  # 查看状态
"""

import os
import sys
import signal
import asyncio
import argparse
from datetime import date, datetime
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sources.arxiv_fetcher import fetch_latest_ai_papers
from pipelines.process_paper import process_and_ingest_paper
from graph.neo4j_manager import Neo4jManager
from qdrant_client import QdrantClient

load_dotenv()


class DailyPaperScheduler:
    """每日论文抓取调度器 - 独立服务"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
        self.should_stop = False
        
        # 配置参数
        self.daily_paper_count = int(os.getenv("DAILY_PAPER_COUNT", "8"))
        self.smart_mode = os.getenv("DAILY_SMART_MODE", "true").lower() == "true"
        self.schedule_time = os.getenv("DAILY_SCHEDULE_TIME", "10:00")
        # 并发处理配置（暂时禁用以避免API rate limit）
        self.enable_concurrent = os.getenv("ENABLE_CONCURRENT_PROCESSING", "false").lower() == "true"
        self.max_workers = int(os.getenv("MAX_CONCURRENT_WORKERS", "3"))
        
        # 数据库连接参数
        self.neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD", "neo4j_password")
        self.qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        
        logger.info("📅 每日论文调度器启动")
        logger.info(f"⚙️  配置: {self.daily_paper_count}篇论文, 智能模式{'开启' if self.smart_mode else '关闭'}, 时间{self.schedule_time}")
        logger.info(f"🔧 并发处理: {'启用({} workers)'.format(self.max_workers) if self.enable_concurrent else '禁用（顺序处理）'}")
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """处理停止信号"""
        logger.info(f"📨 收到停止信号 {signum}")
        self.should_stop = True
        if self.scheduler.running:
            self.scheduler.shutdown()
    
    async def daily_paper_ingestion_task(self):
        """每日论文抓取的核心任务"""
        task_start_time = datetime.now()
        today = str(date.today())
        
        logger.info("=" * 60)
        logger.info("🚀 开始每日论文自动抓取任务")
        logger.info(f"📅 日期: {today}")
        logger.info(f"📊 目标论文数: {self.daily_paper_count}")
        logger.info(f"🧠 智能模式: {'启用' if self.smart_mode else '禁用'}")
        logger.info("=" * 60)
        
        try:
            # 1. 获取今日最新论文
            logger.info("🔍 获取今日最新AI论文...")
            papers = fetch_latest_ai_papers(
                max_results=self.daily_paper_count, 
                fetch_date=today
            )
            
            if not papers:
                logger.warning("⚠️ 未获取到今日论文，任务结束")
                return
            
            logger.info(f"✅ 成功获取 {len(papers)} 篇论文")
            for i, paper in enumerate(papers, 1):
                logger.info(f"  {i}. {paper.title[:60]}{'...' if len(paper.title) > 60 else ''}")
                logger.info(f"     ID: {paper.arxiv_id} | 作者: {paper.authors[0]} 等")
            
            # 2. 初始化数据库连接
            logger.info("🔌 初始化数据库连接...")
            qdrant = QdrantClient(url=self.qdrant_url)
            graph = Neo4jManager(self.neo4j_uri, self.neo4j_user, self.neo4j_password)
            
            try:
                # 3. 批量处理论文
                if self.enable_concurrent:
                    logger.info(f"🔧 启用并发处理模式 ({self.max_workers} workers)")
                    success_count, error_count = await self._process_papers_concurrent(papers, qdrant, graph, today)
                else:
                    logger.info("🔧 使用顺序处理模式")
                    success_count, error_count = await self._process_papers_sequential(papers, qdrant, graph, today)
                
                # 4. 任务统计报告
                task_end_time = datetime.now()
                processing_time = (task_end_time - task_start_time).total_seconds()
                
                logger.info("\n" + "=" * 60)
                logger.info("📊 每日抓取任务完成统计:")
                logger.info(f"   ✅ 成功处理: {success_count} 篇")
                logger.info(f"   ❌ 处理失败: {error_count} 篇")
                logger.info(f"   📈 成功率: {success_count/len(papers)*100:.1f}%")
                logger.info(f"   ⏱️  总耗时: {processing_time:.1f} 秒")
                
                # 5. 生成知识图谱统计
                await self._generate_daily_stats(graph, today)
                
                logger.info("=" * 60)
                logger.info("🎉 每日论文抓取任务顺利完成！")
                
            finally:
                graph.close()
                
        except Exception as e:
            logger.error(f"❌ 每日论文抓取任务异常: {e}")
            raise
    
    async def _generate_daily_stats(self, graph_manager: Neo4jManager, target_date: str):
        """生成每日知识图谱统计报告"""
        try:
            with graph_manager.driver.session() as session:
                # 今日新增论文统计
                query_today = """
                MATCH (p:Paper) 
                WHERE p.fetch_date = $date
                RETURN count(p) as total_papers,
                       count(case when p.title IS NOT NULL then 1 end) as complete_papers,
                       collect(DISTINCT p.domain)[0..5] as sample_domains
                """
                result = session.run(query_today, date=target_date)
                record = result.single()
                
                if record:
                    total = record["total_papers"]
                    complete = record["complete_papers"]
                    domains = record["sample_domains"]
                    
                    logger.info("📈 今日知识图谱增长:")
                    logger.info(f"   📚 新增论文节点: {total}")
                    logger.info(f"   ✅ 完整论文数据: {complete}")
                    logger.info(f"   🏷️  涉及研究领域: {', '.join(filter(None, domains))}")
                
                # 今日新增引用关系统计
                query_citations = """
                MATCH (p:Paper {fetch_date: $date})-[:CITES]->(cited:Paper)
                RETURN count(cited) as total_citations,
                       count(case when cited.title IS NOT NULL then 1 end) as complete_citations
                """
                result = session.run(query_citations, date=target_date)
                record = result.single()
                
                if record:
                    total_cites = record["total_citations"]
                    complete_cites = record["complete_citations"]
                    
                    logger.info("🔗 今日引用关系扩展:")
                    logger.info(f"   🔍 发现引用关系: {total_cites}")
                    logger.info(f"   ✅ 完整引用数据: {complete_cites}")
                    if total_cites > 0:
                        completion_rate = complete_cites/total_cites*100
                        logger.info(f"   📊 引用完整率: {completion_rate:.1f}%")
                        
                        # 如果智能模式启用，显示AI的贡献
                        if self.smart_mode and completion_rate > 0:
                            logger.info("🧠 AI智能扩展效果显著！")
                
        except Exception as e:
            logger.error(f"❌ 统计报告生成失败: {e}")
    
    async def _process_papers_sequential(self, papers, qdrant, graph, today):
        """顺序处理论文（默认模式，避免API rate limit）"""
        success_count = 0
        error_count = 0
        
        for i, paper in enumerate(papers, 1):
            logger.info(f"\n📄 处理论文 {i}/{len(papers)}: {paper.title[:50]}...")
            
            try:
                # 使用线程池调用同步函数避免阻塞事件循环
                await asyncio.to_thread(
                    process_and_ingest_paper,
                    paper_meta=paper,
                    qdrant_client=qdrant,
                    graph_manager=graph,
                    current_depth=0,
                    fetch_date=today
                )
                
                success_count += 1
                logger.info(f"✅ 论文处理成功: {paper.arxiv_id}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"❌ 论文处理失败: {paper.arxiv_id} - {e}")
                continue
        
        return success_count, error_count
    
    async def _process_papers_concurrent(self, papers, qdrant, graph, today):
        """并发处理论文（可选模式，需谨慎使用API限制）"""
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        success_count = 0
        error_count = 0
        processing_lock = threading.Lock()
        processed_papers = set()
        
        def process_single_paper(paper, worker_id):
            """处理单篇论文的内部函数"""
            try:
                with processing_lock:
                    if paper.arxiv_id in processed_papers:
                        return paper.arxiv_id, False, "已在处理中，跳过"
                    processed_papers.add(paper.arxiv_id)
                
                logger.info(f"[Worker-{worker_id}] 开始处理: {paper.arxiv_id}")
                
                # 每个线程独立的数据库连接
                thread_qdrant = QdrantClient(url=self.qdrant_url)
                thread_graph = Neo4jManager(self.neo4j_uri, self.neo4j_user, self.neo4j_password)
                
                try:
                    process_and_ingest_paper(
                        paper_meta=paper,
                        qdrant_client=thread_qdrant,
                        graph_manager=thread_graph,
                        current_depth=0,
                        fetch_date=today
                    )
                    return paper.arxiv_id, True, "处理成功"
                finally:
                    thread_graph.close()
                    
            except Exception as e:
                return paper.arxiv_id, False, f"处理失败: {str(e)}"
        
        # 使用线程池执行器
        logger.info(f"🔧 启动 {self.max_workers} 个并发线程...")
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_paper = {
                executor.submit(process_single_paper, paper, i+1): paper 
                for i, paper in enumerate(papers)
            }
            
            # 等待任务完成并收集结果
            for future in as_completed(future_to_paper):
                paper = future_to_paper[future]
                try:
                    paper_id, success, message = future.result()
                    if success:
                        success_count += 1
                        logger.info(f"✅ {paper_id}: {message}")
                    else:
                        error_count += 1
                        logger.error(f"❌ {paper_id}: {message}")
                except Exception as e:
                    error_count += 1
                    logger.error(f"❌ {paper.arxiv_id}: 线程异常: {e}")
        
        return success_count, error_count
    
    def start_scheduler(self):
        """启动定时调度器"""
        # 解析时间配置
        hour, minute = map(int, self.schedule_time.split(':'))
        
        # 添加每日任务
        self.scheduler.add_job(
            self.daily_paper_ingestion_task,
            trigger=CronTrigger(hour=hour, minute=minute, timezone='Asia/Shanghai'),
            id='daily_paper_ingestion',
            name='每日AI论文自动抓取',
            max_instances=1,  # 防止重复执行
            replace_existing=True
        )
        
        # 启动调度器
        self.scheduler.start()
        self.is_running = True
        
        next_run = self.scheduler.get_job('daily_paper_ingestion').next_run_time
        logger.info(f"✅ 定时调度器已启动")
        logger.info(f"📅 每日执行时间: {self.schedule_time} (北京时间)")
        logger.info(f"🔄 下次执行时间: {next_run}")
    
    async def run_daemon(self):
        """以守护进程模式运行"""
        logger.info("🔄 启动守护进程模式...")
        
        # 启动调度器
        self.start_scheduler()
        
        try:
            # 保持运行直到收到停止信号
            while not self.should_stop:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("📨 收到键盘中断信号")
        finally:
            if self.scheduler.running:
                logger.info("🛑 正在停止调度器...")
                self.scheduler.shutdown()
            logger.info("👋 调度器已安全停止")
    
    async def run_once(self):
        """立即执行一次抓取任务"""
        logger.info("🔧 手动执行每日论文抓取任务...")
        try:
            await self.daily_paper_ingestion_task()
            return True
        except Exception as e:
            logger.error(f"❌ 手动任务执行失败: {e}")
            return False


def setup_logging(log_file: str = None):
    """设置日志系统"""
    logger.remove()
    
    # 控制台输出
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    # 文件输出
    if log_file:
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            level="INFO",
            rotation="1 day",
            retention="30 days"
        )


async def main():
    parser = argparse.ArgumentParser(description="每日论文自动抓取调度器")
    parser.add_argument("--daemon", action="store_true", help="以守护进程模式运行")
    parser.add_argument("--run-now", action="store_true", help="立即执行一次抓取任务")
    parser.add_argument("--log-file", default="daily_scheduler.log", help="日志文件路径")
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(args.log_file)
    
    # 检查必要的环境变量
    required_env = ["GROQ_API_KEY"]
    missing_env = [env for env in required_env if not os.getenv(env)]
    if missing_env:
        logger.error(f"❌ 缺少必要的环境变量: {', '.join(missing_env)}")
        return
    
    # 创建调度器实例
    scheduler = DailyPaperScheduler()
    
    if args.run_now:
        # 立即执行一次
        logger.info("🚀 立即执行模式")
        success = await scheduler.run_once()
        if success:
            logger.info("✅ 任务执行成功")
        else:
            logger.error("❌ 任务执行失败")
            sys.exit(1)
    
    elif args.daemon:
        # 守护进程模式
        logger.info("🔄 守护进程模式")
        await scheduler.run_daemon()
    
    else:
        # 显示帮助信息
        parser.print_help()
        logger.info("\n使用示例:")
        logger.info("  python daily_scheduler.py --daemon      # 后台定时运行")
        logger.info("  python daily_scheduler.py --run-now     # 立即执行一次")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 程序被用户中断")
    except Exception as e:
        logger.error(f"❌ 程序异常退出: {e}")
        sys.exit(1)
