# ComfyUI во Вью

Вью **сама** ставит Comfy в `U:\Viu\ComfyUI`, качает Wan-workflows с GitHub и T2V-модели с HuggingFace.

Пайплайн: [COMFY_CASCADEUR_PIPELINE.md](./COMFY_CASCADEUR_PIPELINE.md).

---

## Окно Comfy

У ComfyUI **нет** отдельного desktop-приложения.

1. **Браузер** `http://127.0.0.1:8188` — UI (пустой Unsaved Workflow — норма: MoCap через API).
2. **Лог** `.viu/logs/comfy_launch.log` — прогресс Wan / ошибки старта (не чёрное пустое окно).
3. Браузер после ensure: `VIU_COMFY_OPEN_BROWSER=1` (выкл = `0`).
4. Отдельная консоль (опционально): `VIU_COMFY_SHOW_CONSOLE=1` — иначе по умолчанию выкл: `CREATE_NEW_CONSOLE` из pythonw давал пустое чёрное окно.

В диспетчере задач процесс есть, а «не вкалывает» — часто очередь пустая или чат раньше рвал job (`Global interrupt`). Сейчас чат по умолчанию **не** убивает генерацию; жёсткий yield: `VIU_COMFY_YIELD_INTERRUPT=1`.

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

### Из cmd (не из чата Вью)

`comfy_install` — **инструмент Вью**, не отдельная программа. Из `U:\Viu\`:

```bat
comfy_install.bat reactor=1 models=0
comfy_ensure.bat
```

Только ReActor (без скачивания Wan-моделей, быстрее):

```bat
python -m viu tool comfy_install --args "{\"reactor\":\"1\",\"models\":\"0\"}"
```

Или полная установка + ReActor:

```bat
python -m viu tool comfy_install --args "{\"reactor\":\"1\"}"
python -m viu tool comfy_ensure
```

В cmd сразу должны появляться строки `[comfy_install] …` — установка долгая (git, pip).
Если «моргает и тишина» — обнови Viu до свежей версии или используй `comfy_install.bat`.

В окне Вью в чате тоже можно: `comfy_install reactor=1`.

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

Если браузер пишет **403 на 127.0.0.1** — обнови Вью и перезапусти Comfy (`comfy_ensure`):
запуск теперь с `--listen 127.0.0.1` и CORS. Либо открой `http://localhost:8188`.
Для MoCap UI не обязателен — Вью ходит в API сама.

### Шоу-дубль (SmoothMix / cinematic)

Отдельный профиль — **1 красивый клип**, не MoCap-ref для Cascadeur.

**GUI:** «Девушки → Шоу-дубль… / Съёмка видео» — одна панель (цель, режим, длина, чекпоинт, эталон ★, LoRA, промпт) → **Снять**.  
В чате: **«шоу дубль»** / `comfy_show` · аниме: **«шоу аниме»**.

Промпт — **тот же канон**, что у MoCap (не `young woman` / длинный negative):

```text
positive: a fit girl with a big fake breast and perfect body is [процесс + антураж]
          + smoothmixrealism|smoothmixanime + cinematic style bits
negative: Tongue out, wet hair
```

Отдельного блока Action нет. Длина ролика задаётся в панели (сек → кадры).

1. Положи **SmoothMix Wan 2.2** (`.safetensors` / `.gguf`) в  
   `U:\Viu\ComfyUI\models\diffusion_models\`  
   (имя с `smoothmix` — Вью подхватит сама; или выбери чекпоинт в панели).
2. Или задай явно: `VIU_COMFY_SHOW_UNET=имя_файла.safetensors` в `.env`.
3. Если модели нет — шоу всё равно идёт на **Wan 2.1** с cinematic-промптом  
   (896×576, длина из панели, euler/simple, steps=8).

Режимы: **T2V** (текст→видео), **I2V** (эталон→видео). T2I/I2I — в UI уже есть; графы картинок подключим отдельно (пока fallback на video).

MoCap снова: цель MoCap в панели / `comfy_mocap`.

### Подмена лица (ReActor)

Чтобы Wan не рисовал случайные лица:

1. **Папка** `U:\Anabarra\Library\Lab\FaceRefs\` (Места → «Лица MoCap»).  
   Не `U:\Viu\Library\` — склад игры в **Anabarra\Library**.
2. Положи **PNG/JPG** с одним чётким лицом (фронт или ¾).
   - `default.png` — всегда это лицо;
   - или несколько файлов — **случайный** на каждый batch (одинаковый на 3 дубля).
3. Один раз: `comfy_install.bat reactor=1` (ReActor + inswapper).
4. `comfy_ensure` — перезапуск Comfy, чтобы подхватить ноду.

Выключить: `VIU_COMFY_FACE_SWAP=0` в `.env`.  
Фиксированное лицо: `VIU_COMFY_FACE_REF=U:\path\to\face.png`.

**Битые mp4 ~4–5 KB (не открываются):** встроенный NSFW-filter ReActor вырезает
NSFW-кадры → остаётся один чёрный кадр. Вью патчит `reactor_sfw.py` при
`comfy_install reactor=1` / `comfy_reactor_fix`. После патча — `comfy_ensure restart=1`
и переснять. Временно без лица: `VIU_COMFY_FACE_SWAP=0`.

### Llava — оценка клипов (до Telegram)

После тройки дублей Вью (если `VIU_COMFY_VISION=1` и `ollama pull llava`):

1. **Первый и последний** кадр из каждого mp4 (ловит чёрный старт/финиш)
2. Llava → `VERDICT: OK | BLACK_FRAME | …`
3. Плохие — в `Lab/Refs/rejected/`, в Telegram только нормальные

Ручная проверка: `comfy_vision_review path=U:\...\clip.mp4 action=touch_self`

**Референсы:** `vision_reference path=U:\...\ref.png` или `path=clip.mp4 frame=last` —
EN_POSE / EN_LOOK / RU для промпта. Цепочка анимаций: last-frame seed уже в `keep_clip`
(`comfy_seed_frames/`); i2v — опционально позже.


### LoRA — простой сценарий

1. **Скачай** `.safetensors` в `ComfyUI/models/loras/` (можно подпапки).
2. **Индекс:** `comfy_lora_scan` или `comfy_lora_list scan=1` — Вью нумерует файлы.
3. **Перед каждым пулом** (после одобрения промпта) Вью спросит в Telegram/чате:
   - `lora: 1` / `lora: 1,3` / `lora: all` / `lora: none`
4. **Заметки к файлу** (trigger, strength): `comfy_lora_note lora_file=foo.safetensors trigger=...`
5. **Away:** без LoRA или повтор последнего выбора (`lora_last_pick`).

Опционально: `comfy_lora_bind` / `download_url` — если всё же хочешь автоподкачку по URL.

### Что искать на Civitai / HF (теги)

База модели: **Wan 2.1**, **wan2.1**, **wan t2v**, **wan i2v**, **video lora**, **motion lora**.

По действиям (примеры):
- `touch_self` / интим: `self touch`, `masturbation`, `solo`, `nsfw motion`
- сидеть/лежать: `sit`, `lie down`, `sleep`, `get up`
- ходьба: `walk cycle`, `locomotion`, `stride`
- жесты: `wave`, `reach`, `pick up`, `drink`, `eat`

Фильтр: Type = LoRA, Base model содержит Wan / video. Смотри preview-GIF и trigger words в описании.
