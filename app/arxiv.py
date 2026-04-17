from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import CurrentUser, require_user
from app.arxiv_service import get_arxiv_paper, search_arxiv
from app.db import add_document, list_documents
from app.ingestion import ingest_text


router = APIRouter()


class ArxivImportRequest(BaseModel):
    project_id: str
    arxiv_id: str


@router.get("/search")
def search(query: str, max_results: int = 8):
    return {"papers": search_arxiv(query, max_results)}


def _related_query(documents):
    external_terms = set()
    local_terms = []

    for document in documents:
        if document.get("source_type") == "arxiv":
            continue

        title = document.get("title") or document.get("filename") or ""
        abstract = document.get("abstract") or ""
        authors = document.get("authors") or []

        if title:
            local_terms.append(title.rsplit(".", 1)[0])
        if abstract:
            local_terms.append(" ".join(abstract.split()[:40]))
        for author in authors[:2]:
            external_terms.add(author)

    if not local_terms and documents:
        for document in documents:
            title = document.get("title") or document.get("filename") or ""
            if title:
                local_terms.append(title.rsplit(".", 1)[0])

    query = " ".join(local_terms[:3])
    author_terms = " ".join(sorted(external_terms)[:2])
    combined = f"{query} {author_terms}".strip()
    return " ".join(combined.split())


@router.get("/related")
def related(project_id: str, max_results: int = 6, user: CurrentUser = Depends(require_user)):
    documents = list_documents(user.id, project_id)
    if not documents:
        return {"query": "", "papers": []}

    query = _related_query(documents)
    if not query:
        return {"query": "", "papers": []}

    imported_ids = {
        document.get("external_id")
        for document in documents
        if document.get("source_type") == "arxiv" and document.get("external_id")
    }
    papers = [
        paper
        for paper in search_arxiv(query, max_results + len(imported_ids))
        if paper.get("arxiv_id") not in imported_ids
    ][:max_results]
    return {"query": query, "papers": papers}


@router.post("/import")
def import_paper(req: ArxivImportRequest, user: CurrentUser = Depends(require_user)):
    paper = get_arxiv_paper(req.arxiv_id)
    filename = f"arxiv-{paper['arxiv_id']}.txt"
    text = (
        f"Title: {paper['title']}\n\n"
        f"Authors: {', '.join(paper['authors'])}\n\n"
        f"Published: {paper['published']}\n\n"
        f"Abstract\n{paper['summary']}"
    )

    document = add_document(
        user.id,
        req.project_id,
        filename=filename,
        filepath=f"arxiv:{paper['arxiv_id']}",
        source_type="arxiv",
        external_id=paper["arxiv_id"],
        title=paper["title"],
        authors=paper["authors"],
        abstract=paper["summary"],
        url=paper["url"],
        published_at=paper["published"],
    )
    ingest_text(
        text,
        req.project_id,
        filename,
        metadata={
            "source_type": "arxiv",
            "external_id": paper["arxiv_id"],
            "title": paper["title"],
            "url": paper["url"],
            "published_at": paper["published"],
        },
        document_id=document["id"],
        owner_id=user.id,
    )
    return {"status": "success", "paper": paper, "document": document}
