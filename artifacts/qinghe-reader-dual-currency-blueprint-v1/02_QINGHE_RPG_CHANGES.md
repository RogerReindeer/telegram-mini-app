# 2. Изменения Qinghe RPG

## 2.1. Backend

Добавить модуль `commerce`:

```text
backend/src/commerce/catalog.ts
backend/src/commerce/checkoutService.ts
backend/src/commerce/paymentService.ts
backend/src/commerce/walletService.ts
backend/src/commerce/grantDeliveryService.ts
backend/src/routes/commerce.ts
backend/src/routes/paymentWebhook.ts
backend/src/workers/grantOutboxWorker.ts
```

Названия ориентировочные и могут быть адаптированы к существующей структуре.

### Обязательные функции

- получить каталог активных валютных пакетов;
- создать checkout, привязанный к Telegram user ID;
- получить состояние checkout;
- создать Telegram Stars invoice;
- обработать `pre_checkout_query` не позднее допустимого Telegram времени;
- обработать `successful_payment`;
- сохранить `telegram_payment_charge_id`;
- начислить Платину ровно один раз;
- поставить начисление Монеток в outbox;
- повторять доставку с backoff;
- показать историю покупок и состояние доставки.

## 2.2. Идентификация пользователя

- доверять только Telegram `initData`, проверенному сервером;
- не принимать `telegram_user_id` из тела клиентского запроса как доказательство личности;
- checkout, открытый по `startapp`, окончательно связывать с пользователем только после Telegram-auth;
- не помещать user ID, цену или секрет в `startapp`.

## 2.3. Платиновый кошелёк

Баланс изменяется только через ledger-service. Запрещено выполнять произвольный `UPDATE balance = ...` из route.

Каждое изменение содержит:

- `amount` со знаком;
- тип операции;
- `purchase_id` или игровой reference;
- уникальный `idempotency_key`;
- баланс после операции;
- дату и metadata.

Списание должно блокировать строку кошелька через `SELECT ... FOR UPDATE` и запрещать отрицательный баланс.

## 2.4. Двойное начисление

После успешной оплаты:

```text
commerce_purchases.status = paid
currency_ledger: +platinum_grant
purchase_grants.platinum_status = completed
purchase_grants.reader_coins_status = pending
commerce_outbox: reader.coin_grant
```

Если читалка недоступна, покупка остаётся успешной, а доставка Монеток повторяется. Пользователю показывается `Монетки начисляются` вместо общей ошибки платежа.

## 2.5. Frontend

Добавить:

- экран `Магазин валюты`;
- карточки пакетов 100/200/500/1000;
- текущий баланс Платины;
- подпись `Также вы получите N Монеток в читалке`;
- состояния `готово`, `оплата`, `начисление`, `частично доставлено`, `завершено`;
- кнопку возврата в читалку;
- историю последних покупок;
- ссылку на поддержку по платежам.

Клиент не рассчитывает цену и количество награды самостоятельно. UI отображает значения, полученные из API.

## 2.6. Админка Qinghe

Добавить раздел `Commerce`:

- каталог пакетов и активности;
- поиск покупки по `purchase_id`, charge ID и Telegram user ID;
- статусы обоих начислений;
- ручной безопасный retry доставки Монеток;
- просмотр ledger без возможности редактировать записи;
- refund/reversal как отдельная операция, а не удаление;
- аудит административных действий.

