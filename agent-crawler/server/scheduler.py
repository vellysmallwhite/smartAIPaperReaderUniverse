"""
定时任务调度器 - 每日自动抓取AI论文

这个模块实现了：
1. 每日定时抓取最新AI论文
2. 智能模式处理重要引用
3. 与FastAPI服务器集成
4. 错误处理和日志记录
"""

import os
import asyncio
from datetime import date, datetime
from typing import Optional
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from sources.arxiv_fetcher import fetch_latest_ai_papers
from pipelines.process_paper import process_and_ingest_paper
from graph.neo4j_manager import Neo4jManager
from qdrant_client import QdrantClient


class DailyPaperScheduler:
    """每日论文抓取调度器"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.is_running = False
        
        # 配置参数
        self.daily_paper_count = int(os.getenv("DAILY_PAPER_COUNT", "8"))
        self.smart_mode = os.getenv("DAILY_SMART_MODE", "true").lower() == "true"
        self.schedule_time = os.getenv("DAILY_SCHEDULE_TIME", "10:00")  # 默认上午10点
        
        # 数据库连接参数
        self.neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD", "neo4j_password")
        self.qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        
        logger.info("每日论文调度器初始化完成")
        logger.info(f"配置参数: 论文数={self.daily_paper_count}, 智能模式={self.smart_mode}, 时间={self.schedule_time}")
    
    async def daily_paper_ingestion_task(self):
        """每日论文抓取任务"""
        task_start_time = datetime.now()
        today = str(date.today())
        
        logger.info("🚀 开始每日论文自动抓取任务")
        logger.info(f"📅 日期: {today}")
        logger.info(f"📊 目标论文数: {self.daily_paper_count}")
        logger.info(f"🧠 智能模式: {'启用' if self.smart_mode else '禁用'}")
        
        try:
            # 1. 获取今日最新论文
            logger.info("📄 获取今日最新AI论文...")
            papers = fetch_latest_ai_papers(
                max_results=self.daily_paper_count, 
                fetch_date=today
            )
            
            if not papers:
                logger.warning("⚠️ 未获取到今日论文")
                return
            
            logger.info(f"✅ 成功获取 {len(papers)} 篇论文")
            
            # 2. 初始化数据库连接
            logger.info("🔌 初始化数据库连接...")
            qdrant = QdrantClient(url=self.qdrant_url)
            graph = Neo4jManager(self.neo4j_uri, self.neo4j_user, self.neo4j_password)
            
            try:
                # 3. 批量处理论文
                success_count = 0
                error_count = 0
                total_papers_processed = 0
                
                for i, paper in enumerate(papers, 1):
                    logger.info(f"\n📄 处理论文 {i}/{len(papers)}: {paper.title[:60]}...")
                    logger.info(f"   arXiv ID: {paper.arxiv_id}")
                    
                    try:
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
                
                # 4. 统计报告
                task_end_time = datetime.now()
                processing_time = (task_end_time - task_start_time).total_seconds()
                
                logger.info(f"\n📊 每日论文抓取任务完成:")
                logger.info(f"   成功处理: {success_count}")
                logger.info(f"   处理失败: {error_count}")
                logger.info(f"   总计论文: {len(papers)}")
                logger.info(f"   处理时间: {processing_time:.1f} 秒")
                logger.info(f"   成功率: {success_count/len(papers)*100:.1f}%")
                
                # 5. 生成知识图谱统计
                await self._generate_graph_stats(graph, today)
                
            finally:
                graph.close()
                
        except Exception as e:
            logger.error(f"❌ 每日论文抓取任务失败: {e}")
            raise
    
    async def _generate_graph_stats(self, graph_manager: Neo4jManager, target_date: str):
        """生成知识图谱统计"""
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
                    
                    logger.info(f"📈 今日知识图谱统计:")
                    logger.info(f"   新增论文: {total}")
                    logger.info(f"   完整论文: {complete}")
                    logger.info(f"   涉及领域: {', '.join(filter(None, domains))}")
                
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
                    
                    logger.info(f"🔗 今日引用关系:")
                    logger.info(f"   发现引用: {total_cites}")
                    logger.info(f"   完整引用: {complete_cites}")
                    if total_cites > 0:
                        completion_rate = complete_cites/total_cites*100
                        logger.info(f"   引用完整率: {completion_rate:.1f}%")
                        
        except Exception as e:
            logger.error(f"❌ 知识图谱统计生成失败: {e}")
    
    def start_scheduler(self):
        """启动定时调度器"""
        if self.is_running:
            logger.warning("调度器已在运行中")
            return
        
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
        
        logger.info(f"✅ 定时调度器已启动")
        logger.info(f"📅 每日执行时间: {self.schedule_time} (中国时间)")
        logger.info(f"🔄 下次执行时间: {self.scheduler.get_job('daily_paper_ingestion').next_run_time}")
    
    def stop_scheduler(self):
        """停止定时调度器"""
        if not self.is_running:
            logger.warning("调度器未在运行")
            return
        
        self.scheduler.shutdown()
        self.is_running = False
        logger.info("🛑 定时调度器已停止")
    
    async def run_manual_task(self) -> bool:
        """手动执行一次抓取任务"""
        logger.info("🔧 手动执行每日论文抓取任务...")
        try:
            await self.daily_paper_ingestion_task()
            logger.info("✅ 手动任务执行成功")
            return True
        except Exception as e:
            logger.error(f"❌ 手动任务执行失败: {e}")
            return False
    
    def get_scheduler_status(self) -> dict:
        """获取调度器状态"""
        if not self.is_running:
            return {
                "running": False,
                "message": "调度器未启动"
            }
        
        job = self.scheduler.get_job('daily_paper_ingestion')
        if job:
            return {
                "running": True,
                "next_run_time": str(job.next_run_time),
                "schedule_time": self.schedule_time,
                "daily_paper_count": self.daily_paper_count,
                "smart_mode": self.smart_mode
            }
        else:
            return {
                "running": True,
                "message": "调度器运行中但任务未找到"
            }


# 全局调度器实例
_scheduler: Optional[DailyPaperScheduler] = None


def get_scheduler() -> DailyPaperScheduler:
    """获取全局调度器实例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = DailyPaperScheduler()
    return _scheduler


def start_daily_scheduler():
    """启动每日调度器"""
    scheduler = get_scheduler()
    scheduler.start_scheduler()


def stop_daily_scheduler():
    """停止每日调度器"""
    scheduler = get_scheduler()
    scheduler.stop_scheduler()


async def run_manual_daily_task() -> bool:
    """手动执行每日任务"""
    scheduler = get_scheduler()
    return await scheduler.run_manual_task()


def get_daily_scheduler_status() -> dict:
    """获取调度器状态"""
    scheduler = get_scheduler()
    return scheduler.get_scheduler_status()
