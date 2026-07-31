# Мониторинг и пилот

## 1. Цель мониторинга

Мониторинг должен отвечать на три вопроса:

1. Работает ли система технически?
2. Снижает ли она нагрузку и стоимость поддержки?
3. Не ухудшает ли она пользовательское качество и безопасность?

## 2. События

Каждое решение формирует структурированное событие:

```text
event_id
ticket_id
created_at
action
response_source
scope_status
risk_level
pii_detected
retrieval_top_score
retrieval_margin
llm_attempts
llm_latency_ms
processing_latency_ms
fallback_reason
degradation_events
audit_storage
```

Raw пользовательский текст и секреты не логируются.

## 3. Технические метрики

### Нагрузка

- tickets per minute;
- concurrent sessions;
- requests by channel;
- peak queue size;
- out-of-scope request rate.

### Latency

- p50/p95/p99 total processing latency;
- scope gate latency;
- risk rules latency;
- retrieval latency;
- LLM latency;
- audit write latency.

### Надёжность

- retrieval error rate;
- LLM timeout rate;
- LLM 429 rate;
- LLM 5xx rate;
- invalid first response rate;
- corrective retry success rate;
- template fallback rate;
- operator fallback rate;
- primary audit failure rate;
- backup audit failure rate.

### Стоимость

- prompt tokens;
- completion tokens;
- tokens per ticket;
- LLM requests per ticket;
- retry rate;
- estimated LLM cost per ticket.

Не следует придумывать стоимость, если pricing модели не задан.

## 4. Privacy и safety

- PII detected rate;
- PII redaction count;
- PII detected in LLM output;
- forbidden claim rate;
- unknown citation rate;
- auto-replies in high-risk categories;
- confirmed PII leakage incidents;
- unsafe response incidents.

Критические показатели:

```text
confirmed PII leakage incidents = 0
unsafe auto-replies = 0
auto-replies in forbidden categories = 0
```

## 5. Product metrics

### Primary

Для suggest-mode пилота:

```text
median operator handling time
```

Целевой эффект PoC-гипотезы: снижение минимум на 15%.

### Secondary

- time to first meaningful response;
- p90 first meaningful response;
- SLA breach rate;
- cost per handled ticket;
- operator draft acceptance rate;
- share of drafts accepted without changes;
- share accepted after editing;
- share rejected;
- successful automated resolution rate.

### Successful automated resolution

```text
тикеты, решённые без оператора
и не переоткрытые в течение 7 дней
/
все тикеты, разрешённые для автоматизации
```

## 6. Guardrails

### CSAT

Non-inferiority условие пилота:

```text
CSAT_test >= CSAT_control - 0.1
```

### Reopen rate

```text
reopen_test <= reopen_control + 1 п.п.
```

Повторное обращение по той же теме также желательно учитывать как скрытый reopen.

### Failed automation

```text
автоматический ответ с последующей эскалацией
/
все автоматические ответы
```

## 7. Почему не F1 online

Macro-F1, accuracy и recall требуют истинных меток.

Без разметчиков или операторской обратной связи online F1 будет либо отсутствовать, либо основываться на псевдоразметке самой системы, что не является независимой оценкой.

Допустимый подход:

- фиксированный небольшой golden set;
- выборочный ручной safety-аудит;
- бизнес-метрики пилота;
- операторские действия как слабые proxy-сигналы.

## 8. План запуска

### Этап 1: Shadow mode

AI принимает тикеты и формирует решения, но не влияет на пользователя.

Собираем:

- latency;
- score distributions;
- fallback reasons;
- стоимость;
- ручную оценку выборки;
- расхождения с действиями операторов.

### Этап 2: Suggest mode

A/B-тест:

- Control: оператор без AI;
- Treatment: оператор получает retrieval и draft.

Primary: handling time.

Guardrails: CSAT, reopen rate, safety.

### Этап 3: Safe auto-reply

Только согласованные категории:

- FAQ;
- восстановление доступа без признаков взлома;
- настройки;
- известные технические инструкции;
- статус сервиса.

Рискованные категории остаются у оператора.

## 9. Алерты

Примерные operational alerts, которые должны быть откалиброваны на пилоте:

- LLM timeout rate резко выше baseline;
- primary audit failure rate > 1%;
- backup audit failure > 0;
- high-risk auto-reply > 0;
- PII in output > 0;
- operator fallback rate резко вырос;
- scope uncertain rate резко вырос;
- p95 latency нарушает SLA внутреннего этапа.

## 10. Dashboard

Рекомендуемые блоки:

1. Volume and latency.
2. LLM health and cost.
3. Retrieval and fallback.
4. Privacy and safety.
5. Product experiment.
6. Audit storage health.
