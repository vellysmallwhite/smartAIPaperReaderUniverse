import os
import typer
from typing import Optional
from pipelines.process_pdf import process_pdf_command
from pipelines.process_paper import process_and_ingest_paper, backfill_cited_papers_metadata
from sources.arxiv_fetcher import fetch_papers_by_ids, fetch_latest_ai_papers
from graph.neo4j_manager import Neo4jManager
from qdrant_client import QdrantClient
from rag.insights import create_insight_generator
from dotenv import load_dotenv


load_dotenv()  # Load env vars from .env if present
app = typer.Typer(help="Agent crawler CLI")


@app.command("process-pdf")
def cmd_process_pdf(
    url_arg: Optional[str] = typer.Argument(None, help="PDF URL as positional argument"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="PDF URL (alternative to positional)"),
    paper_id: Optional[str] = typer.Option(None, "--paper-id", "-p", help="Override paper id"),
):
    effective_url = url or url_arg
    if not effective_url:
        raise typer.BadParameter("Please provide a PDF URL as positional argument or via --url/-u")
    process_pdf_command(url=effective_url, paper_id=paper_id)


@app.command("ingest-arxiv")
def ingest_arxiv(
    arxiv_id: str = typer.Argument(..., help="arXiv ID to ingest, e.g., 1706.03762"),
    neo4j_uri: str = typer.Option("bolt://localhost:7687", help="Neo4j bolt URI"),
    neo4j_user: str = typer.Option("neo4j", help="Neo4j user"),
    neo4j_password: str = typer.Option("neo4j_password", help="Neo4j password"),
):
    from datetime import date
    
    papers = fetch_papers_by_ids([arxiv_id], fetch_date=str(date.today()))
    if not papers:
        raise typer.BadParameter(f"arXiv id not found: {arxiv_id}")
    paper = papers[0]
    qdrant = QdrantClient(url="http://localhost:6333")
    graph = Neo4jManager(neo4j_uri, neo4j_user, neo4j_password)
    try:
        process_and_ingest_paper(paper, qdrant, graph, current_depth=0, fetch_date=str(date.today()))
    finally:
        graph.close()


@app.command("get-insight")
def get_insight(
    arxiv_id: str = typer.Argument(..., help="arXiv ID to generate insight for, e.g., 1706.03762"),
    neo4j_uri: str = typer.Option("bolt://localhost:7687", envvar="NEO4J_URI", help="Neo4j bolt URI"),
    neo4j_user: str = typer.Option("neo4j", envvar="NEO4J_USER", help="Neo4j user"),
    neo4j_password: str = typer.Option("neo4j_password", envvar="NEO4J_PASSWORD", help="Neo4j password"),
    qdrant_url: str = typer.Option("http://localhost:6333", envvar="QDRANT_URL", help="Qdrant URL"),
    openai_api_key: Optional[str] = typer.Option(None, envvar="OPENAI_API_KEY", help="OpenAI API key (or provider key)"),
    openai_base_url: Optional[str] = typer.Option(None, envvar="OPENAI_BASE_URL", help="OpenAI-compatible base URL (e.g., vLLM/OpenRouter/Groq if compatible)"),
    model_name: str = typer.Option(os.getenv("MODEL_NAME", "openai/gpt-oss-20b"), help="LLM model name (env: MODEL_NAME)"),
):
    """生成指定arXiv论文的深度洞察分析"""
    try:
        # 创建insight生成器
        generator = create_insight_generator(
            qdrant_url=qdrant_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
            openai_api_key=openai_api_key,
            openai_base_url=openai_base_url,
            model_name=model_name,
        )
        
        # 生成洞察
        insight = generator.generate_insight(arxiv_id)
        
        # 输出结果
        print(f"\n{'='*60}")
        print(f"论文洞察分析: {arxiv_id}")
        print(f"{'='*60}")
        print(insight)
        print(f"{'='*60}\n")
        
    except Exception as e:
        typer.echo(f"错误：{e}", err=True)
        raise typer.Exit(1)
    finally:
        # 清理资源
        try:
            generator.graph_manager.close()
        except:
            pass


@app.command("backfill-metadata")
def backfill_metadata_cmd(
    neo4j_uri: str = typer.Option("bolt://localhost:7687", envvar="NEO4J_URI", help="Neo4j bolt URI"),
    neo4j_user: str = typer.Option("neo4j", envvar="NEO4J_USER", help="Neo4j user"),
    neo4j_password: str = typer.Option("neo4j_password", envvar="NEO4J_PASSWORD", help="Neo4j password"),
):
    """批量补全图中缺少元数据的被引论文"""
    graph = Neo4jManager(neo4j_uri, neo4j_user, neo4j_password)
    try:
        backfill_cited_papers_metadata(graph)
        print("✅ 被引论文元数据补全完成")
    finally:
        graph.close()


