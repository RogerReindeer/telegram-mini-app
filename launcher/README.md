# Startup launcher v247

Назначение: статический экран запуска находится на Render CDN и не засыпает вместе с Python Web Service. Он первым открывается в Telegram, будит backend через `/health`, ждёт реального ответа приложения и только затем переводит пользователя в `/library`.

Backend в текущей production-конфигурации:

```text
https://telegram-mini-app-fwq0.onrender.com
```

## Render Static Site

Создать отдельный Static Site из того же репозитория:

```text
Root Directory: launcher
Build Command: echo "launcher ready"
Publish Directory: .
```

Добавить Rewrite:

```text
Source: /*
Destination: /index.html
Action: Rewrite
```

После деплоя URL этого Static Site указать как URL Telegram Mini App вместо URL Python Web Service.

Python Web Service не удалять и его URL не менять.
