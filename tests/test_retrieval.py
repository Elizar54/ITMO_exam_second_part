from src.config import Settings
from src.retrieval import KnowledgeRetriever


class FakeCollection:
    def __init__(self, rows):
        self.rows = rows

    def query(self, query_texts, n_results, include):
        query = query_texts[0].lower()
        scored = []
        for row in self.rows:
            keywords = row["keywords"]
            matches = sum(1 for keyword in keywords if keyword in query)
            distance = 1.0 - min(1.0, matches / max(1, len(keywords)))
            scored.append((distance, row))
        scored.sort(key=lambda item: item[0])
        selected = scored[:n_results]
        return {
            "ids": [[row["id"] for _, row in selected]],
            "documents": [[row["document"] for _, row in selected]],
            "metadatas": [[row["metadata"] for _, row in selected]],
            "distances": [[distance for distance, _ in selected]],
        }


def test_password_question_finds_relevant_article() -> None:
    retriever = KnowledgeRetriever(
        FakeCollection(
            [
                {
                    "id": "kb-password-reset",
                    "document": "Восстановление пароля",
                    "metadata": {"document_id": "kb-password-reset", "title": "Пароль", "is_active": True},
                    "keywords": ["восстановить", "пароль"],
                },
                {
                    "id": "kb-weather",
                    "document": "Погода",
                    "metadata": {"document_id": "kb-weather", "title": "Погода", "is_active": True},
                    "keywords": ["погода"],
                },
            ]
        ),
        Settings(retrieval_score_threshold=0.5, retrieval_margin_threshold=0.1),
    )

    result = retriever.search("Не могу восстановить пароль")

    assert result.chunks
    assert result.chunks[0].chunk_id == "kb-password-reset"


def test_irrelevant_query_has_low_retrieval_score() -> None:
    retriever = KnowledgeRetriever(
        FakeCollection(
            [
                {
                    "id": "kb-password-reset",
                    "document": "Восстановление пароля",
                    "metadata": {"document_id": "kb-password-reset", "title": "Пароль", "is_active": True},
                    "keywords": ["восстановить", "пароль"],
                }
            ]
        ),
        Settings(retrieval_score_threshold=0.5, retrieval_margin_threshold=0.0),
    )

    result = retriever.search("Какая завтра погода")

    assert result.chunks == []
    assert result.top_score == 0.0


def test_inactive_document_is_not_relevant() -> None:
    retriever = KnowledgeRetriever(
        FakeCollection(
            [
                {
                    "id": "kb-old-login-flow",
                    "document": "Старый вход",
                    "metadata": {"document_id": "kb-old-login-flow", "title": "Вход", "is_active": False},
                    "keywords": ["вход"],
                }
            ]
        ),
        Settings(retrieval_score_threshold=0.5, retrieval_margin_threshold=0.0),
    )

    result = retriever.search("Проблема со входом")

    assert result.chunks == []


def test_low_kb_score_does_not_mean_out_of_scope() -> None:
    result = KnowledgeRetriever(
        FakeCollection([]),
        Settings(retrieval_score_threshold=0.5, retrieval_margin_threshold=0.0),
    ).search("у меня ничего не работает")

    assert result.chunks == []
    assert result.unavailable is False
