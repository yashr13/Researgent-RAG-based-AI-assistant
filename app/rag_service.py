import logging
import os
import re

from dotenv import load_dotenv
from langchain_community.chat_models import ChatOpenAI
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import openai_chat_model
from app.embeddings import get_embeddings
from app.vectorstore import get_project_documents, similarity_search

load_dotenv()
logger = logging.getLogger(__name__)


def _question_mode(question: str):
    lowered = question.lower()

    comparison_terms = (
        "compare",
        "contrast",
        "difference",
        "similarit",
        "versus",
        " vs ",
        "agree",
        "disagree",
    )
    extraction_terms = (
        "extract",
        "list",
        "table",
        "key findings",
        "action items",
        "risks",
        "methods",
        "entities",
        "limitations",
    )
    explanation_terms = (
        "summarize",
        "summary",
        "explain",
        "overview",
        "what is this document about",
        "main points",
    )

    if any(term in lowered for term in comparison_terms):
        return "compare"
    if any(term in lowered for term in extraction_terms):
        return "extract"
    if any(term in lowered for term in explanation_terms):
        return "explain"
    return "qa"


def _search_kwargs(mode: str):
    if mode == "compare":
        return {"k": 10, "fetch_k": 30}
    if mode in {"extract", "explain"}:
        return {"k": 8, "fetch_k": 24}
    return {"k": 6, "fetch_k": 20}


def _mode_instructions(mode: str):
    if mode == "compare":
        return (
            "The user is asking for a comparison across documents or sections. "
            "Organize the answer into shared points, differences, and notable gaps. "
            "If the retrieved context only covers one document, state that comparison evidence is limited."
        )
    if mode == "extract":
        return (
            "The user is asking for structured extraction. "
            "Return a concise, clearly labeled list using only fields supported by the context. "
            "If a requested field is not supported, say it is not stated in the documents."
        )
    if mode == "explain":
        return (
            "The user wants explanation or summary. "
            "Provide a concise structured explanation with clear headings or bullets. "
            "Focus on purpose, key ideas, important findings, and limitations that appear in the context."
        )
    return (
        "Answer the question directly and concisely. "
        "Ground each important claim in the provided context."
    )


def _build_excerpt(text: str):
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if len(cleaned) <= 220:
        return cleaned
    return f"{cleaned[:217]}..."


def _history_context(chat_history):
    if not chat_history:
        return ""

    lines = []
    for item in chat_history[-4:]:
        role = "User" if item.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {item.get('content', '').strip()}")
    return "\n".join(lines)


def _retrieval_query(question: str, chat_history):
    history = _history_context(chat_history)
    if not history:
        return question
    return f"Conversation context:\n{history}\n\nCurrent question: {question}"


def _doc_key(doc: Document):
    metadata = doc.metadata or {}
    return (
        metadata.get("document_id"),
        metadata.get("filename"),
        metadata.get("page"),
        metadata.get("section_title"),
        doc.page_content[:120],
    )


def _ranked_merge(primary_docs, secondary_docs, limit: int):
    scores = {}
    ordered = {}

    for rank, doc in enumerate(primary_docs):
        key = _doc_key(doc)
        scores[key] = scores.get(key, 0) + (1.5 / (rank + 1))
        ordered.setdefault(key, doc)

    for rank, doc in enumerate(secondary_docs):
        key = _doc_key(doc)
        scores[key] = scores.get(key, 0) + (1.0 / (rank + 1))
        ordered.setdefault(key, doc)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [ordered[key] for key, _ in ranked[:limit]]


def _lexical_search(project_id: str, retrieval_query: str, mode: str, embeddings, owner_id: str | None = None):
    documents = get_project_documents(project_id, embeddings, owner_id=owner_id)
    if not documents:
        return []

    try:
        bm25 = BM25Retriever.from_documents(documents)
    except ImportError:
        logger.warning("rank_bm25 is not installed; falling back to dense retrieval only.")
        return []

    bm25.k = _search_kwargs(mode)["fetch_k"]
    try:
        return bm25.invoke(retrieval_query)
    except AttributeError:
        return bm25.get_relevant_documents(retrieval_query)


def _retrieve_documents(project_id: str, question: str, mode: str, chat_history, embeddings, owner_id: str | None = None):
    retrieval_query = _retrieval_query(question, chat_history or [])
    settings = _search_kwargs(mode)
    dense_docs = similarity_search(project_id, retrieval_query, settings["fetch_k"], embeddings, owner_id=owner_id)
    lexical_docs = _lexical_search(project_id, retrieval_query, mode, embeddings, owner_id=owner_id)
    return _ranked_merge(dense_docs, lexical_docs, settings["k"])


def _context_block(source_documents):
    blocks = []
    for index, doc in enumerate(source_documents, start=1):
        metadata = doc.metadata or {}
        context_lines = [f"[Chunk {index}]"]
        if metadata.get("filename"):
            context_lines.append(f"Document: {metadata['filename']}")
        if metadata.get("section_title"):
            context_lines.append(f"Section: {metadata['section_title']}")
        if metadata.get("page") is not None:
            context_lines.append(f"Page: {metadata['page']}")
        context_lines.append(doc.page_content)
        blocks.append("\n".join(context_lines))
    return "\n\n".join(blocks)


def query_rag(project_id: str, question: str, chat_history=None, owner_id: str | None = None):
    embeddings = get_embeddings()
    mode = _question_mode(question)
    source_documents = _retrieve_documents(project_id, question, mode, chat_history, embeddings, owner_id=owner_id)

    if not source_documents:
        return {
            "answer": "I could not find relevant material in this project's indexed documents.",
            "sources": [],
        }

    llm = ChatOpenAI(model=openai_chat_model(), temperature=0)
    system_prompt = (
        "You are a helpful assistant for question answering over a private document set.\n"
        "The retrieved context may span multiple documents and named sections.\n"
        "Use ONLY the provided context. If the answer is not in the context, say the question is beyond the document context.\n"
        f"{_mode_instructions(mode)}\n"
        "Do not mention source filenames, page numbers, or section names in the answer body.\n"
        "Keep all citation details for the separate sources panel.\n"
        "Answer clearly, with concise reasoning grounded in the context."
    )
    human_prompt = (
        f"Context:\n{_context_block(source_documents)}\n\n"
        f"Question: {question}\n"
        "Answer:"
    )

    result = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ]
    )
    answer = getattr(result, "content", "") or ""

    sources = []
    for doc in source_documents:
        meta = doc.metadata or {}
        source_path = meta.get("source") or ""
        source_name = meta.get("filename")
        if not source_name:
            source_name = os.path.basename(source_path) if source_path else "unknown"
        page = meta.get("page")
        section_title = meta.get("section_title")
        sources.append(
            {
                "source": source_name,
                "page": page,
                "section_title": section_title,
                "excerpt": _build_excerpt(doc.page_content),
            }
        )

    return {"answer": answer, "sources": sources}
