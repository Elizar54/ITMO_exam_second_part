from src.config import Settings
from src.templates import TemplateRetriever


class FakeTemplateCollection:
    def __init__(self, rows):
        self.rows = rows

    def query(self, query_texts, n_results, include):
        query = query_texts[0].lower()
        scored = []
        for row in self.rows:
            matches = sum(1 for keyword in row["keywords"] if keyword in query)
            distance = 1.0 - min(1.0, matches / max(1, len(row["keywords"])))
            scored.append((distance, row))
        scored.sort(key=lambda item: item[0])
        selected = scored[:n_results]
        return {
            "ids": [[row["id"] for _, row in selected]],
            "documents": [[row["document"] for _, row in selected]],
            "metadatas": [[row["metadata"] for _, row in selected]],
            "distances": [[distance for distance, _ in selected]],
        }


def test_password_template_found_by_close_example() -> None:
    retriever = TemplateRetriever(
        FakeTemplateCollection(
            [
                {
                    "id": "tpl-password-reset::1",
                    "document": "забыл пароль",
                    "metadata": {
                        "template_id": "tpl-password-reset",
                        "title": "Пароль",
                        "answer": "Сбросьте пароль.",
                        "auto_reply_allowed": True,
                        "risk": "low",
                        "is_active": True,
                    },
                    "keywords": ["забыл", "пароль"],
                }
            ]
        ),
        Settings(template_score_threshold=0.5, template_margin_threshold=0.0),
    )

    match = retriever.search("Я забыл пароль")

    assert match is not None
    assert match.template_id == "tpl-password-reset"
    assert match.is_allowed


def test_low_template_score_does_not_allow_template_response() -> None:
    retriever = TemplateRetriever(
        FakeTemplateCollection(
            [
                {
                    "id": "tpl-password-reset::1",
                    "document": "забыл пароль",
                    "metadata": {
                        "template_id": "tpl-password-reset",
                        "title": "Пароль",
                        "answer": "Сбросьте пароль.",
                        "auto_reply_allowed": True,
                        "risk": "low",
                        "is_active": True,
                    },
                    "keywords": ["забыл", "пароль"],
                }
            ]
        ),
        Settings(template_score_threshold=0.8, template_margin_threshold=0.0),
    )

    match = retriever.search("Какая погода")

    assert match is not None
    assert match.score < 0.8


def test_login_lock_template_found_by_close_example() -> None:
    retriever = TemplateRetriever(
        FakeTemplateCollection(
            [
                {
                    "id": "tpl-login-temporary-lock::1",
                    "document": "блокировка входа",
                    "metadata": {
                        "template_id": "tpl-login-temporary-lock",
                        "title": "Временная блокировка входа",
                        "answer": "Подождите 15 минут и попробуйте снова.",
                        "auto_reply_allowed": True,
                        "risk": "low",
                        "is_active": True,
                    },
                    "keywords": ["блокировка", "входа"],
                }
            ]
        ),
        Settings(template_score_threshold=0.5, template_margin_threshold=0.0),
    )

    match = retriever.search("У меня блокировка входа")

    assert match is not None
    assert match.template_id == "tpl-login-temporary-lock"
    assert match.is_allowed
