# Self Review

## 1. Что сделано

В PoC спроектирован безопасный сквозной pipeline обработки обращений:

- Pydantic-контракты;
- PII masking;
- scope gate;
- risk rules;
- retrieval по KB;
- LLM generation;
- output validation;
- corrective retry;
- template fallback;
- operator fallback;
- primary и backup audit;
- Streamlit decision trace;
- mock-сценарии и pytest.

Основной акцент сделан не на количестве кода, а на управляемых переходах и проверяемом поведении при отказах.

## 2. Ключевые архитектурные решения

### Убран классификатор typical / non-typical

Причина: отсутствует размеченный датасет. Искусственная модель на нескольких примерах не дала бы достоверного качества. 

### PII masking не равен operator fallback

Наличие email или телефона — обычная ситуация поддержки. Данные маскируются, после чего обработка может продолжаться.

### Risk policy находится вне LLM

LLM не решает, имеет ли право отправить ответ. Это определяет детерминированная policy.

### LLM outage деградирует на шаблоны

Это снижает зависимость от внешнего API и показывает, что LLM не является единственной точкой ответа.

### Невалидный ответ получает один retry

Одна ошибка формата не должна сразу создавать операторский тикет. При повторной ошибке система прекращает автоматизацию.

### Primary audit outage не блокирует ответ

Решение сохраняется в backup JSONL. Автоответ блокируется только при отказе всех audit storage.

### Out-of-scope не идёт оператору

Поддержка не должна тратить ресурсы на вопросы, не связанные с сервисом.

## 3. Что получилось хорошо

- Fallback представлен как часть архитектуры.
- Каждый критический маршрут можно покрыть unit-тестом.
- Компоненты разделены через dependency injection.
- Документация различает PoC и production design.
- Бизнес-оценка опирается на A/B-тест и реальные метрики.

## 4. Главные ограничения

### PII detection

Regex не обнаружит:

- имена;
- адреса;
- нестандартные номера документов;
- PII с опечатками;
- контекстно чувствительные данные.

До production нужна NER-система и/или security evaluation. 

### Risk detection

Keyword rules имеют ограниченный recall. Новая формулировка мошенничества может быть пропущена.

Нужны размеченные данные, high-recall модель, adversarial test set и выборочный аудит. Для этого можно использовать модель classic-ml, обученную на векторных представлениях текста. Это должно улучшить Recall. 

### Scope gate

Positive/negative examples искусственные, thresholds экспертные.

Нужна валидация на реальных out-of-scope и in-scope запросах. Нужна калибровка порогов на реальных размеченных датасетах.

### Retrieval

Маленькая KB не отражает реальный продукт. Similarity score зависит от embedding-модели. Вероятно будет полезно дообучить свою модель формирования эмбеддингов типа Frida и сравнить метрики типа Recall@K.

### Grounding

Citations снижают риск выдуманных источников, но не доказывают, что каждое утверждение строго следует из контекста.

Полезен независимый verifier или claim-level проверка.

### Audit storage

SQLite и JSONL подходят для PoC, но не для highload production.

Нужны highly available database и durable event stream.

### UI

Streamlit демонстрирует логику, но не является операторской системой и не покрывает права доступа.

### Business effect

CSAT, reopen rate и handling time не измерялись. Указанные значения являются гипотезами и критериями пилота, а не результатами.

## 5. Что улучшить за два дополнительных дня

Приоритет:

1. Проверить все end-to-end сценарии.
2. Расширить KB и шаблоны.
3. Добавить golden test set.
4. Подобрать retrieval thresholds.
5. Добавить Dockerfile.
6. Добавить простую нагрузочную проверку.
7. Провести security review prompt и logs.

## 6. Что необходимо до production

- реальные исторические данные;
- процесс обезличивания;
- разметка scope, risk и resolution;
- security и legal review;
- integration с CRM/helpdesk;
- operator suggest mode;
- production DLP;
- high-availability storage;
- queues и autoscaling;
- model/provider governance;
- monitoring и alerting;
- kill switch;
- canary rollout;
- incident response;
- A/B-пилот.

## 7. Какие категории нельзя полностью автоматизировать

- fraud и account takeover;
- спорные финансовые операции;
- юридические претензии;
- удаление данных;
- блокировки;
- идентификация пользователя;
- необратимые действия;
- запросы с недостаточным контекстом;
- случаи, где политика требует ручного решения.

## 8. Что заставит остановить проект

- подтверждённая утечка PII;
- опасный автоответ;
- систематический пропуск high-risk;
- ухудшение CSAT выше допустимой границы;
- существенный рост reopen rate;
- отсутствие экономии;
- нестабильная работа внешнего LLM;
- невозможность воспроизводить и аудировать решения.

## 9. Технический долг

- тесты на реальных embeddings;
- миграции audit DB;
- versioning schemas;
- structured error taxonomy;
- полноценный correlation ID;
- retries с circuit breaker;
- storage reconciliation;
- prompt versioning;
- model version recording;
- retention и access control.
