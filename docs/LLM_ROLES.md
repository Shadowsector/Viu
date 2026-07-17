# Модели Ollama для Вью (роли)

Вью **уже умеет** подставлять разные модели **на каждый запрос**  
(`VIU_MODEL_REFLECT` / `WORK` / `CODE`). Это не «4×70B в VRAM сразу» —  
Ollama **выгружает одну и грузит другую**. Ночью над сюжетом = reflect;  
днём «следующий шаг» = work. Пауза при смене — норма.

## Рекомендуемый набор (NSFW + VRAM)

| Роль | Тег | Зачем |
|------|-----|--------|
| **Reflect** — чат, сюжет, NSFW | `viu-cydonia` ← Cydonia 24B | Живой ERP/проза (~14 GB) |
| **Reflect** — литературный | `viu-magnum` ← Magnum 32B Q4 | Богатый язык сцен |
| **Reflect** — GDD / квесты | `viu-command-r` ← Command R | Длинный контекст, таблицы |
| **Work** — lab, JSON, механика | `viu-qwen32` ← Qwen 2.5 32B | Протокол агента |
| **Code** | `qwen2.5-coder:14b` | Код (**без** NSFW-обёртки) |
| **Vision** | `llava` | Только глаза (**не** заворачивать) |

70B / 72B (Abliterated, Dolphin, Qwen 72B, старые Euryale/Nevoria) — не держим  
в повседневном наборе: жрут VRAM и дублируют 24–32B.

### Чистка + сборка обёрток

```bat
cd /d U:\Viu
scripts\cleanup_ollama_models.bat
scripts\create_viu_ollama_models.bat
```

Или вручную:

```bat
ollama stop
ollama rm huihui_ai/llama3.3-abliterated:70b
ollama rm dolphin-llama3:70b
ollama rm viu-dolphin
ollama rm viu-abliterated
ollama rm qwen2.5:72b
ollama rm viu-euryale
ollama rm viu-nevoria
rem опционально старый Magnum 34B:
ollama rm fluffy/magnum-v3-34b:latest
ollama rm viu-magnum
scripts\create_viu_ollama_models.bat
```

Сироты `viu-*` после удаления базы остаются отдельными тегами —  
их надо `ollama rm` отдельно (или через cleanup bat).

### `.env` (практичный старт)

```env
VIU_PROVIDER=openai
VIU_BASE_URL=http://127.0.0.1:11434/v1
VIU_API_KEY=ollama

VIU_MODEL_REFLECT=viu-cydonia
VIU_MODEL_WORK=viu-qwen32
VIU_MODEL_CODE=qwen2.5-coder:14b
# GDD: VIU_MODEL_REFLECT=viu-command-r
# лит. NSFW: VIU_MODEL_REFLECT=viu-magnum

VIU_LLM_TIMEOUT=600
VIU_REFLECT_TEMPERATURE=0.88
VIU_OLLAMA_KEEP_ALIVE=5m
VIU_OLLAMA_NUM_CTX=16384
```

## Контекст (num_ctx)

| Кто задаёт | Действует на |
|------------|--------------|
| Ползунок в **окне Ollama** | Обычно только чат внутри Ollama UI |
| `PARAMETER num_ctx` в **Modelfile** (`viu-*`) | Дефолт при загрузке этой модели |
| **`VIU_OLLAMA_NUM_CTX`** в `.env` | Каждый запрос из Viu (перебивает дефолт) |

Больше контекст = больше VRAM. Для GDD / Command R — `16384` или `32768`.

## Command R vs Qwen 32B

| | Command R | Qwen 2.5 32B |
|--|-----------|--------------|
| Роль | Reflect / GDD | **Work** |
| Сильная сторона | таблицы, деревья, лор | JSON, механика, Unity |

Промпт «ведущий геймдизайнер NSFW» — в reflect-промптах Вью,  
не общий SYSTEM Ollama на все роли.

Перед сменой тяжёлых моделей: `ollama stop`.

## Почему Magnum спросил «вам есть 18?»

Не запрет Viu — модель разыграла age-check (часто из истории Ollama UI).  
Clean Modelfile + SYSTEM режут такие отыгрыши. Новый чат = чистый тест.

## Что сработает, что нет

| Идея | Вердикт |
|------|---------|
| Reflect = Cydonia, work = Qwen 32B, code = coder 14B | **Да** |
| NSFW-обёртка на llava | **Нет** — только vision |
| 70B/72B в повседневном наборе | **Нет** — снести |
| Смена модели на каждый тип запроса | **Да — уже в коде** |
| Command R для длинной канвы | Ок как reflect-эксперимент |
