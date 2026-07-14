# ComfyUI во Вью

Локальный сервер ComfyUI → инструменты `comfy_status` / `comfy_run` → файлы в `Lab/Refs` для Cascadeur MoCap.

Полный пайплайн: [COMFY_CASCADEUR_PIPELINE.md](./COMFY_CASCADEUR_PIPELINE.md).

---

## Быстрый старт

1. Установи ComfyUI (клон репо или portable) так, чтобы был `main.py`.
2. Запусти: `python main.py --listen` (по умолчанию `http://127.0.0.1:8188`).
3. В UI: собери workflow → **Save (API Format)** → положи JSON как:
   - `U:\Viu\.viu\comfy\workflows\default.json`
4. Во Вью: `comfy_status`, затем `comfy_run` с `prompt=…`.

---

## Переменные окружения / config

| Ключ | Значение |
|------|----------|
| `VIU_COMFY_URL` / `comfy_url` | `http://127.0.0.1:8188` |
| `VIU_COMFY_ROOT` / `comfy_root` | каталог с `main.py` (иначе автопоиск `U:\ComfyUI` и т.п.) |
| `VIU_COMFY_REFS` | опционально: куда копировать готовые mp4/png |
| `VIU_COMFY_OUT` | опционально: сырой выход |

По умолчанию:

```
U:\Anabarra\Library\Lab\Refs\       ← для Cascadeur
U:\Anabarra\Library\Lab\ComfyOut\   ← копия с /view
U:\Viu\.viu\comfy\workflows\        ← API JSON
```

---

## Инструменты

- **`comfy_status`** — ping `:8188`, пути, список workflow.
- **`comfy_run`** — `prompt=`, `workflow=default`, `slug=имя`, `timeout=600`.  
  Подставляет текст в первый `CLIPTextEncode`, ждёт history, качает outputs → Refs.

Пока **нет** готового video-workflow в репо — нужен твой `default.json` (txt2img / i2v / t2v).  
Имена на потом: `i2v.json`, `t2v.json`.

---

## VRAM

На одной карте не гоняй Comfy + Cascadeur + Unity одновременно — lab-очередь по очереди.
