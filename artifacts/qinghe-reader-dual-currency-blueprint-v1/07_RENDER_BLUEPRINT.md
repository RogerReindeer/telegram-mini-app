# 7. Render Blueprint

## 7.1. Рекомендуемая организация

Оставить два независимых репозитория и два Blueprint:

- Qinghe Blueprint управляет `qinghe-api` и `qinghe-frontend`;
- Reader Blueprint управляет `telegram-mini-app`;
- Supabase читалки остаётся внешним managed-сервисом;
- Qinghe PostgreSQL остаётся текущей базой Qinghe.

Не требуется объединять приложения в один репозиторий или одну базу.

## 7.2. Новые env Qinghe

```text
TELEGRAM_BOT_TOKEN                 secret
TELEGRAM_STARS_ENABLED=true
READER_API_URL                     public config
READER_COMMERCE_SHARED_SECRET      secret
READER_MINIAPP_RETURN_URL          public config
GRANT_WORKER_ENABLED=true
GRANT_MAX_ATTEMPTS=0
PAYMENTS_TRIBUTE_CURRENCY_ENABLED=false
```

`GRANT_MAX_ATTEMPTS=0` означает не терять событие автоматически. После длительных ошибок оно переходит в manual review, но остаётся в БД.

## 7.3. Новые env читалки

```text
QINGHE_API_URL                     public config
QINGHE_MINIAPP_LAUNCH_URL          public config
QINGHE_COMMERCE_SHARED_SECRET      secret
COMMERCE_ENABLED=false             feature flag
READER_COIN_MAX_SINGLE_GRANT=10000
STORE_ENABLED=false                feature flag
```

Секреты задаются через `sync: false` или `generateValue`, но один общий HMAC secret нельзя независимо генерировать в двух сервисах: его значение нужно безопасно задать одинаковым вручную.

## 7.4. Feature flags

Первый deploy выполняется с отключённым UI:

```text
COMMERCE_ENABLED=false
STORE_ENABLED=false
```

После миграций, smoke-тестов и проверки internal grant:

```text
COMMERCE_ENABLED=true
STORE_ENABLED=false
```

Это включает только покупку валютных пакетов и отображение Монеток. Магазин контента включается отдельным шагом после проверки access rules.