@app.command("smart-ingest")
def smart_ingest_cmd(
    arxiv_id: str = typer.Argument(..., help="arXiv ID to intelligently ingest with important references, e.g., 1706.03762"),
    neo4j_uri: str = typer.Option("bolt://localhost:7687", envvar="NEO4J_URI", help="Neo4j bolt URI"),
    neo4j_user: str = typer.Option("neo4j", envvar="NEO4J_USER", help="Neo4j user"),
    neo4j_password: str = typer.Option("neo4j_password", envvar="NEO4J_PASSWORD", help="Neo4j password"),
    max_depth: int = typer.Option(1, help="Maximum recursion depth for reference expansion"),
):
    """智能地抓取论文及其最重要的引用（带深度控制）"""
    from datetime import date
    from pipelines.process_paper import MAX_INGESTION_DEPTH
    
    # 临时设置最大深度
    import pipelines.process_paper as pp
    original_depth = pp.MAX_INGESTION_DEPTH
    pp.MAX_INGESTION_DEPTH = max_depth
    
    try:
        papers = fetch_papers_by_ids([arxiv_id], fetch_date=str(date.today()))
        if not papers:
            raise typer.BadParameter(f"arXiv id not found: {arxiv_id}")
        paper = papers[0]
        
        qdrant = QdrantClient(url="http://localhost:6333")
        graph = Neo4jManager(neo4j_uri, neo4j_user, neo4j_password)
        
        try:
            print(f"🚀 Starting intelligent ingestion for {arxiv_id} (max depth: {max_depth})")
            process_and_ingest_paper(paper, qdrant, graph, current_depth=0, fetch_date=str(date.today()))
            print("✅ 智能抓取完成")
        finally:
            graph.close()
    finally:
        # 恢复原始深度设置
        pp.MAX_INGESTION_DEPTH = original_depth


@app.command("fetch-daily")
def fetch_daily_papers_cmd(
    max_papers: int = typer.Option(10, help="Maximum number of papers to fetch"),
    smart_mode: bool = typer.Option(True, help="Enable smart mode with recursive reference processing"),
    neo4j_uri: str = typer.Option("bolt://localhost:7687", envvar="NEO4J_URI", help="Neo4j bolt URI"),
    neo4j_user: str = typer.Option("neo4j", envvar="NEO4J_USER", help="Neo4j user"),
    neo4j_password: str = typer.Option("neo4j_password", envvar="NEO4J_PASSWORD", help="Neo4j password"),
):
    """抓取今日最新AI论文并处理"""
    from datetime import date
    import pipelines.process_paper as pp
    
    print(f"🔍 开始抓取今日最新 {max_papers} 篇AI论文...")
    print(f"🧠 智能模式: {'启用' if smart_mode else '禁用'}")
    
    try:
        # 获取今日论文
        today = str(date.today())
        papers = fetch_latest_ai_papers(max_results=max_papers, fetch_date=today)
        
        if not papers:
            print("❌ 未找到今日论文")
            return
        
        print(f"✅ 成功获取 {len(papers)} 篇论文")
        
        # 初始化数据库连接
        qdrant = QdrantClient(url="http://localhost:6333")
        graph = Neo4jManager(neo4j_uri, neo4j_user, neo4j_password)
        
        # 如果不是智能模式，临时设置深度为0
        original_depth = pp.MAX_INGESTION_DEPTH
        if not smart_mode:
            pp.MAX_INGESTION_DEPTH = 0
        
        try:
            success_count = 0
            for i, paper in enumerate(papers, 1):
                print(f"\n📄 处理论文 {i}/{len(papers)}: {paper.title[:60]}...")
                try:
                    process_and_ingest_paper(
                        paper_meta=paper,
                        qdrant_client=qdrant,
                        graph_manager=graph,
                        current_depth=0,
                        fetch_date=today
                    )
                    success_count += 1
                    print(f"✅ 成功处理: {paper.arxiv_id}")
                except Exception as e:
                    print(f"❌ 处理失败: {paper.arxiv_id} - {e}")
                    continue
            
            print(f"\n🎉 今日论文抓取完成!")
            print(f"📊 成功处理: {success_count}/{len(papers)}")
            
        finally:
            graph.close()
            pp.MAX_INGESTION_DEPTH = original_depth
            
    except Exception as e:
        print(f"❌ 今日论文抓取失败: {e}")


if __name__ == "__main__":
    app()



