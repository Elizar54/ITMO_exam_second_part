# Риски и эксплуатация

## 1. Реестр основных рисков

| Риск | Последствие | Меры в PoC | Меры до production |
|---|---|---|---|
| PII не обнаружены | Утечка во внешний API | Regex masking, output scan | DLP/NER, policy engine, security review |
| Ложное high-risk решение | Лишняя нагрузка на операторов | Интерпретируемые rules | Размеченные данные, калибровка |
| Пропуск high-risk запроса | Небезопасный автоответ | Запрещённые категории, guardrails | High-recall classifier, manual audit |
| Галлюцинация LLM | Неверная инструкция | RAG, citations, output validation | Verifier, model evaluation |
| Prompt injection | Обход инструкций | LLM без tools, restricted prompt | Input firewall, red teaming |
| LLM outage | Нет генерации | Template fallback | Multi-provider routing, circuit breaker |
| Vector store outage | Нет retrieval | Template/operator fallback | Replication, cache |
| SQLite outage | Потеря аудита | Backup JSONL | PostgreSQL + durable event stream |
| Ошибка обоих audit storage | Неаудируемый автоответ | Блокировка автоответа | Highly available event storage |
| Неверный шаблон | Ошибочный детерминированный ответ | Score, margin, metadata | Versioning, approval workflow |
| Out-of-scope трафик | Лишняя стоимость | Scope gate | Anti-spam, rate limits |
| Drift | Падение качества | Score/fallback monitoring | Continuous evaluation |
| Массовый инцидент | Всплеск нагрузки | Документируется | Incident mode, broadcast response |
| Рост стоимости LLM | Экономика не сходится | Token tracking | Budget limits, model routing |

## 2. Privacy

### Data minimization

Во внешний LLM передаётся только:

- redacted ticket;
- минимально необходимый KB-контекст;
- document IDs;
- инструкции по формату.

Не передаются:

- raw PII;
- placeholder mapping;
- история вне текущего контекста без необходимости;
- API keys;
- внутренние логи.

