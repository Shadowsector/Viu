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

Потом снова lab. **Дома** — промпт уйдёт в Telegram; **Нет дома** (красный сверху) — Вью сама одобрит и снимет. Кадр выбирает режиссёр из каталога (не только idle).

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

### Torch / CUDA (RTX)

Если в логе `Torch not compiled with CUDA enabled` или `from versions: none` для cu124:

1. Обнови Вью (**«Обновить Вью»**), снова `comfy_ensure` (без `comfy_install`).
2. Вью смотрит версию Python в `ComfyUI\\venv`:
   - **3.10–3.13** → `torch` cu124 / cu121
   - **3.14+** (часто системный Python) → `torch==2.13.0+cu126` (fallback cu130)
3. Если Comfy уже крутится на CPU при наличии GPU — `comfy_ensure` сам остановит `:8188`, поставит CUDA torch и перезапустит.
4. Лог: `U:\Viu\.viu\logs\comfy_launch.log`.

Wan на CPU крайне медленный — нужен CUDA torch.
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

---

## ComfyUI глазами Дена

Обычный MoCap **не требует** смотреть в Comfy: Вью ставит в очередь, ждёт, кладёт в `Lab/Refs`.

Кнопка **«Открыть ComfyUI»** (Редко) → `http://127.0.0.1:8188` — когда нужно:
- понять, почему таймаут 900s (очередь / OOM / нода красная);
- вручную крутить workflow;
- подключить **LoRA** / эксперименты.

### LoRA / v2v — как вижу

1. **Сначала файлы:** LoRA в `ComfyUI/models/loras/`, v2v-ноды/модели — как обычно в Comfy.
2. **Потом Вью:** tool вроде `comfy_lora_list` / правка workflow JSON (имя LoRA + strength в T2V-граф) — без обязательного кликанья в UI.
3. **v2v / I2V:** уже задел — seed last-frame → следующий клип; полный v2v — отдельный workflow, когда появятся файлы и задача в каталоге.

Итого: UI Comfy — отладочный люк; пайплайн — через Вью. LoRA не «магия из воздуха»: сначала артефакт на диске, потом Вью вшивает в шаблон.
