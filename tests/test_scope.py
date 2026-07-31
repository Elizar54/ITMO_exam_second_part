from src.config import Settings
from src.schemas import ScopeStatus
from src.scope import ScopeGate


class FakeScopeCollection:
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


def scope_gate() -> ScopeGate:
    rows = [
        {
            "id": "positive-login",
            "document": "не могу войти",
            "metadata": {"label": "positive", "is_active": True},
            "keywords": ["войти", "аккаунт"],
        },
        {
            "id": "negative-weather",
            "document": "какая погода",
            "metadata": {"label": "negative", "is_active": True},
            "keywords": ["погода"],
        },
        {
            "id": "negative-math",
            "document": "реши пример",
            "metadata": {"label": "negative", "is_active": True},
            "keywords": ["реши", "пример"],
        },
    ]
    return ScopeGate(
        FakeScopeCollection(rows),
        Settings(
            scope_positive_threshold=0.6,
            scope_negative_threshold=0.6,
            scope_margin_threshold=0.1,
        ),
    )


def test_weather_question_is_out_of_scope() -> None:
    assert scope_gate().classify("Какая погода завтра?").status == ScopeStatus.OUT_OF_SCOPE


def test_math_question_is_out_of_scope() -> None:
    assert scope_gate().classify("Реши пример 2 плюс 2").status == ScopeStatus.OUT_OF_SCOPE


def test_login_question_is_in_scope() -> None:
    assert scope_gate().classify("Не могу войти в аккаунт").status == ScopeStatus.IN_SCOPE


def test_broad_failure_can_be_uncertain() -> None:
    assert scope_gate().classify("У меня ничего не работает").status == ScopeStatus.UNCERTAIN
