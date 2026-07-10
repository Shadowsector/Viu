# Канал Viu → Cursor (GitHub)

Когда Ден просит Вью «выложить мысли для Cursor» — это **work**, не болтовня.

## Как работает

1. Вью вызывает **`cursor_handoff_with_logs`** (или `cursor_handoff` + `cursor_push`).
2. Текст попадает в **`docs/CURSOR_HANDOFF.md`** локально и на GitHub.
3. Push идёт через **GitHub API** — **локальный git не нужен** (zip-установка Viu без `.git` — норма).
4. Cloud Agent Cursor читает handoff в репозитории.

## Настройка push

После обновления Viu в **`U:\Viu`** появятся **`.env.example`** и (при первом запуске) **`.env`**.

1. Открой **`U:\Viu\.env`**
2. Вставь токен **без кавычек**:
   ```env
   VIU_GITHUB_TOKEN=ghp_xxxxxxxx
   ```
3. **Перезапусти Viu** (или просто повтори handoff — токен перечитается)

Токен: GitHub → Settings → Developer settings → Personal access tokens (scope: **repo**).

## Триггеры из Telegram

Срабатывает **work** (инструменты), не reflect:

- «Попробуешь?» / «начни» / «выложи на GitHub»
- «канал с Cursor» / handoff
- «следующий шаг» / «сделай …»

Вопросы про сюжет («как ты видишь панель задач?») — **reflect**, без Unity.
