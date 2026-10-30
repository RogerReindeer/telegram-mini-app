# Startup launcher v248

Назначение: минимальный статический экран запуска находится на Render CDN и не засыпает вместе с Python Web Service. Он показывает только фон читалки и небольшой индикатор, будит backend через `/health`, ждёт реального ответа приложения и только затем возвращает пользователя в библиотеку, оглавление или главу.

После первого успешного запуска backend регистрирует узкий Service Worker. Он не кеширует API, кошелёк, покупки или страницы пользователя. Его единственная задача — при следующем долгом HTML-переходе/обновлении мгновенно показать этот же экран, пока Render просыпается.

Backend в текущей production-конфигурации:

```text
https://telegram-mini-app-fwq0.onrender.com
```

## Render Static Site

Статический сервис уже добавлен вторым сервисом в корневой `render.yaml`. При использовании Render Blueprint отдельная ручная настройка не требуется.

Для ручного создания Static Site используются параметры:

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

После деплоя URL `telegram-mini-app-launcher.onrender.com` (или фактически выданный Render URL) указать как URL Telegram Mini App вместо URL Python Web Service.

Python Web Service не удалять и его URL не менять.

Важно: если Telegram продолжает открывать `telegram-mini-app-fwq0.onrender.com` напрямую, первое холодное открытие всё равно будет показывать ожидание Render. Launcher начинает работать только после замены URL Mini App в BotFather/настройках бота.
