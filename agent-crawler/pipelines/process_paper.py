from __future__ import annotations

import os
from loguru import logger
from typing import List
from datetime import date
from .process_pdf import download_pdf, extract_with_pymupdf, build_text_embedder, build_image_embedder, upsert_chunks, ensure_qdrant_collection
from models import PaperMetadata
from qdrant_client import QdrantClient
from sources.arxiv_fetcher import fetch_papers_by_ids
from rag.summarizer import create_paper_summarizer
from rag.agents import create_paper_analysis_agents

# 递归深度限制
MAX_INGESTION_DEPTH = 1
MAX_IMPORTANT_REFERENCES = 5


def extract_references_from_text(full_text: str) -> List[str]:
    import re
    pattern = r"(?:arXiv:)?(\d{4}\.\d{4,5})"
    return list(sorted(set(re.findall(pattern, full_text))))


def process_and_ingest_paper(
    paper_meta: PaperMetadata, 
    qdrant_client: QdrantClient, 
    graph_manager,
    current_depth: int = 0,
    fetch_date: str = None
) -> None:
    import fitz  # type: ignore
    import io
    import base64
    import numpy as np
    from PIL import Image

    # === 1. 深度检查 (递归停止条件) ===
    if current_depth > MAX_INGESTION_DEPTH:
        logger.info("Max ingestion depth ({}) reached for paper {}. Halting recursion.", 
                   MAX_INGESTION_DEPTH, paper_meta.arxiv_id)
        return

    # 设置 fetch_date
    if fetch_date is None:
        fetch_date = str(date.today())
    if paper_meta.fetch_date is None:
        paper_meta.fetch_date = fetch_date

    logger.info("[Depth {}] Processing paper: {} - {}", 
               current_depth, paper_meta.arxiv_id, paper_meta.title)

    # 1) Download PDF (失败/超时才算整篇失败)
    import httpx
    response = httpx.get(paper_meta.pdf_url, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    pdf_bytes = response.content

    # 2) Extract references from full text AND generate AI summary
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = "".join([doc.load_page(i).get_text("text") for i in range(doc.page_count)])
    refs = extract_references_from_text(full_text)
    paper_meta.references = refs
    
    # 2.5) Generate AI-powered comprehensive analysis using LangGraph agents
    use_langgraph = os.getenv("USE_LANGGRAPH", "true").lower() == "true"
    
    if use_langgraph:
        try:
            logger.info("Using LangGraph agents for paper analysis")
            agents = create_paper_analysis_agents()
            analysis_result = agents.analyze_paper(paper_meta, full_text)
            
            # Update paper metadata with agent-generated fields
            paper_meta.ai_summary = analysis_result["ai_summary"]
            paper_meta.domain = analysis_result["domain"]
            paper_meta.key_contributions = analysis_result["key_contributions"]
            paper_meta.methodology = analysis_result["methodology"]
            
            logger.info("Enhanced paper metadata with LangGraph agents: domain={}, summary_len={}, contributions={}", 
                       analysis_result["domain"], 
                       len(analysis_result["ai_summary"]) if analysis_result["ai_summary"] else 0,
                       len(analysis_result["key_contributions"]))
        except Exception as e:
            logger.warning("LangGraph agents failed, falling back to basic summarizer: {}", e)
            use_langgraph = False
    
    if not use_langgraph:
        try:
            logger.info("Using basic summarizer (fallback)")
            summarizer = create_paper_summarizer()
            ai_summary, domain, key_contributions, methodology = summarizer.generate_comprehensive_summary(
                paper_meta, full_text, max_length=400
            )
            
            # Update paper metadata with AI-generated fields
            paper_meta.ai_summary = ai_summary
            paper_meta.domain = domain
            paper_meta.key_contributions = key_contributions
            paper_meta.methodology = methodology
            
            logger.info("Enhanced paper metadata with basic AI summary: domain={}, summary_len={}", 
                       domain, len(ai_summary) if ai_summary else 0)
        except Exception as e:
            logger.warning("Failed to generate AI summary, using basic fallback: {}", e)
            # Fallback to basic processing
            paper_meta.ai_summary = paper_meta.abstract
            paper_meta.domain = "Computer Science"

    # 3) Upsert to graph
    graph_manager.add_paper(paper_meta)
    graph_manager.add_citations(paper_meta.arxiv_id, refs)
    logger.info("Graph upsert done: {} refs", len(refs))

    # 4) Chunk + embed and upsert to Qdrant
    chunks = extract_with_pymupdf(pdf_bytes, paper_id=paper_meta.arxiv_id)
    text_chunks = [c for c in chunks if c.chunk_type == "text"]
    # 限制最多 30 张图片
    max_imgs = int(os.getenv("MAX_IMAGE_CHUNKS", "30"))
    image_chunks = [c for c in chunks if c.chunk_type == "image"][:max_imgs]

    text_model = build_text_embedder()
    text_vectors = text_model.encode([c.content or "" for c in text_chunks], batch_size=32, show_progress_bar=False, normalize_embeddings=True)

    image_vectors = []
    try:
        from .process_pdf import open_clip, torch
        if image_chunks and open_clip is not None and torch is not None:
            model, preprocess = build_image_embedder()
            ims = []
            for ch in image_chunks:
                try:
                    img = Image.open(io.BytesIO(base64.b64decode(ch.image_b64 or "")))
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    ims.append(np.array(preprocess(img)).astype(np.float32))
                except Exception as e:
                    logger.warning("Skip one image (decode/format): {}", e)
                    continue
            if ims:
                import torch as _torch
                with _torch.no_grad():
                    batch = _torch.stack([_torch.from_numpy(im) for im in ims])
                    feats = model.encode_image(batch)
                    image_vectors = feats.cpu().numpy()
    except Exception as e:
        logger.warning("Skip image embedding stage: {}", e)

    # Qdrant upsert 可选/失败不致命
    try:
        text_dim = int(text_vectors.shape[1]) if hasattr(text_vectors, 'shape') else (len(text_vectors[0]) if text_chunks else 384)
        ensure_qdrant_collection(qdrant_client, collection="papers", vector_size_text=text_dim, vector_size_image=512)
        upsert_chunks(
            qdrant_client, collection="papers",
            paper_id=paper_meta.arxiv_id,
            text_vectors=text_vectors, text_chunks=text_chunks,
            image_vectors=image_vectors, image_chunks=image_chunks
        )
        logger.info("Vector upsert done: text={}, image={}", len(text_chunks), len(image_chunks))
    except Exception as e:
        logger.warning("Vector upsert skipped (non-fatal): {}", e)

    # 5) 智能引用扩展 (新核心功能)
    if current_depth < MAX_INGESTION_DEPTH and refs:
        try:
            logger.info("[Depth {}] Starting intelligent reference expansion for paper {}", 
                       current_depth, paper_meta.arxiv_id)
            
            # 使用 AI Agent 分析哪些引用最重要
            agents = create_paper_analysis_agents()
            analysis_result = agents.analyze_references(full_text, refs, MAX_IMPORTANT_REFERENCES)
            important_ref_ids = analysis_result.get("important_references", [])
            
            if not important_ref_ids:
                logger.info("[Depth {}] No important references identified by AI for {}", 
                           current_depth, paper_meta.arxiv_id)
            else:
                logger.info("[Depth {}] AI identified {} important references for {}: {}", 
                           current_depth, len(important_ref_ids), paper_meta.arxiv_id, important_ref_ids)

                # 过滤掉已经存在完整元数据的论文
                new_ids_to_process = graph_manager.filter_existing_papers_with_metadata(important_ref_ids)
                
                if not new_ids_to_process:
                    logger.info("[Depth {}] All important references already exist with metadata. No new ingestion needed.", 
                               current_depth)
                else:
                    logger.info("[Depth {}] Fetching metadata for {} new important references: {}", 
                               current_depth, len(new_ids_to_process), new_ids_to_process)

                    # 从 arXiv API 获取这些重要引用的元数据
                    try:
                        new_papers_meta = fetch_papers_by_ids(new_ids_to_process, fetch_date)
                        logger.info("[Depth {}] Successfully fetched metadata for {} papers", 
                                   current_depth, len(new_papers_meta))
                        
                        # 递归处理每个重要引用
                        for new_paper in new_papers_meta:
                            logger.info("[Depth {}] Recursively processing important reference: {}", 
                                       current_depth, new_paper.arxiv_id)
                            try:
                                process_and_ingest_paper(
                                    paper_meta=new_paper,
                                    qdrant_client=qdrant_client,
                                    graph_manager=graph_manager,
                                    current_depth=current_depth + 1,  # 递增深度
                                    fetch_date=fetch_date
                                )
                            except Exception as e:
                                logger.error("[Depth {}] Failed to process reference {}: {}", 
                                           current_depth, new_paper.arxiv_id, e)
                                # 继续处理其他引用，不中断流程
                                continue
                                
                    except Exception as e:
                        logger.error("[Depth {}] Failed to fetch metadata for important references: {}", 
                                   current_depth, e)

        except Exception as e:
            logger.error("[Depth {}] Failed during intelligent reference expansion for {}: {}", 
                        current_depth, paper_meta.arxiv_id, e)

    logger.info("[Depth {}] Completed processing paper: {}", current_depth, paper_meta.arxiv_id)


def backfill_cited_papers_metadata(graph_manager) -> None:
    """批量补全图中缺少元数据的被引论文"""
    incomplete_ids = graph_manager.get_incomplete_cited_papers(limit=20)  # 每次处理20个，避免API过载
    if not incomplete_ids:
        logger.info("No incomplete cited papers found")
        return
    
    logger.info("Found {} incomplete cited papers, fetching metadata...", len(incomplete_ids))
    
    try:
        # 批量从arXiv API获取元数据
        papers_metadata = fetch_papers_by_ids(incomplete_ids)
        logger.info("Successfully fetched metadata for {} papers", len(papers_metadata))
        
        # 批量更新到图数据库
        if papers_metadata:
            graph_manager.backfill_papers_metadata(papers_metadata)
            logger.info("Backfilled metadata for {} cited papers", len(papers_metadata))
    except Exception as e:
        logger.warning("Failed to backfill cited papers metadata: {}", e)


