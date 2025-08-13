from __future__ import annotations

from typing import List
from neo4j import GraphDatabase
from loguru import logger
from models import PaperMetadata


class Neo4jManager:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self.driver.close()

    def add_paper(self, paper_meta: PaperMetadata) -> None:
        with self.driver.session() as session:
            session.execute_write(self._create_paper_node, paper_meta)

    @staticmethod
    def _create_paper_node(tx, paper_meta: PaperMetadata):
        query = (
            "MERGE (p:Paper {arxiv_id: $arxiv_id}) "
            "ON CREATE SET p.title=$title, p.authors=$authors, p.abstract=$abstract, "
            "p.pdf_url=$pdf_url, p.publication_date=$publication_date, "
            "p.ai_summary=$ai_summary, p.domain=$domain, p.key_contributions=$key_contributions, "
            "p.methodology=$methodology, p.fetch_date=$fetch_date "
            "ON MATCH SET p.title=$title, p.authors=$authors, p.abstract=$abstract, "
            "p.pdf_url=$pdf_url, p.publication_date=$publication_date, "
            "p.ai_summary=$ai_summary, p.domain=$domain, p.key_contributions=$key_contributions, "
            "p.methodology=$methodology, p.fetch_date=$fetch_date"
        )
        tx.run(query, **paper_meta.model_dump())

    def add_citations(self, paper_id: str, cited_ids: List[str]) -> None:
        if not cited_ids:
            return
        with self.driver.session() as session:
            session.execute_write(self._create_citation_rels, paper_id, cited_ids)

    @staticmethod
    def _create_citation_rels(tx, paper_id: str, cited_ids: List[str]):
        query = (
            "MATCH (source:Paper {arxiv_id: $paper_id}) "
            "FOREACH (cid IN $cited_ids | "
            "  MERGE (cited:Paper {arxiv_id: cid}) "
            "  MERGE (source)-[:CITES]->(cited)"
            ")"
        )
        tx.run(query, paper_id=paper_id, cited_ids=cited_ids)

    def get_paper_metadata(self, arxiv_id: str) -> PaperMetadata:
        """获取单篇论文的完整元数据"""
        with self.driver.session() as session:
            result = session.execute_read(self._get_paper_metadata, arxiv_id)
            if not result:
                raise ValueError(f"Paper {arxiv_id} not found in graph database")
            return result

    @staticmethod
    def _get_paper_metadata(tx, arxiv_id: str):
        query = (
            "MATCH (p:Paper {arxiv_id: $arxiv_id}) "
            "RETURN p.arxiv_id as arxiv_id, p.title as title, p.authors as authors, "
            "p.abstract as abstract, p.pdf_url as pdf_url, p.publication_date as publication_date, "
            "p.ai_summary as ai_summary, p.domain as domain, p.key_contributions as key_contributions, "
            "p.methodology as methodology, p.fetch_date as fetch_date"
        )
        result = tx.run(query, arxiv_id=arxiv_id)
        record = result.single()
        if record:
            return PaperMetadata(
                arxiv_id=record["arxiv_id"],
                title=record["title"] or "",
                authors=record["authors"] or [],
                abstract=record["abstract"] or "",
                pdf_url=record["pdf_url"] or "",
                publication_date=record["publication_date"] or "",
                ai_summary=record["ai_summary"],
                domain=record["domain"],
                key_contributions=record["key_contributions"],
                methodology=record["methodology"],
                fetch_date=record["fetch_date"]
            )
        return None

    def get_cited_papers_metadata(self, arxiv_id: str, limit: int = 5) -> List[PaperMetadata]:
        """获取指定论文引用的其他论文的元数据"""
        with self.driver.session() as session:
            return session.execute_read(self._get_cited_papers_metadata, arxiv_id, limit)

    @staticmethod
    def _get_cited_papers_metadata(tx, arxiv_id: str, limit: int):
        query = (
            "MATCH (source:Paper {arxiv_id: $arxiv_id})-[:CITES]->(cited:Paper) "
            "WHERE cited.title IS NOT NULL AND cited.abstract IS NOT NULL "
            "RETURN cited.arxiv_id as arxiv_id, cited.title as title, cited.authors as authors, "
            "cited.abstract as abstract, cited.pdf_url as pdf_url, cited.publication_date as publication_date, "
            "cited.ai_summary as ai_summary, cited.domain as domain, cited.key_contributions as key_contributions, "
            "cited.methodology as methodology, cited.fetch_date as fetch_date "
            "LIMIT $limit"
        )
        result = tx.run(query, arxiv_id=arxiv_id, limit=limit)
        papers = []
        for record in result:
            papers.append(PaperMetadata(
                arxiv_id=record["arxiv_id"],
                title=record["title"] or "",
                authors=record["authors"] or [],
                abstract=record["abstract"] or "",
                pdf_url=record["pdf_url"] or "",
                publication_date=record["publication_date"] or "",
                ai_summary=record["ai_summary"],
                domain=record["domain"],
                key_contributions=record["key_contributions"],
                methodology=record["methodology"],
                fetch_date=record["fetch_date"]
            ))
        return papers

    def get_incomplete_cited_papers(self, limit: int = 100) -> List[str]:
        """获取图中缺少元数据的被引论文ID列表"""
        with self.driver.session() as session:
            return session.execute_read(self._get_incomplete_cited_papers, limit)

    @staticmethod
    def _get_incomplete_cited_papers(tx, limit: int):
        query = (
            "MATCH (p:Paper) "
            "WHERE p.title IS NULL OR p.abstract IS NULL "
            "RETURN p.arxiv_id as arxiv_id "
            "LIMIT $limit"
        )
        result = tx.run(query, limit=limit)
        return [record["arxiv_id"] for record in result]

    def backfill_papers_metadata(self, papers_list: List[PaperMetadata]) -> None:
        """批量补全论文元数据"""
        with self.driver.session() as session:
            for paper in papers_list:
                session.execute_write(self._update_paper_metadata, paper)

    @staticmethod
    def _update_paper_metadata(tx, paper_meta: PaperMetadata):
        query = (
            "MATCH (p:Paper {arxiv_id: $arxiv_id}) "
            "SET p.title = $title, p.authors = $authors, p.abstract = $abstract, "
            "p.pdf_url = $pdf_url, p.publication_date = $publication_date, "
            "p.ai_summary = $ai_summary, p.domain = $domain, p.key_contributions = $key_contributions, "
            "p.methodology = $methodology, p.fetch_date = $fetch_date"
        )
        tx.run(query, **paper_meta.model_dump())

    def filter_existing_papers_with_metadata(self, paper_ids: List[str]) -> List[str]:
        """
        Given a list of paper IDs, return a new list containing only those
        that DO NOT have complete metadata (e.g., title is null) in the database.
        This is used to avoid reprocessing papers that already have full information.
        """
        if not paper_ids:
            return []
        
        with self.driver.session() as session:
            return session.execute_read(self._filter_existing_papers, paper_ids)

    @staticmethod
    def _filter_existing_papers(tx, paper_ids: List[str]):
        # A paper is considered "existing/complete" if its title is not null.
        # This is a good proxy for whether it has been fully processed.
        query = (
            "UNWIND $paper_ids AS paperId "
            "MATCH (p:Paper {arxiv_id: paperId}) "
            "WHERE p.title IS NOT NULL "
            "RETURN p.arxiv_id AS existingId"
        )
        result = tx.run(query, paper_ids=paper_ids)
        existing_ids = {record["existingId"] for record in result}
        
        # Return IDs that were NOT found in the `existing_ids` set
        new_ids = [pid for pid in paper_ids if pid not in existing_ids]
        logger.info(f"Filtered {len(paper_ids)} paper IDs: {len(existing_ids)} already exist, {len(new_ids)} need processing")
        return new_ids


