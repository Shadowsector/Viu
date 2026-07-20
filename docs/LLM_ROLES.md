# Модели Ollama для Вью (роли)

Вью **уже умеет** подставлять разные модели **на каждый запрос**  
(`VIU_MODEL_REFLECT` / `WORK` / `CODE`). Это не «4×70B в VRAM сразу» —  
Ollama **выгружает одну и грузит другую**. Ночью над сюжетом = reflect;  
днём «следующий шаг» = work. Пауза при смене — норма.

## Рекомендуемый набор (NSFW + VRAM)

| Роль | Тег | Зачем |
|------|-----|--------|
| **Reflect** — чат / NSFW | `viu-cydonia` | Живой ERP (~14 GB) |
| **Reflect** — сюжет / GDD | `viu-command-r` | **Модель чата** — вторая строка сверху или меню **Чат** |
| **Reflect** — литературный | `viu-magnum` | Сцены |
| **Work** | `viu-qwen32` | JSON / lab |
| **Code** | `qwen2.5-coder:14b` | Код (без NSFW-обёртки) |
| **Vision** | `llava` | Глаза + `creature_describe` |

70B / 72B (Abliterated, Dolphin, Qwen 72B, старые Euryale/Nevoria) — не держим  
в повседневном наборе: жрут VRAM и дублируют 24–32B.

### Чистка + сборка обёрток

```bat
cd /d U:\Viu
scripts\cleanup_ollama_models.bat
scripts\abort_heavy_ollama.bat
scripts\create_viu_ollama_models.bat
```

Баннер create должен показывать:
`Set: slim-cydonia-magnum32-commandr-qwen32`  
Если в tip всё ещё `viu-euryale` — файлы Viu **устарели**, не продолжай.

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

VIU_LLM_TIMEOUT=1200
VIU_REFLECT_TEMPERATURE=0.88
VIU_OLLAMA_KEEP_ALIVE=5m
VIU_OLLAMA_NUM_CTX=16384
VIU_OLLAMA_NUM_PREDICT=4096
```

Длинные ответы (GDD, квесты): `VIU_OLLAMA_NUM_PREDICT=4096` — иначе JSON/final обрывается.  
Выбор reflect без правки `.env`: выпадающий список **Чат:** вверху окна (пишет в `.viu/runtime.json`).

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

Промпт reflect — только **голос Вью** (~15 строк). Разрешения 18+ — в Ollama Modelfile;
пайплайн и граф — в заметках (`VIU_SELF`, `build_reflect_notes`), не в system.  
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
