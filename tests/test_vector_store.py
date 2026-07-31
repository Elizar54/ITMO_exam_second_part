from src.vector_store import (
    CHROMA_COLLECTION_METADATA,
    KNOWLEDGE_COLLECTION,
    SCOPE_COLLECTION,
    TEMPLATE_COLLECTION,
    cosine_distance_to_similarity,
    get_or_create_collections,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def get_or_create_collection(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs


def test_collections_use_cosine_distance_space() -> None:
    client = FakeClient()

    get_or_create_collections(client, embedding_function=object())

    assert {call["name"] for call in client.calls} == {
        KNOWLEDGE_COLLECTION,
        TEMPLATE_COLLECTION,
        SCOPE_COLLECTION,
    }
    assert all(call["metadata"] == CHROMA_COLLECTION_METADATA for call in client.calls)
    assert CHROMA_COLLECTION_METADATA == {"hnsw:space": "cosine"}


def test_cosine_distance_to_similarity_is_bounded() -> None:
    assert cosine_distance_to_similarity(0.0) == 1.0
    assert cosine_distance_to_similarity(0.25) == 0.75
    assert cosine_distance_to_similarity(1.5) == 0.0
