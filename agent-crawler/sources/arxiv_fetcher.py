from __future__ import annotations

from typing import List
import arxiv
from loguru import logger
from models import PaperMetadata


def _to_meta(r: arxiv.Result, fetch_date: str = None) -> PaperMetadata:
    from datetime import date
    if fetch_date is None:
        fetch_date = str(date.today())
    
    return PaperMetadata(
        arxiv_id=r.entry_id.split("/")[-1],
        title=r.title,
        authors=[a.name for a in r.authors],
        abstract=r.summary,
        pdf_url=r.pdf_url,
        publication_date=str(r.published.date()),
        fetch_date=fetch_date
    )


def fetch_papers_by_ids(id_list: List[str], fetch_date: str = None) -> List[PaperMetadata]:
    if not id_list:
        return []
    logger.info("Fetching arXiv by IDs: {}", id_list)
    search = arxiv.Search(id_list=id_list)
    results = list(search.results())
    return [_to_meta(r, fetch_date) for r in results]


def fetch_latest_ai_papers(max_results: int = 10, fetch_date: str = None) -> List[PaperMetadata]:
    logger.info("Fetching latest arXiv AI papers (max_results={})", max_results)
    search = arxiv.Search(
        query="cat:cs.AI OR cat:cs.CL OR cat:cs.CV",
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )
    results = list(search.results())
    return [_to_meta(r, fetch_date) for r in results]


