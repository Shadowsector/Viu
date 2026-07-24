# Глаза Вью — как перестать спрашивать Дена «посмотри»

## Принцип

**Не** тащить Unity в облако (дорого, GPU, лицензии, твои ассеты на U:).
**Да** — дать Вью глаза на твоём ПК:

1. `screen_capture` — PrintWindow скрин `AnabarraOverlay` / Unity
2. `vision_observe` — Ollama VL (`llava` / `qwen2-vl`), если стоит
3. Скрин + вердикт → gist + `CURSOR_HANDOFF` → Cursor чинит код
4. Дена зовут только на вкус/сюжет (`needs_decision`)

## Что поставить (один раз)

```bat
ollama pull llava
```

или `qwen2-vl:7b`. Без VL всё равно работает: скрин уходит Cursor в gist.

В `.env` можно: `VIU_VISION_MODEL=llava` (опционально, авто-поиск есть).

## Инструменты

| Tool | Делает |
|------|--------|
| `screen_capture` | PNG в `.viu/shots/` |
| `vision_observe` | скрин + VL + handoff |
| `vision_reference` | картинка или mp4 → EN/RU описание для Comfy/MoCap |
| `comfy_vision_review` | первый+последний кадр mp4 → вердикт качества |
| `overlay_playtest` | сборка → запуск → boot-лог → **eyes** → gist |

## Почему «оверлея не было»

Часто открывался только **Unity Editor / GameTest** (кнопка/задача `unity_open`).
Дом ставится только в **OverlayDesktop**. Eyes проверяют именно `AnabarraOverlay`.

## Облачный Unity — потом

Когда глаза и локальный цикл стабильны — можно думать про GPU-runner.
Сейчас это не разблокирует прогресс быстрее, чем скрин+Cursor.
