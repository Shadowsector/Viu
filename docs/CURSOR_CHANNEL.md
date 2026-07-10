# Канал Viu → Cursor (GitHub)

Когда Ден просит Вью «выложить мысли для Cursor» — это **work**, не болтовня.

## Как работает

1. Вью вызывает **`cursor_handoff_with_logs`** (или `cursor_handoff` + `cursor_push`).
2. Текст попадает в **`docs/CURSOR_HANDOFF.md`** в репозитории Viu.
3. При наличии **`VIU_GITHUB_TOKEN`** — commit + push на текущую ветку.
4. Cloud Agent Cursor в GitHub читает handoff и может продолжить код/дизайн.

## Настройка push

В `U:\Viu\.env`:

```env
VIU_GITHUB_TOKEN=ghp_xxxxxxxx
VIU_GITHUB_REPO=Shadowsector/Viu
```

Токен: GitHub → Settings → Developer settings → Personal access tokens (repo scope).

## Триггеры из Telegram

Срабатывает **work** (инструменты), не reflect:

- «Попробуешь?» / «начни» / «выложи на GitHub»
- «канал с Cursor» / handoff
- «следующий шаг» / «сделай …»

Вопросы про сюжет («как ты видишь панель задач?») — **reflect**, без Unity.
