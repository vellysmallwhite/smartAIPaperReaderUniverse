#!/usr/bin/env python3
"""
测试并发论文处理
使用3个线程同时处理3篇不同的论文
"""

import os
import threading
import time
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

from sources.arxiv_fetcher import fetch_papers_by_ids
from pipelines.process_paper import process_and_ingest_paper
from graph.neo4j_manager import Neo4jManager
from qdrant_client import QdrantClient
from loguru import logger

# 配置
TEST_PAPER_IDS = [
    "2508.08248v1",  # StableAvatar
    "2508.08244v1",  # Cut2Next
    "2508.08243v1",  # Jinx
]

# 并发配置（可通过环境变量控制）
ENABLE_CONCURRENT = os.getenv("ENABLE_CONCURRENT_PROCESSING", "false").lower() == "true"
MAX_WORKERS = int(os.getenv("MAX_CONCURRENT_WORKERS", "3")) if ENABLE_CONCURRENT else 1
MAX_IMAGE_CHUNKS = 10  # 限制图片数量以提高速度

# 全局锁，防止并发处理同一篇论文
PROCESSING_LOCK = threading.Lock()
PROCESSED_PAPERS = set()

def process_single_paper(paper_id: str, worker_id: int) -> Tuple[str, bool, str]:
    """
    处理单篇论文
    返回: (paper_id, success, message)
    """
    start_time = time.time()
    thread_name = f"Worker-{worker_id}"
    
    try:
        logger.info(f"[{thread_name}] 开始处理论文: {paper_id}")
        
        # 检查是否已经在处理中
        with PROCESSING_LOCK:
            if paper_id in PROCESSED_PAPERS:
                return paper_id, False, "论文已在处理中，跳过"
            PROCESSED_PAPERS.add(paper_id)
        
        # 设置环境变量
        os.environ['MAX_IMAGE_CHUNKS'] = str(MAX_IMAGE_CHUNKS)
        
        # 获取论文元数据
        papers = fetch_papers_by_ids([paper_id], fetch_date=str(date.today()))
        if not papers:
            return paper_id, False, "无法获取论文元数据"
        
        paper = papers[0]
        logger.info(f"[{thread_name}] 论文标题: {paper.title[:50]}...")
        
        # 初始化数据库连接（每个线程独立连接）
        qdrant = QdrantClient(url="http://localhost:6333")
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")  
        neo4j_password = os.getenv("NEO4J_PASSWORD", "neo4j_password")
        graph = Neo4jManager(neo4j_uri, neo4j_user, neo4j_password)
        
        try:
            # 处理论文（深度设为0，避免递归引用处理）
            process_and_ingest_paper(
                paper_meta=paper,
                qdrant_client=qdrant,
                graph_manager=graph,
                current_depth=0,
                fetch_date=str(date.today())
            )
            
            end_time = time.time()
            processing_time = end_time - start_time
            message = f"处理成功，耗时 {processing_time:.1f} 秒"
            logger.info(f"[{thread_name}] {message}")
            return paper_id, True, message
            
        finally:
            graph.close()
            
    except Exception as e:
        end_time = time.time()
        processing_time = end_time - start_time
        error_msg = f"处理失败，耗时 {processing_time:.1f} 秒，错误: {str(e)}"
        logger.error(f"[{thread_name}] {error_msg}")
        return paper_id, False, error_msg

def test_concurrent_processing():
    """测试论文处理（可配置并发/顺序模式）"""
    mode = "并发" if ENABLE_CONCURRENT else "顺序"
    print(f"🚀 开始{mode}论文处理测试")
    print(f"📄 目标论文: {TEST_PAPER_IDS}")
    print(f"🔧 处理模式: {mode}（{MAX_WORKERS} workers）")
    print(f"🖼️  最大图片数: {MAX_IMAGE_CHUNKS}")
    print(f"⚙️  并发配置: ENABLE_CONCURRENT_PROCESSING={ENABLE_CONCURRENT}")
    print("-" * 60)
    
    start_time = time.time()
    results = []
    
    # 使用线程池执行器
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        future_to_paper = {
            executor.submit(process_single_paper, paper_id, i+1): paper_id 
            for i, paper_id in enumerate(TEST_PAPER_IDS)
        }
        
        # 等待任务完成并收集结果
        for future in as_completed(future_to_paper):
            paper_id = future_to_paper[future]
            try:
                result = future.result()
                results.append(result)
                paper_id, success, message = result
                status = "✅" if success else "❌"
                print(f"{status} {paper_id}: {message}")
            except Exception as e:
                results.append((paper_id, False, f"线程异常: {e}"))
                print(f"❌ {paper_id}: 线程异常: {e}")
    
    # 统计结果
    end_time = time.time()
    total_time = end_time - start_time
    success_count = sum(1 for _, success, _ in results if success)
    
    print("-" * 60)
    print("📊 并发处理结果统计:")
    print(f"   总论文数: {len(TEST_PAPER_IDS)}")
    print(f"   成功处理: {success_count}")
    print(f"   失败数量: {len(TEST_PAPER_IDS) - success_count}")
    print(f"   总耗时: {total_time:.1f} 秒")
    print(f"   平均耗时: {total_time/len(TEST_PAPER_IDS):.1f} 秒/篇")
    if success_count > 0:
        success_times = [
            float(msg.split("耗时 ")[1].split(" 秒")[0]) 
            for _, success, msg in results 
            if success and "耗时" in msg
        ]
        if success_times:
            avg_success_time = sum(success_times) / len(success_times)
            print(f"   成功论文平均耗时: {avg_success_time:.1f} 秒/篇")
    
    return results

if __name__ == "__main__":
    test_concurrent_processing()
