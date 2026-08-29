# 6. Безопасность и надёжность

## 6.1. Запрещённые решения

- общий изменяемый баланс для двух приложений;
- передача service key Supabase в Qinghe frontend/backend;
- доверие user ID из клиентского JSON;
- цена и размер начисления из браузера;
- начисление по redirect после оплаты;
- удаление ledger при отмене;
- секрет в URL или `startapp`;
- прямая запись Qinghe в Supabase таблицы читалки;
- постоянный retry ошибок подписи.

## 6.2. Idempotency

Уникальными должны быть:

- provider + payment reference;
- purchase ID;
- event ID доставки;
- ledger idempotency key;
- reader purchase `client_action_id`.

Повторный валидный запрос возвращает прежний результат с `duplicate=true`.

Если тот же `purchase_id` приходит с другим user, amount или product, возвращается `409 purchase_conflict` и создаётся security event.

## 6.3. Outbox

Начисление Платины и создание outbox-события выполняются в одной PostgreSQL-транзакции. Это предотвращает состояние `Платина начислена, но задача Монеток потеряна`.

Worker забирает события через безопасную блокировку, например `FOR UPDATE SKIP LOCKED`, отправляет их и обновляет статус.

## 6.4. Логи

Разрешено логировать:

- purchase ID;
- event ID;
- provider;
- product code;
- status;
- номер попытки;
- request ID.

Запрещено логировать:

- bot token;
- service shared secret;
- Telegram initData целиком;
- полную платёжную подпись;
- Supabase service key;
- пользовательские cookies.

## 6.5. Ограничения

- body internal endpoint: до 16 KiB;
- clock skew подписи: до 5 минут;
- nonce TTL: минимум 10 минут;
- лимит одного начисления задаётся конфигурацией;
- rate limit отдельно для checkout и internal grant;
- таймаут server-to-server запроса: 5–10 секунд;
- соединение только HTTPS.

## 6.6. Мониторинг

Метрики:

- успешные/ошибочные платежи;
- начисления Платины;
- начисления Монеток;
- pending delivery старше 5/30/120 минут;
- повторные webhook;
- signature failure;
- purchase conflict;
- ledger invariant failure;
- средняя задержка двойного начисления.

Blocker production-gate:

- нет shared secret;
- не настроен Stars provider;
- миграции не применены;
- internal endpoint не проходит probe;
- баланс может стать отрицательным;
- нет уникальных idempotency constraints.

