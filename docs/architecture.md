# Архитектура решения

## 1. Архитектурные принципы

1. **Fail safely.** Система не обязана автоматически отвечать на каждый запрос.
2. **PII first.** Маскирование выполняется до retrieval, LLM и технического аудита.
3. **Deterministic orchestration.** Бизнес-переходы задаются кодом, а не автономным агентом.
4. **LLM is not a policy engine.** Модель генерирует текст, но не разрешает себе автоответ.
5. **Grounded generation.** Ответ строится только по retrieved context.
6. **Graceful degradation.** Отказ LLM не означает отказ всей системы.
7. **Auditable decisions.** Маршрут и причины решения сохраняются.
8. **Human-in-the-loop.** Рискованные и сомнительные случаи передаются оператору.

## 2. Контекст системы

```mermaid
flowchart LR
    U[Пользователь] --> UI[Streamlit PoC]
    UI --> P[Support Pipeline]
    P --> VS[Vector Store]
    P --> LLM[OpenRouter]
    P --> AS[Audit Storage]
    P --> OP[Оператор / simulated handoff]
    UI --> U
```

## 3. Компоненты

### Streamlit UI

Отвечает только за:

- ввод сообщения;
- отображение истории;
- demo mode;
- decision trace;
- обратную связь «Помогло / Не помогло».

UI не должен содержать бизнес-логику маршрутизации.

### Pydantic schemas

Фиксируют контракты:

- `TicketInput`;
- `PrivacyResult`;
- `ScopeResult`;
- `RiskResult`;
- `RetrievalResult`;
- `LLMAnswer`;
- `ValidationResult`;
- `DecisionRecord`.

`extra="forbid"` снижает риск тихого принятия неожиданной структуры.

### PII service

Обнаруживает и заменяет email, телефон, карту, IP, OTP и токен. Возвращает только обезличенный текст и метаданные о типах PII.

### Scope gate

Определяет `IN_SCOPE`, `OUT_OF_SCOPE` или `UNCERTAIN`.

Явно нерелевантный запрос завершается системным ответом без LLM и оператора.

### Risk service

Использует интерпретируемые правила. High-risk запросы не передаются во внешний LLM.

### Knowledge retriever

Ищет релевантные статьи базы знаний и возвращает top-k, top1 score, top2 score, margin и document metadata.

### Template retriever

Используется как fallback при технической недоступности LLM или retrieval.

Шаблон разрешается только при выполнении policy:

- высокий score;
- достаточный margin;
- `auto_reply_allowed=true`;
- `risk=low`;
- `is_active=true`.

### LLM client

Получает redacted ticket, retrieved chunks и разрешённые document IDs.

Ожидаемый ответ:

```json
{
  "answer": "Текст ответа",
  "citations": ["kb_document_id"],
  "needs_operator": false
}
```

### Answer validator

Проверяет:

- Pydantic schema;
- citations;
- отсутствие PII;
- отсутствие запроса секретов;
- отсутствие обещаний выполненных действий;
- `needs_operator`;
- длину и непустой ответ.

### Audit repository

Primary: SQLite.

Backup: append-only JSONL.

Raw пользовательский текст не сохраняется.

## 4. Основной pipeline

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Streamlit
    participant P as Pipeline
    participant S as Scope/Risk
    participant V as Vector Store
    participant L as LLM
    participant A as Audit

    U->>UI: Ticket
    UI->>P: TicketInput
    P->>P: PII masking
    P->>S: redacted_text

    alt Out of scope
        S-->>P: OUT_OF_SCOPE
        P->>A: Save decision
        P-->>UI: Scope response
    else High risk
        S-->>P: HIGH
        P->>A: Save escalation
        P-->>UI: Operator handoff
    else Safe
        P->>V: Retrieve KB
        V-->>P: chunks + scores
        P->>L: redacted_text + context
        L-->>P: structured answer
        P->>P: Validate answer
        P->>A: Save decision
        P-->>UI: Answer
    end
```

## 5. Fallback-логика

```mermaid
flowchart TD
    A[Safe in-scope ticket] --> B[KB retrieval]

    B -->|Ошибка / нет контекста| T[Template search]
    B -->|Контекст найден| C[LLM attempt 1]

    C -->|Timeout / 429 / 5xx| T
    C -->|Ответ получен| D[Validation]

    D -->|Valid| E[Auto reply]
    D -->|Invalid| F[Corrective attempt 2]

    F -->|Valid| E
    F -->|Invalid| G[Operator review]

    T -->|Reliable template| H[Template response]
    T -->|Low score / ambiguous| G

    E --> I[Primary audit]
    H --> I
    G --> I

    I -->|Failure| J[Backup JSONL]
    J -->|Failure and auto response| G
```

## 6. Corrective retry

Corrective retry выполняется только если LLM технически ответила, но результат не прошёл валидацию.

Второй запрос содержит:

- тот же redacted ticket;
- тот же контекст;
- список ошибок;
- разрешённые citations;
- `temperature=0`.

Количество попыток ограничено двумя.

При техническом outage corrective retry не выполняется — система сразу переходит к шаблонному fallback.

## 7. Аудит

### Что сохраняется

- event ID;
- ticket ID;
- action;
- response source;
- scope;
- risk;
- PII types;
- retrieved document IDs;
- scores;
- LLM attempts и latency;
- fallback reason;
- degradation events;
- audit storage;
- processing latency;
- redacted text, если это разрешено политикой.

### Что не сохраняется

- raw text;
- API key;
- placeholder mapping;
- полный prompt;
- raw LLM response;
- секреты пользователя.

## 8. Состояния тикета

```text
NEW
→ VALIDATED
→ REDACTED
→ SCOPED
→ TRIAGED
→ RETRIEVED
→ GENERATED / TEMPLATE_SELECTED
→ VALIDATED_RESPONSE
→ AUDITED
→ ANSWERED
→ RESOLVED / ESCALATED
```

Для PoC состояния могут быть представлены через итоговый `DecisionRecord`, без полноценной workflow БД.

## 9. Производительность

### PoC

- локальный последовательный pipeline;
- Streamlit;
- Chroma;
- SQLite;
- один пользовательский процесс.

### Целевая архитектура

```mermaid
flowchart LR
    CH[Channels] --> GW[API Gateway]
    GW --> Q[Ticket Queue]
    Q --> FP[Fast Path Workers]
    FP --> POL[Scope / Risk / Policy]
    POL -->|Escalate| OQ[Operator Queue]
    POL -->|Safe| RQ[Generation Queue]
    RQ --> RW[RAG / LLM Workers]
    RW --> OG[Output Guardrails]
    OG --> ES[Event Store]
    ES --> CRM[Support Platform]
```

Fast path должен включать дешёвые операции:

- validation;
- PII preprocessing;
- scope/risk;
- routing.

## 10. Production evolution

До production необходимы:

- managed vector DB или поисковый сервис;
- versioned KB;
- PostgreSQL и durable queue;
- централизованная DLP/NER;
- provider allowlist и Zero Data Retention;
- rate limiting;
- circuit breaker;
- полноценный operator handoff;
- нагрузочное и security-тестирование;
- аудит качества на исторических данных.
