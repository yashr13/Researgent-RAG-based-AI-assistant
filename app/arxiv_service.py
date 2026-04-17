import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from fastapi import HTTPException


ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
ARXIV_API = "https://export.arxiv.org/api/query"


def _text(node, path: str):
    found = node.find(path, ATOM_NS)
    return found.text.strip() if found is not None and found.text else ""


def _entry_to_paper(entry):
    entry_id = _text(entry, "atom:id")
    arxiv_id = entry_id.rsplit("/", 1)[-1]
    authors = [
        _text(author, "atom:name")
        for author in entry.findall("atom:author", ATOM_NS)
    ]
    pdf_url = ""
    for link in entry.findall("atom:link", ATOM_NS):
        if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
            pdf_url = link.attrib.get("href", "")
            break

    return {
        "arxiv_id": arxiv_id,
        "title": _text(entry, "atom:title").replace("\n", " "),
        "authors": authors,
        "summary": _text(entry, "atom:summary"),
        "published": _text(entry, "atom:published"),
        "updated": _text(entry, "atom:updated"),
        "url": entry_id,
        "pdf_url": pdf_url,
    }


def _fetch(params):
    url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "RAGAssistant/1.0 (local research assistant)"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach arXiv: {exc}") from exc

    root = ET.fromstring(data)
    return [_entry_to_paper(entry) for entry in root.findall("atom:entry", ATOM_NS)]


def search_arxiv(query: str, max_results: int = 8):
    cleaned = query.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Search query is required.")

    return _fetch({
        "search_query": f"all:{cleaned}",
        "start": 0,
        "max_results": max(1, min(max_results, 20)),
        "sortBy": "relevance",
        "sortOrder": "descending",
    })


def get_arxiv_paper(arxiv_id: str):
    cleaned = arxiv_id.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="arXiv ID is required.")

    papers = _fetch({
        "id_list": cleaned,
        "max_results": 1,
    })
    if not papers:
        raise HTTPException(status_code=404, detail=f"No arXiv paper found for '{cleaned}'.")
    return papers[0]
