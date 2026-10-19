# Kvitto Payments API

[![checks](https://github.com/vladgenyuk/kvitto-payments-api/actions/workflows/ci.yml/badge.svg)](https://github.com/vladgenyuk/kvitto-payments-api/actions/workflows/ci.yml)

Тестовое Junior Python / FastAPI: тарифы, платежи, промокод, рассрочка и вебхук банка.
Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 / AsyncSession, SQLite и Alembic.

[PDF: скриншоты и результаты запросов](output/pdf/project-overview.pdf) ·
[Исходные скриншоты Swagger](docs/screenshots/)

## Запуск

Нужен Docker Engine с Compose. При использовании Colima на macOS: `colima start`.

```bash
docker compose up --build --wait --wait-timeout 90
```

API: <http://127.0.0.1:8000>, Swagger: <http://127.0.0.1:8000/docs>.
Миграции и три тарифа создаются автоматически. Healthcheck проверяет API и базу.
Контейнер работает от пользователя с UID 10001; порт доступен только локально.

```bash
docker compose logs --tail=100 api
docker compose stop
# На macOS с Colima выключить также виртуальную машину:
colima stop
```

База хранится в именованном томе `kvitto-data` и сохраняется после остановки и `down`.
Команда `docker compose down --volumes` удаляет данные.

## Тесты

Все проверки запускаются внутри отдельного контейнера, без локального Python:

```bash
docker compose --profile test run --build --rm test
```

Команда выполняет Ruff, проверку форматирования, pytest и coverage с порогом 95%.
Тесты используют временные базы; данные работающего API не затрагиваются.
Зависимости разработки находятся только в тестовом образе.

HTTP-проверка работающего API, включая HMAC при настроенном секрете:

```bash
docker compose exec -T api python scripts/smoke_test.py
```

Она создаёт один тестовый платёж и проводит его до возврата.
GitHub Actions запускает эти же проверки при push и pull request.

## Локальная разработка

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
uvicorn app.backend.main:app --reload
```

Для запуска без тестовых инструментов достаточно `requirements.txt`.

## Настройки

| Переменная | По умолчанию |
| --- | --- |
| `DATABASE_URL` | `sqlite+aiosqlite:///./kvitto.db` |
| `WEBHOOK_SECRET` | пустая строка, подпись отключена |

Пример конфигурации — `.env.example`. Compose читает `.env` для подстановки секрета;
локальный запуск читает переменные окружения. Compose использует базу `/data/kvitto.db`.
Поддерживается файловая SQLite; родительский каталог должен существовать.

```bash
WEBHOOK_SECRET='demo-secret' docker compose up --wait --wait-timeout 90
```

При включённой подписи `X-Signature` — 64 строчных hex-символа HMAC-SHA256
от исходных байтов тела с ключом `WEBHOOK_SECRET`. Сравнение — `compare_digest`.
Отсутствующая или неверная подпись возвращает 401. Без секрета вебхук принимает
обычные запросы из обязательных сценариев ТЗ.

## API

| Запрос | Ответ |
| --- | --- |
| `GET /tariffs` | 200, список тарифов |
| `POST /payments` | 201, новый платёж; 200, повтор по `Idempotency-Key` |
| `GET /payments/{id}` | 200, платёж; 404, отсутствует |
| `POST /webhooks/bank` | 200, успех; 404, отсутствует; 409, переход запрещён |
| `GET /payments?email=...&status=...` | 200, список с фильтрами |

Ошибки валидации — 422 с массивом `detail`. Полные схемы доступны в Swagger.

Примеры для сервера без `WEBHOOK_SECRET`:

```bash
curl -s http://127.0.0.1:8000/tariffs

curl -i http://127.0.0.1:8000/payments \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: course-order-001' \
  -d '{"tariff_id":2,"email":"student@example.com","method":"installment","installment_months":3,"promo_code":"kvitto10"}'
```

Сумма: `1791000`, скидка: `199000`, график: `[597000, 597000, 597000]`.
Повтор команды возвращает 200 с тем же платежом. В следующих запросах замените `1` на полученный `id`:

```bash
curl -s http://127.0.0.1:8000/payments/1

curl -i http://127.0.0.1:8000/webhooks/bank \
  -H 'Content-Type: application/json' \
  -d '{"payment_id":1,"status":"succeeded"}'
```

Успех: `200 {"result":"ok"}`. Запрещённый переход:
`409 {"error":"invalid_transition"}`, платёж не меняется.

## Правила и архитектура

- Тарифы: `basic` — `990000`, `standard` — `1990000`, `premium` — `2990000` копеек.
- Деньги в API и БД — целые копейки. `amount` — сумма после скидки.
- `KVITTO10` даёт 10% без учёта регистра; неизвестный или пустой код — 422.
- Рассрочка — 3, 6 или 12 месяцев. Остаток деления распределяется в первые платежи.
  Например, `1990000 / 3` → `[663334, 663333, 663333]`.
- Для `card` и `sbp` график и срок равны `null`; переданный срок — 422.
- Переходы: `pending → succeeded`, `pending → failed`, `succeeded → refunded`.
- `Idempotency-Key` — глобальный ключ длиной 1–200 символов, без TTL.
  Повтор с другим валидным телом возвращает первый платёж в его текущем статусе.
- ID — положительный int64. Строки, bool, дроби и переполнение в теле — 422.
  `created_at` — UTC. Фильтр email использует точное совпадение после нормализации.

ООП-структура адаптирована из [u-bro/Backend, ветка dev][reference].

| Слой | Ответственность |
| --- | --- |
| `app/backend` | `BackendApplication`, классы роутеров, зависимости и HTTP-ошибки |
| `app/services` | Сценарии, расчёты и commit транзакций |
| `app/crud` | SQL, чтение, вставка и условное обновление статуса |
| `app/models`, `app/schemas` | ORM-модели и схемы Pydantic |
| `app/db.py`, `migrations` | Сессии, миграции и начальные тарифы |

На запрос создаётся отдельная `AsyncSession`. UNIQUE защищает от дублей;
при коллизии сервис откатывает вставку и читает первый платёж. Смена статуса —
атомарный `UPDATE ... WHERE id = ... AND status = ...`. Успешный ответ выдаётся
после commit. При ошибке транзакция откатывается.

Запуск рассчитан на один процесс; при нескольких экземплярах миграции нужно
применять отдельным шагом. Список платежей не имеет пагинации.

```bash
docker compose exec -T api alembic current
docker compose exec -T api alembic check
```

## Работа с ИИ

Инструменты, ключевые запросы и исправленные ошибки — [AI_LOG.md](AI_LOG.md).

## Правила для ассистента

- Сохраняй API-контракт и ООП-слои; деньги считай только целыми копейками.
- Сохраняй UNIQUE ключа, атомарность статуса и commit до успешного ответа.
- Обновляй миграции при изменении схемы; используй временные базы в тестах.
- Перед завершением запускай тестовый профиль Compose и HTTP-проверку.
- Обновляй README и AI_LOG.md; указывай только реальные результаты.
- Публикация и внешние сообщения требуют явного запроса пользователя.

[reference]: https://github.com/u-bro/Backend/tree/827961604c728ecc598ae1460d075fae588eddf4/Backend-Bot-master/app/backend
