import hashlib
import math
import os
import re

from fastapi import HTTPException
from langchain_community.embeddings import OpenAIEmbeddings

from app.config import embedding_dimensions, openai_embedding_model


class LocalHashEmbeddings:
    def __init__(self, dimensions: int | None = None):
        self.dimensions = dimensions or embedding_dimensions()

    def _tokenize(self, text: str):
        return re.findall(r"\w+", (text or "").lower())

    def _embed(self, text: str):
        vector = [0.0] * self.dimensions
        tokens = self._tokenize(text)

        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimensions
            sign = 1.0 if digest[8] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector

    def embed_documents(self, texts):
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        return self._embed(text)


def get_embeddings():
    provider = (os.getenv("EMBEDDINGS_PROVIDER") or "local").strip().lower()

    if provider == "openai":
        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="EMBEDDINGS_PROVIDER is set to 'openai' but OPENAI_API_KEY is not configured.",
            )
        return OpenAIEmbeddings(
            openai_api_key=api_key,
            model=openai_embedding_model(),
        )

    return LocalHashEmbeddings()
