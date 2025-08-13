#!/usr/bin/env python3
"""
智能数据管道测试脚本

这个脚本演示了新的AI驱动的智能论文抓取管道，包括：
1. 递归深度控制
2. AI智能引用分析
3. 自动过滤已存在的论文
4. 完整的知识图谱构建

使用方法:
    python test_smart_pipeline.py --arxiv-id 1706.03762 --max-depth 1
"""

import os
import sys
import argparse
from datetime import date
from loguru import logger

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from qdrant_client import QdrantClient
from graph.neo4j_manager import Neo4jManager
from sources.arxiv_fetcher import fetch_papers_by_ids
from pipelines.process_paper import process_and_ingest_paper
import pipelines.process_paper as pp


def setup_logging():
    """设置日志"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )


def test_smart_pipeline(arxiv_id: str, max_depth: int = 1):
    """测试智能管道"""
    logger.info("🚀 开始测试智能数据管道")
    logger.info(f"目标论文: {arxiv_id}")
    logger.info(f"最大递归深度: {max_depth}")
    
    # 临时设置最大深度
    original_depth = pp.MAX_INGESTION_DEPTH
    pp.MAX_INGESTION_DEPTH = max_depth
    
    try:
        # 1. 获取论文元数据
        logger.info("📄 获取论文元数据...")
        papers = fetch_papers_by_ids([arxiv_id], fetch_date=str(date.today()))
        if not papers:
            logger.error(f"❌ 无法找到论文: {arxiv_id}")
            return False
        
        paper = papers[0]
        logger.info(f"✅ 成功获取论文: {paper.title}")
        
        # 2. 初始化数据库连接
        logger.info("🔌 初始化数据库连接...")
        qdrant = QdrantClient(url="http://localhost:6333")
        graph = Neo4jManager(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "neo4j_password")
        )
        
        try:
            # 3. 开始智能处理
            logger.info("🧠 开始AI驱动的智能处理...")
            process_and_ingest_paper(
                paper_meta=paper,
                qdrant_client=qdrant,
                graph_manager=graph,
                current_depth=0,
                fetch_date=str(date.today())
            )
            
            logger.info("✅ 智能管道处理完成！")
            return True
            
        finally:
            graph.close()
            
    except Exception as e:
        logger.error(f"❌ 智能管道测试失败: {e}")
        return False
    finally:
        # 恢复原始深度设置
        pp.MAX_INGESTION_DEPTH = original_depth


def analyze_results(graph_manager: Neo4jManager, arxiv_id: str):
    """分析处理结果"""
    logger.info("📊 分析处理结果...")
    
    try:
        # 获取论文的引用信息
        with graph_manager.driver.session() as session:
            query = """
            MATCH (p:Paper {arxiv_id: $arxiv_id})-[:CITES]->(cited:Paper)
            RETURN count(cited) as total_citations,
                   count(case when cited.title IS NOT NULL then 1 end) as complete_citations
            """
            result = session.run(query, arxiv_id=arxiv_id)
            record = result.single()
            
            if record:
                total = record["total_citations"]
                complete = record["complete_citations"]
                logger.info(f"📈 引用统计:")
                logger.info(f"   总引用数: {total}")
                logger.info(f"   完整元数据引用数: {complete}")
                logger.info(f"   元数据完整率: {complete/total*100:.1f}%" if total > 0 else "   元数据完整率: N/A")
                
    except Exception as e:
        logger.error(f"❌ 结果分析失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="测试智能数据管道")
    parser.add_argument("--arxiv-id", required=True, help="要测试的arXiv论文ID")
    parser.add_argument("--max-depth", type=int, default=1, help="最大递归深度 (默认: 1)")
    parser.add_argument("--analyze", action="store_true", help="分析处理结果")
    
    args = parser.parse_args()
    
    setup_logging()
    
    # 检查环境变量
    if not os.getenv("GROQ_API_KEY"):
        logger.error("❌ 请设置 GROQ_API_KEY 环境变量")
        return
    
    logger.info("🔍 智能数据管道测试开始")
    logger.info("=" * 60)
    
    # 运行测试
    success = test_smart_pipeline(args.arxiv_id, args.max_depth)
    
    if success and args.analyze:
        # 分析结果
        graph = Neo4jManager(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "neo4j_password")
        )
        try:
            analyze_results(graph, args.arxiv_id)
        finally:
            graph.close()
    
    logger.info("=" * 60)
    if success:
        logger.info("🎉 智能数据管道测试成功完成！")
    else:
        logger.error("💥 智能数据管道测试失败")


if __name__ == "__main__":
    main()
