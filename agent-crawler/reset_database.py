#!/usr/bin/env python3
"""
数据库重置脚本

清理Neo4j和Qdrant中的所有数据，为新的测试做准备
"""

import os
import sys
from loguru import logger
from dotenv import load_dotenv

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from graph.neo4j_manager import Neo4jManager
from qdrant_client import QdrantClient

load_dotenv()


def setup_logging():
    """设置日志"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
        level="INFO"
    )


def reset_neo4j_database():
    """清理Neo4j数据库"""
    logger.info("🗑️  开始清理Neo4j数据库...")
    
    try:
        graph = Neo4jManager(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "neo4j_password")
        )
        
        with graph.driver.session() as session:
            # 获取数据库统计
            result = session.run("MATCH (n) RETURN count(n) as node_count")
            node_count = result.single()["node_count"]
            
            result = session.run("MATCH ()-[r]->() RETURN count(r) as rel_count")
            rel_count = result.single()["rel_count"]
            
            logger.info(f"发现 {node_count} 个节点，{rel_count} 个关系")
            
            if node_count > 0 or rel_count > 0:
                # 删除所有节点和关系
                logger.info("删除所有节点和关系...")
                session.run("MATCH (n) DETACH DELETE n")
                
                # 验证删除
                result = session.run("MATCH (n) RETURN count(n) as node_count")
                remaining_nodes = result.single()["node_count"]
                
                if remaining_nodes == 0:
                    logger.info("✅ Neo4j数据库清理完成")
                else:
                    logger.warning(f"⚠️ 仍有 {remaining_nodes} 个节点未删除")
            else:
                logger.info("✅ Neo4j数据库已经是空的")
        
        graph.close()
        
    except Exception as e:
        logger.error(f"❌ Neo4j数据库清理失败: {e}")
        return False
    
    return True


def reset_qdrant_database():
    """清理Qdrant数据库"""
    logger.info("🗑️  开始清理Qdrant数据库...")
    
    try:
        qdrant = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))
        
        # 获取所有集合
        collections = qdrant.get_collections()
        collection_names = [col.name for col in collections.collections]
        
        logger.info(f"发现 {len(collection_names)} 个集合: {collection_names}")
        
        if collection_names:
            for collection_name in collection_names:
                logger.info(f"删除集合: {collection_name}")
                try:
                    qdrant.delete_collection(collection_name)
                    logger.info(f"✅ 集合 {collection_name} 删除成功")
                except Exception as e:
                    logger.warning(f"⚠️ 集合 {collection_name} 删除失败: {e}")
        else:
            logger.info("✅ Qdrant数据库已经是空的")
        
        # 验证删除
        collections_after = qdrant.get_collections()
        remaining_collections = [col.name for col in collections_after.collections]
        
        if not remaining_collections:
            logger.info("✅ Qdrant数据库清理完成")
        else:
            logger.warning(f"⚠️ 仍有集合未删除: {remaining_collections}")
        
    except Exception as e:
        logger.error(f"❌ Qdrant数据库清理失败: {e}")
        return False
    
    return True


def main():
    setup_logging()
    
    logger.info("🚀 开始数据库重置...")
    logger.info("=" * 50)
    
    # 确认操作
    confirm = input("⚠️  这将删除所有数据库内容！确认继续吗？(yes/no): ")
    if confirm.lower() not in ['yes', 'y']:
        logger.info("❌ 操作已取消")
        return
    
    success_count = 0
    
    # 清理Neo4j
    if reset_neo4j_database():
        success_count += 1
    
    # 清理Qdrant
    if reset_qdrant_database():
        success_count += 1
    
    logger.info("=" * 50)
    if success_count == 2:
        logger.info("🎉 数据库重置完成！所有数据已清理")
    else:
        logger.warning(f"⚠️ 数据库重置部分完成 ({success_count}/2)")
        logger.info("请检查错误信息并手动处理失败的部分")


if __name__ == "__main__":
    main()
