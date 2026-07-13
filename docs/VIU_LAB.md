# Лаборатория Вью (Lab v1 + v2)

Два режима в одном окне:

| Режим | Кто | Что делает |
|-------|-----|------------|
| **Оператор** | Кнопки GUI | Экспорт, оверлей, inbox — скрипты, без «характера» |
| **Лаборатория** | Фон + чат | Cascadeur, web, journal, скрины, оценки |

## Cascadeur — headless?

**Нет.** У Cascadeur нет API/headless. Lab:

1. Запускает `Cascadeur.exe` (если закрыт)
2. Переносит окно на **3-й монитор** (`VIU_LAB_MONITOR=2`, нумерация с 0)
3. Сканирует **Lab Models Inbox**, проверяет кости в Blender
4. Кладёт **случайную** модель (FBX) в `Library/Cascadeur/Inbox`
5. Опционально **кликает** в окно Cascadeur (фокус UI)
6. Делает **скрин окна** → `lab/cascadeur/artifacts/`
7. Пишет **journal.md** и просит **оценку** (в away — кратко в **Telegram**)

## Папка входящих моделей

Можно класть **.blend / .fbx** в любую из папок:

```
U:\Anabarra\Library\Cascadeur\Inbox\     ← Den клал сюда; lab конвертирует .blend → .fbx
U:\Anabarra\Library\Lab\Models\Inbox\    ← rig-check + сводка models_summary.md
```

На шаге **Inbox (4/8)**: если в Cascadeur Inbox уже `.blend` — экспорт FBX **на месте** через Blender (`--factory-startup`, без DAZ/Viu Bridge — окно не «мигает» с аддонами).
Нужен `VIU_BLENDER_EXE` (Steam-Blender ищется автоматически).

Новые файлы в inbox после начала сессии → **авто reset** с шага 1.
**Обновление Viu** (другой git SHA / версия) → **авто reset** с шага 1 — не нужно вручную `reset=1`.
Продолжение с середины: кнопка «Лаборатория» без новых файлов и без обновления. С нуля: `lab_start reset=1`.

Сводка:

```
.viu/lab/cascadeur/artifacts/models_summary.md
.viu/lab/cascadeur/artifacts/models_summary.json
```

Колонка **Каскадёр**: good (≥70) / maybe / poor — по совместимости скелета с Humanoid.

## Пайплайн (9 шагов)

1. Статус (Inbox/Export/exe)
2. **Скан моделей + rig-check**
3. Web-исследование (docs, export FBX) — DDG API + HTML fallback + cascadeur.com
4. **Случайная модель** → Cascadeur Inbox
5. Запуск + монитор
6. **Import FBX** — команда `Viu.Lab Import` (Python) + `pending_import.json`
7. **Фокус мышью** — только в **away** и только Windows; курсор сразу возвращается на место
8. **Скрин UI** — HWND по PID `cascadeur.exe` (не по заголовку «Cascadeur») + **vision** (Ollama VL): WELCOME / MODEL_OK / EMPTY_SCENE
9. Отчёт → **awaiting_rating** (+ Telegram в away)

**Inbox / launch / import / capture** — при ошибке шаг **не сдвигается**. После **2 неудач** на одном шаге следующий клик «Лаборатория» — не слепой повтор, а **RECOVER**: `cascadeur_status`, список окон, web, vision по последнему PNG, запись в journal + Telegram (away). При 4× — auto-reset с шага 1; при capture без окна — откат к шагу «Запуск».

### Весь цикл одной кнопкой

- GUI: **«Лаборатория: Cascadeur»** и **«Lab: весь цикл»** — оба с `run_all=1` (полный цикл до отчёта или затыка)
- Чат: `lab_start run_all=1` / `lab_run_all`
- В away lab по таймеру гоняет **весь оставшийся цикл**, не по одному шагу.

Прерывание: кнопки **экспорт/оверлей/…** (не lab) или **«Обновить Вью»** → `paused`.

## Автономный режим + Telegram

«Меня нет» → lab делает **весь цикл** (или продолжение) каждые `VIU_LAB_INTERVAL_MIN` минут.

