import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document

from app.embeddings import get_embeddings
from app.vectorstore import add_documents

load_dotenv()


def _is_heading(line: str):
    candidate = line.strip()
    if not candidate or len(candidate) > 120:
        return False
    if candidate.endswith((".", ",", ";", ":")):
        return False
    if re.match(r"^\d+(\.\d+)*\s+[A-Z].*$", candidate):
        return True
    if candidate.isupper() and len(candidate.split()) <= 8:
        return True

    words = [word for word in re.split(r"\s+", candidate) if word]
    if not words or len(words) > 12:
        return False

    titled = sum(1 for word in words if word[:1].isupper())
    return titled >= max(2, len(words) - 1)


def _section_documents(docs, project_id: str, filename: str):
    section_docs = []

    for doc in docs:
        metadata = dict(doc.metadata or {})
        metadata["project_id"] = project_id
        metadata["filename"] = filename
        current_section = metadata.get("section_title") or "Document Overview"
        buffer = []

        for raw_line in doc.page_content.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if _is_heading(line):
                if buffer:
                    section_docs.append(
                        Document(
                            page_content="\n".join(buffer),
                            metadata={**metadata, "section_title": current_section},
                        )
                    )
                    buffer = []
                current_section = line
                continue

            buffer.append(line)

        if buffer:
            section_docs.append(
                Document(
                    page_content="\n".join(buffer),
                    metadata={**metadata, "section_title": current_section},
                )
            )

    return section_docs


def ingest_file(filepath, project_id, document_id: int | None = None, owner_id: str | None = None):
    suffix = Path(filepath).suffix.lower()
    filename = Path(filepath).name

    if suffix == ".pdf":
        loader = PyPDFLoader(filepath)
    elif suffix == ".docx":
        loader = Docx2txtLoader(filepath)
    elif suffix in {".txt", ".md", ".csv"}:
        loader = TextLoader(filepath, autodetect_encoding=True)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or 'unknown'}")

    try:
        docs = loader.load()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read '{filename}'. Please verify the file is valid and not corrupted.",
        ) from exc

    section_docs = _section_documents(docs, project_id, filename)

    splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=250)
    chunks = splitter.split_documents(section_docs)

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail=f"'{filename}' does not contain readable text to index.",
        )

    embeddings = get_embeddings()
    add_documents(project_id, document_id, chunks, embeddings, owner_id=owner_id)


def ingest_text(
    text: str,
    project_id: str,
    filename: str,
    metadata=None,
    document_id: int | None = None,
    owner_id: str | None = None,
):
    base_metadata = {
        "source": filename,
        "project_id": project_id,
        "filename": filename,
        **(metadata or {}),
    }
    docs = [Document(page_content=text, metadata=base_metadata)]
    section_docs = _section_documents(docs, project_id, filename)

    splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=250)
    chunks = splitter.split_documents(section_docs)

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail=f"'{filename}' does not contain readable text to index.",
        )

    embeddings = get_embeddings()
    add_documents(project_id, document_id, chunks, embeddings, owner_id=owner_id)
