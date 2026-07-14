# ComfyUI во Вью

Вью **сама** ставит Comfy в `U:\Viu\ComfyUI`, качает Wan-workflows с GitHub и T2V-модели с HuggingFace.

Пайплайн: [COMFY_CASCADEUR_PIPELINE.md](./COMFY_CASCADEUR_PIPELINE.md).

---

## Что сделать Дена

Ничего. Если Lab пишет «ComfyUI не найден» — нажми снова **«Лаборатория: Comfy MoCap»** или в чате:

```
comfy_install
```

Вью:
1. Сканирует `U:\Viu` и типичные пути
2. `git clone` ComfyUI → `U:\Viu\ComfyUI`
3. `pip install -r requirements.txt` (venv)
4. Скачивает официальные Wan JSON (UI→API конвертит сама)
5. Качает T2V 1.3B + VAE + umt5 (~9 GB)

Потом снова lab — промпт уйдёт в Telegram.

---

## Модель

**Wan 2.1** T2V `wan2.1_t2v_1.3B_fp16.safetensors`  
I2V 14B — опционально: `comfy_install i2v=1` (десятки GB).

---

## Инструменты

| Tool | Что |
|------|-----|
| `comfy_install` | clone + workflows + модели |
| `comfy_ensure` | install при необходимости + старт `:8188` |
| `comfy_status` | диагностика |
| `comfy_mocap` | lab: Telegram → 3 ракурса |

---

## Env

| Ключ | Default |
|------|---------|
| `VIU_COMFY_URL` | `http://127.0.0.1:8188` |
| `VIU_COMFY_ROOT` | `U:/Viu/ComfyUI` |

Нужны: `git`, интернет, место на `U:` (~10+ GB для T2V).

Если `U:\Viu\ComfyUI` уже занята чем-то без `main.py`, Вью сама прячет содержимое
в `U:\Viu\ComfyUI_stash_<время>`, клонирует Comfy туда и возвращает папку `models` обратно.
