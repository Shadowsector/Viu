# Модели Ollama для Вью (роли)

Вью **уже умеет** подставлять разные модели **на каждый запрос**  
(`VIU_MODEL_REFLECT` / `WORK` / `CODE`). Это не «4×70B в VRAM сразу» —  
Ollama **выгружает одну и грузит другую**. Ночью над сюжетом = reflect;  
днём «следующий шаг» = work. Пауза при смене — норма.

## Рекомендуемый набор Дена (2026) — живые 24–32B

70B (Euryale/Nevoria/Dolphin/Abliterated) оставляй как «ночную пушку»,  
не как повседневный чат: при нехватке VRAM они пишут по букве.

| Роль | Тег Viu / Ollama | Зачем |
|------|------------------|--------|
| **Reflect** — чат, сюжет, NSFW, тепло | `viu-cydonia` ← Cydonia 24B | Живой ERP/проза, инициатива, мало морали |
| **Reflect (запас литературный)** | `viu-magnum` ← Magnum 34B | Богатый язык сцен (после clean SYSTEM) |
| **Work** — кнопки, lab, JSON, инструменты | `qwen2.5:32b-instruct` | Слушается протокол агента |
| **Code** — скрипты, баги, C# | `qwen2.5-coder:14b` (**у тебя уже была шустрой**) или `:32b` | Быстрый рабочий контур |
| **Vision** (глаза, не чат) | `qwen2.5-vl` / `llava` | Только картинки через eyes |

### Что скачать

```bat
ollama pull moophlo/Cydonia-24B-v4.3-GGUF:Q4_K_M
ollama pull qwen2.5:32b-instruct
ollama pull qwen2.5-coder:14b
rem опционально литературный запас:
rem ollama pull fluffy/magnum-v3-34b
rem ночная 70B — только когда нужна «пушка»:
rem ollama pull huihui_ai/llama3.3-abliterated:70b
```

Потом в корне Viu: `create_viu_ollama_models.bat` → появятся `viu-cydonia`, `viu-magnum`, …

### `.env` (практичный старт)

```env
VIU_PROVIDER=openai
VIU_BASE_URL=http://127.0.0.1:11434/v1
VIU_API_KEY=ollama

VIU_MODEL=qwen2.5:32b-instruct
VIU_MODEL_REFLECT=viu-cydonia
VIU_MODEL_WORK=qwen2.5:32b-instruct
VIU_MODEL_CODE=qwen2.5-coder:14b

VIU_LLM_TIMEOUT=600
VIU_REFLECT_TEMPERATURE=0.88
# выгрузить модель после ответа — меньше свопа при смене ролей
VIU_OLLAMA_KEEP_ALIVE=5m
# контекст запросов Viu (токены). UI Ollama на API обычно не действует.
VIU_OLLAMA_NUM_CTX=16384
```

## Контекст (num_ctx)

| Кто задаёт | Действует на |
|------------|--------------|
| Ползунок / настройка в **окне Ollama** | Обычно только чат внутри Ollama UI |
| `PARAMETER num_ctx` в **Modelfile** (`viu-*`) | Дефолт при загрузке этой модели |
| **`VIU_OLLAMA_NUM_CTX`** в `.env` | Каждый запрос из Viu (перебивает дефолт) |

В `viu-*` Modelfile сейчас **8192**. Через `.env` можно поднять без пересборки  
модели. Больше контекст = больше VRAM. Для длинного GDD / Command R —  
`16384` или `32768`, если память позволяет.

## Command R 35B vs Qwen 2.5 32B (геймдизайн)

| | Command R 35B | Qwen 2.5 32B Instruct |
|--|---------------|------------------------|
| Роль у Вью | Reflect / сценарий / GDD | **Work** (механика, баланс, JSON, код) |
| Контекст | до ~128k (нужен большой `VIU_OLLAMA_NUM_CTX`) | практично 8–32k |
| Сильная сторона | таблицы, деревья диалогов, помнить лор | интеллект, статы, Unity/C# |

Практично: **Cydonia (чат/NSFW) + Qwen 32B (work) + coder 14B**.  
Command R — отдельный эксперимент под «архитектор GDD»  
(`ollama pull command-r` + Modelfile `viu-command-r`).

Промпт «ведущий геймдизайнер NSFW» лучше в reflect-промптах Вью,  
а не общий SYSTEM Ollama на все роли — иначе work начнёт писать романы  
вместо JSON инструментов.

Ночью «думать над сюжетом» = просто чат/heartbeat на `VIU_MODEL_REFLECT`  
(Cydonia). Днём пайплайн = work/code. **Не** держи 70B загруженной,  
если параллельно крутишь 32B: перед сменой `ollama stop`.

## Почему Magnum спросил «вам есть 18?»

Это не запрет Viu — модель **разыграла** проверку возраста (часто из  
истории чата Ollama UI). В том же окне Ollama история общая для разных  
тегов → «уже знает, что 18». В Viu история своя; clean Modelfile +  
жёсткий SYSTEM режут такие отыгрыши. Новый чат в Ollama UI = чистый тест.

## Быстрая модель из прошлого

В `Viu.cmd` / docs уже стояла **`qwen2.5-coder:14b`** — она и была  
«шустрой llama/qwen» для работы. Для сюжета 14B слабовата; для кода — топ.

## Что сработает, что нет

| Идея | Вердикт |
|------|---------|
| Reflect = Cydonia, work = Qwen 32B, code = coder 14B | **Да — рекомендуем** |
| Смена модели на каждый тип запроса | **Да — уже в коде** |
| 4×70B одновременно в VRAM | **Нет** |
| Последовательно: ночь Cydonia → день Qwen | **Да** (Ollama unload/load) |
| Vision-модель вместо чата | **Нет** — только глаза |
| Command R 35B / Chrysalis | Ок как эксперимент; в базовый набор не обязательны |

## Старые 70B (оставить, не мучить каждый день)

| Тег | Когда |
|-----|--------|
| `viu-abliterated` | Ночной длинный NSFW без морали |
| `viu-euryale` / `viu-nevoria` | То же, вкусовщина |
| `viu-dolphin` | Запасной uncensored Llama3 |
