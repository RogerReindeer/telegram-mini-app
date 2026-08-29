# 4. API-контракт между приложениями

## 4.1. Создание checkout

Пользовательский запрос к читалке:

```http
POST /api/store/qinghe-checkout
Content-Type: application/json
X-Telegram-Init-Data: <initData>

{
  "return_path": "/novel/example",
  "source": "reader_paywall"
}
```

Читалка сервер-сервер создаёт checkout в Qinghe и получает:

```json
{
  "checkout_id": "7da789b8-8915-4e49-a5ae-5f86ba305fde",
  "launch_url": "https://t.me/qinghe_bot/qinghe?startapp=checkout_abcd1234",
  "expires_at": "2026-08-29T13:00:00Z"
}
```

`launch_url` должен формировать Qinghe backend, а не браузер.

## 4.2. Начисление Монеток

```http
POST /api/internal/commerce/coin-grants
Content-Type: application/json
X-Service-Id: qinghe-api
X-Timestamp: 1788000000
X-Nonce: 3e69c06c-ecfc-47aa-9034-9b448ba25808
X-Signature: <hex-hmac-sha256>
```

```json
{
  "schema_version": 1,
  "event_id": "c46020a0-d3bb-40b0-88c3-1d641f5e0fc3",
  "purchase_id": "7da789b8-8915-4e49-a5ae-5f86ba305fde",
  "telegram_user_id": 123456789,
  "product_code": "currency_bundle_500",
  "amount": 500,
  "currency": "reader_coins",
  "provider": "telegram_stars",
  "occurred_at": "2026-08-29T12:10:00Z"
}
```

Успешный ответ:

```json
{
  "status": "completed",
  "event_id": "c46020a0-d3bb-40b0-88c3-1d641f5e0fc3",
  "purchase_id": "7da789b8-8915-4e49-a5ae-5f86ba305fde",
  "credited": 500,
  "balance": 730,
  "duplicate": false
}
```

Повторный запрос:

```json
{
  "status": "completed",
  "event_id": "c46020a0-d3bb-40b0-88c3-1d641f5e0fc3",
  "purchase_id": "7da789b8-8915-4e49-a5ae-5f86ba305fde",
  "credited": 0,
  "balance": 730,
  "duplicate": true
}
```

## 4.3. Подпись запроса

Строка подписи:

```text
<timestamp>.<nonce>.<sha256(raw_body)>
```

Подпись:

```text
hex(HMAC-SHA256(READER_COMMERCE_SHARED_SECRET, signing_string))
```

Читалка проверяет:

- service ID входит в allow-list;
- timestamp отличается не более чем на 5 минут;
- nonce ещё не использован;
- HMAC совпадает constant-time сравнением;
- `currency == reader_coins`;
- `amount` больше нуля и не превышает серверный лимит;
- product существует в allow-list пакетов;
- `event_id` и `purchase_id` имеют UUID-формат.

## 4.4. Коды ответов

| HTTP | Код | Значение |
|---:|---|---|
| 200 | `completed` | Начислено или уже было начислено |
| 400 | `invalid_payload` | Некорректные данные |
| 401 | `invalid_signature` | Подпись не прошла |
| 409 | `purchase_conflict` | Purchase уже связан с другими параметрами |
| 422 | `unsupported_product` | Неизвестный пакет |
| 429 | `rate_limited` | Превышен лимит |
| 500 | `temporary_error` | Можно повторить запрос |

Qinghe повторяет только временные ошибки: network, `429`, `5xx`. Ошибки `400/401/409/422` требуют ручной диагностики и не должны бесконечно ретраиться.

## 4.5. Retry policy

```text
30 секунд
2 минуты
10 минут
30 минут
2 часа
6 часов
далее каждые 12 часов до ручного решения
```

Каждая попытка записывается с временем и безопасным текстом ошибки без секретов.

