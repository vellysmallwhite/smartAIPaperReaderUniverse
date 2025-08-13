#!/usr/bin/env python3
"""
每日论文自动抓取测试脚本

这个脚本测试自动抓取今日最热门AI论文的功能，包括：
1. 获取今日最新的10篇AI论文
2. 使用智能管道处理每篇论文
3. 自动识别和处理重要引用
4. 生成统计报告

使用方法:
    python test_daily_ingestion.py --max-papers 5 --smart-mode
"""

import os
import sys
import argparse
from datetime import date, datetime
from loguru import logger
from typing import List

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from qdrant_client import QdrantClient
from graph.neo4j_manager import Neo4jManager
from sources.arxiv_fetcher import fetch_latest_ai_papers
from pipelines.process_paper import process_and_ingest_paper
from models import PaperMetadata
import pipelines.process_paper as pp


def setup_logging():
    """设置日志"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )


def fetch_daily_papers(max_papers: int = 10) -> List[PaperMetadata]:
    """获取今日最新AI论文"""
    logger.info("🔍 获取今日最新AI论文 (max_papers={})", max_papers)
    
    try:
        today = str(date.today())
        papers = fetch_latest_ai_papers(max_results=max_papers, fetch_date=today)
        
        logger.info("✅ 成功获取 {} 篇今日论文", len(papers))
        for i, paper in enumerate(papers, 1):
            logger.info(f"  {i}. {paper.title[:80]}..." if len(paper.title) > 80 else f"  {i}. {paper.title}")
            logger.info(f"     arXiv ID: {paper.arxiv_id} | 作者: {paper.authors[0]} 等")
        
        return papers
        
    except Exception as e:
        logger.error("❌ 获取今日论文失败: {}", e)
        return []


def process_papers_batch(
    papers: List[PaperMetadata], 
    qdrant_client: QdrantClient, 
    graph_manager: Neo4jManager,
    smart_mode: bool = True
):
    """批量处理论文"""
    logger.info("🚀 开始批量处理论文 (smart_mode={})", smart_mode)
    
    success_count = 0
    error_count = 0
    total_papers_processed = 0
    
    for i, paper in enumerate(papers, 1):
        logger.info(f"\n📄 处理论文 {i}/{len(papers)}: {paper.title}")
        logger.info(f"   arXiv ID: {paper.arxiv_id}")
        
        try:
            if smart_mode:
                # 使用智能管道
                process_and_ingest_paper(
                    paper_meta=paper,
                    qdrant_client=qdrant_client,
                    graph_manager=graph_manager,
                    current_depth=0,
                    fetch_date=paper.fetch_date
                )
            else:
                # 使用基础管道（深度=0，不递归）
                original_depth = pp.MAX_INGESTION_DEPTH
                pp.MAX_INGESTION_DEPTH = 0
                try:
                    process_and_ingest_paper(
                        paper_meta=paper,
                        qdrant_client=qdrant_client,
                        graph_manager=graph_manager,
                        current_depth=0,
                        fetch_date=paper.fetch_date
                    )
                finally:
                    pp.MAX_INGESTION_DEPTH = original_depth
            
            success_count += 1
            logger.info("✅ 论文处理成功: {}", paper.arxiv_id)
            
        except Exception as e:
            error_count += 1
            logger.error("❌ 论文处理失败: {} - {}", paper.arxiv_id, e)
            continue
    
    logger.info(f"\n📊 批量处理完成:")
    logger.info(f"   成功处理: {success_count}")
    logger.info(f"   处理失败: {error_count}")
    logger.info(f"   总计论文: {len(papers)}")
    
    return success_count, error_count


def generate_daily_report(graph_manager: Neo4jManager, target_date: str):
    """生成今日处理报告"""
    logger.info("📊 生成今日处理报告...")
    
    try:
        with graph_manager.driver.session() as session:
            # 今日处理的论文统计
            query_today = """
            MATCH (p:Paper) 
            WHERE p.fetch_date = $date
            RETURN count(p) as total_papers,
                   count(case when p.title IS NOT NULL then 1 end) as complete_papers,
                   collect(p.domain)[0..5] as sample_domains
            """
            result = session.run(query_today, date=target_date)
            record = result.single()
            
            if record:
                total = record["total_papers"]
                complete = record["complete_papers"]
                domains = record["sample_domains"]
                
                logger.info(f"📈 今日处理统计 ({target_date}):")
                logger.info(f"   总论文数: {total}")
                logger.info(f"   完整论文数: {complete}")
                logger.info(f"   样本领域: {', '.join(filter(None, domains))}")
            
            # 今日新增的引用关系
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
                logger.info(f"   总引用数: {total_cites}")
                logger.info(f"   完整引用数: {complete_cites}")
                if total_cites > 0:
                    logger.info(f"   引用完整率: {complete_cites/total_cites*100:.1f}%")
            
            # 热门论文（被引用最多的）
            query_popular = """
            MATCH (p:Paper)<-[:CITES]-(citing:Paper)
            WHERE citing.fetch_date = $date
            RETURN p.arxiv_id as arxiv_id, p.title as title, count(citing) as citation_count
            ORDER BY citation_count DESC
            LIMIT 5
            """
            result = session.run(query_popular, date=target_date)
            popular_papers = [r.data() for r in result]
            
            if popular_papers:
                logger.info(f"🔥 今日热门被引论文:")
                for i, paper in enumerate(popular_papers, 1):
                    title = paper["title"] or paper["arxiv_id"]
                    count = paper["citation_count"]
                    logger.info(f"   {i}. {title[:60]}{'...' if len(title) > 60 else ''} (被引{count}次)")
            
    except Exception as e:
        logger.error("❌ 报告生成失败: {}", e)


def main():
    parser = argparse.ArgumentParser(description="每日论文自动抓取测试")
    parser.add_argument("--max-papers", type=int, default=5, help="抓取的最大论文数 (默认: 5)")
    parser.add_argument("--smart-mode", action="store_true", help="启用智能模式（递归处理重要引用）")
    parser.add_argument("--generate-report", action="store_true", help="生成处理报告")
    parser.add_argument("--target-date", default=str(date.today()), help="目标日期 (默认: 今天)")
    
    args = parser.parse_args()
    
    setup_logging()
    
    # 检查环境变量
    required_env = ["GROQ_API_KEY"] if args.smart_mode else []
    for env_var in required_env:
        if not os.getenv(env_var):
            logger.error(f"❌ 请设置 {env_var} 环境变量")
            return
    
    logger.info("🌟 每日论文自动抓取测试开始")
    logger.info("=" * 60)
    logger.info(f"📅 目标日期: {args.target_date}")
    logger.info(f"📊 最大论文数: {args.max_papers}")
    logger.info(f"🧠 智能模式: {'启用' if args.smart_mode else '禁用'}")
    logger.info("=" * 60)
    
    # 1. 获取今日论文
    papers = fetch_daily_papers(args.max_papers)
    if not papers:
        logger.error("❌ 无法获取今日论文，测试终止")
        return
    
    # 2. 初始化数据库连接
    logger.info("🔌 初始化数据库连接...")
    try:
        qdrant = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
        graph = Neo4jManager(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "neo4j_password")
        )
        logger.info("✅ 数据库连接成功")
    except Exception as e:
        logger.error("❌ 数据库连接失败: {}", e)
        return
    
    try:
        # 3. 批量处理论文
        start_time = datetime.now()
        success_count, error_count = process_papers_batch(
            papers, qdrant, graph, args.smart_mode
        )
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        # 4. 生成报告
        if args.generate_report:
            generate_daily_report(graph, args.target_date)
        
        # 5. 最终统计
        logger.info("\n" + "=" * 60)
        logger.info("🎉 每日论文抓取测试完成！")
        logger.info(f"⏱️  总处理时间: {processing_time:.1f} 秒")
        logger.info(f"📊 成功率: {success_count}/{len(papers)} ({success_count/len(papers)*100:.1f}%)")
        
        if args.smart_mode and success_count > 0:
            logger.info("🧠 智能模式已启用 - 重要引用已自动处理")
        
    finally:
        graph.close()


if __name__ == "__main__":
    main()
