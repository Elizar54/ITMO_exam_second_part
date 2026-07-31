"""ChromaDB collection setup and idempotent data loading."""

from __future__ import annotations

import json
import hashlib
import math
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from src.config import Settings, settings


KNOWLEDGE_COLLECTION = "support_knowledge_base"
TEMPLATE_COLLECTION = "support_templates"
SCOPE_COLLECTION = "support_service_scope"
CHROMA_DISTANCE_SPACE = "cosine"
CHROMA_COLLECTION_METADATA = {"hnsw:space": CHROMA_DISTANCE_SPACE}


class MultilingualSentenceTransformerEmbeddingFunction:
    """Lazy sentence-transformer embedding function for Chroma."""

    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        fallback_dimensions: int = 384,
    ) -> None:
        self.model_name = model_name
        self.fallback_dimensions = fallback_dimensions
        self._model: Any | None = None
        self._use_fallback = False

    def name(self) -> str:
        return f"sentence-transformers/{self.model_name}"

    def __call__(self, input: Sequence[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_query(self, input: Sequence[str]) -> list[list[float]]:
        return self._embed(input)

    def embed_documents(self, input: Sequence[str]) -> list[list[float]]:
        return self._embed(input)

    def _embed(self, input: Sequence[str]) -> list[list[float]]:
        if self._use_fallback:
            return self._hash_embeddings(input)

        if self._model is None:
            try:
                import torch  # noqa: F401
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
            except Exception:
                self._use_fallback = True
                return self._hash_embeddings(input)
        embeddings = self._model.encode(list(input), normalize_embeddings=True)
        return embeddings.tolist()

    def _hash_embeddings(self, input: Sequence[str]) -> list[list[float]]:
        return [self._hash_embedding(text) for text in input]

    def _hash_embedding(self, text: str) -> list[float]:
        vector = [0.0] * self.fallback_dimensions
        tokens = re.findall(r"[a-zа-яё0-9]+", text.lower())
        features = [*tokens]
        features.extend(
            f"{tokens[index]}_{tokens[index + 1]}"
            for index in range(len(tokens) - 1)
        )
        if not features:
            return vector

        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.fallback_dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def create_persistent_client(config: Settings = settings) -> Any:
    import chromadb

    config.chroma_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.chroma_path))


def get_or_create_collections(
    client: Any,
    embedding_function: Any | None = None,
) -> dict[str, Any]:
    embedding_function = embedding_function or MultilingualSentenceTransformerEmbeddingFunction()
    return {
        KNOWLEDGE_COLLECTION: client.get_or_create_collection(
            name=KNOWLEDGE_COLLECTION,
            embedding_function=embedding_function,
            metadata=CHROMA_COLLECTION_METADATA,
        ),
        TEMPLATE_COLLECTION: client.get_or_create_collection(
            name=TEMPLATE_COLLECTION,
            embedding_function=embedding_function,
            metadata=CHROMA_COLLECTION_METADATA,
        ),
        SCOPE_COLLECTION: client.get_or_create_collection(
            name=SCOPE_COLLECTION,
            embedding_function=embedding_function,
            metadata=CHROMA_COLLECTION_METADATA,
        ),
    }


def cosine_distance_to_similarity(distance: float) -> float:
    """Convert Chroma cosine distance to a bounded similarity score.

    Chroma returns cosine distance for collections created with
    metadata={"hnsw:space": "cosine"}. For that space, distance is 0 for
    identical vectors and grows as vectors diverge, so 1 - distance is the
    natural similarity scale used by retrieval thresholds.
    """

    return max(0.0, min(1.0, 1.0 - distance))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def populate_all(
    client: Any,
    data_dir: Path = Path("data"),
    embedding_function: Any | None = None,
) -> dict[str, Any]:
    collections = get_or_create_collections(client, embedding_function)
    populate_knowledge_base(collections[KNOWLEDGE_COLLECTION], data_dir / "knowledge_base.json")
    populate_templates(collections[TEMPLATE_COLLECTION], data_dir / "response_templates.json")
    populate_scope(collections[SCOPE_COLLECTION], data_dir / "service_scope.json")
    return collections


def populate_knowledge_base(collection: Any, path: Path) -> None:
    records = load_json(path)
    upsert_records(
        collection=collection,
        ids=[record["document_id"] for record in records],
        documents=[f"{record['title']}. {record['text']}" for record in records],
        metadatas=[
            {
                "document_id": record["document_id"],
                "title": record["title"],
                "topic": record["topic"],
                "auto_reply_allowed": record["auto_reply_allowed"],
                "version": record["version"],
                "is_active": record["is_active"],
            }
            for record in records
        ],
    )


def populate_templates(collection: Any, path: Path) -> None:
    records = load_json(path)
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    for record in records:
        for index, example in enumerate(record["examples"], start=1):
            ids.append(f"{record['template_id']}::example-{index}")
            documents.append(example)
            metadatas.append(
                {
                    "template_id": record["template_id"],
                    "title": record["title"],
                    "answer": record["answer"],
                    "auto_reply_allowed": record["auto_reply_allowed"],
                    "risk": record["risk"],
                    "is_active": record["is_active"],
                }
            )
    upsert_records(collection, ids, documents, metadatas)


def populate_scope(collection: Any, path: Path) -> None:
    records = load_json(path)
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    for label in ("positive", "negative"):
        key = f"{label}_examples"
        for index, example in enumerate(records[key], start=1):
            ids.append(f"scope::{label}::{index}")
            documents.append(example)
            metadatas.append({"label": label, "is_active": True})
    upsert_records(collection, ids, documents, metadatas)


def upsert_records(
    collection: Any,
    ids: Sequence[str],
    documents: Sequence[str],
    metadatas: Sequence[dict[str, Any]],
) -> None:
    if not ids:
        return
    collection.upsert(ids=list(ids), documents=list(documents), metadatas=list(metadatas))


def iter_query_rows(result: dict[str, Any]) -> Iterable[tuple[str, str, dict[str, Any], float]]:
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    for row_id, document, metadata, distance in zip(ids, documents, metadatas, distances, strict=False):
        yield row_id, document, metadata or {}, float(distance)