Вью **решает сама**; спрашивает Дена только при **затыке** (шаг не прошёл) или в **итоговом отчёте**.
При затыке — кратко в Telegram + вопрос в **очередь решений**.

После каждого шага — **краткий** отчёт в бот (`🧪 Lab — шаг N`) только в away.
После итерации — «итерация готова», Ден удалённо смотрит и ставит оценку на ПК.

Нужны: `VIU_TELEGRAM_TOKEN`, chat привязан через `/start`.

## Оценки (1–5)

| Критерий | id |
|----------|-----|
| Техника | `technique` |
| Изобретательность | `creativity` |
| Старание | `effort` |
| Полезность | `usefulness` |
| Ясность отчёта | `clarity` |

GUI: **«Оценить лабораторию»** или инструмент `lab_rate`.

## Файлы

```
U:\Viu\.viu\lab\cascadeur\
  TASK.md       ← задание (не трогать без причины)
  session.json  ← шаг, статус, артефакты
  journal.md    ← ход мыслей
  artifacts\    ← PNG, models_summary.*
```

## Настройки

```env
VIU_LAB_VRAM_GB=6
VIU_LAB_MONITOR=2
VIU_LAB_INTERVAL_MIN=5
VIU_LAB_MOUSE=1
VIU_LAB_MOUSE_AWAY_ONLY=1
VIU_LAB_MODELS_INBOX=U:\Anabarra\Library\Lab\Models\Inbox
VIU_CASCADEUR_EXE=U:\Cascadeur\App\Cascadeur\cascadeur.exe
VIU_CASCADEUR_SCRIPTS=   # опционально: папка user-команд (Commands)
```

`OLLAMA_MAX_VRAM` подсказывается при lab-шагах с web/LLM.

## Мышь — не отбирает

Lab **не захватывает** курсор (нет hook, нет блокировки ввода).

- Шаг «мышь» **только в режиме «меня нет»** (`VIU_LAB_MOUSE_AWAY_ONLY=1` по умолчанию).
- Пока ты **дома** — lab вообще не трогает мышь.
- В away: один клик в центр Cascadeur → **сразу** курсор возвращается туда, где был.
- На `awaiting_rating` lab idle — мышь полностью твоя.

**Vision не нужен** для этого шага: координаты берутся из окна (`GetWindowRect`), не из LLM и не из скрина. «Умные» клики по кнопкам UI — позже, с vision-моделью по запросу.

Отключить совсем: `VIU_LAB_MOUSE=0`.

## LLM для лаборатории

| Задача | Модель |
|--------|--------|
| Кнопки / пайплайн | **без LLM** (скрипты) |
| Web-конспект, rig-summary текст | **gpt-4o-mini** или **gpt-4o** (OpenAI в GUI) |
| Локально при лимите VRAM | **qwen2.5:14b** / **llama3.1:8b** (Ollama) |
| Vision по скринам Cascadeur | **llava** / **qwen2-vl** (Ollama) — шаг 8, recover |

Не грузить тяжёлую local + Cascadeur + Unity одновременно на 6 GB VRAM.

## Кнопки / инструменты

- **Лаборатория: Cascadeur** — `lab_start run_all=1` (полный цикл; после обновления Viu — с шага 1)
- **Lab: весь цикл** — то же + опционально `reset=1`
- **Оценить лабораторию** — форма оценок
- `lab_step`, `lab_status`, `lab_rate` — для чата/агента

## Отложено: NSFW / фанфик-референсы

Идея: читать **18+ fantasy** как учебник **сюжетных приёмов** (не пересказ), конспект в `lab/literature/`.

**Статус: записано, не включено.** Нужен явный флаг `VIU_LAB_NSFW_RESEARCH=1` и локальная папка `References/literature/` — реализуем отдельно, когда Ден скажет.

## Связанные документы

- [CASCADEUR.md](./CASCADEUR.md) — пути Inbox/Export
- [EYES.md](./EYES.md) — скрины окон
- [VIU_HEARTBEAT.md](./VIU_HEARTBEAT.md) — heartbeat ≠ lab
