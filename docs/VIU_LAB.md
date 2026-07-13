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

```
U:\Anabarra\Library\Lab\Models\Inbox\
  hero.blend
  npc.fbx
  README.txt
```

Или свой путь: `VIU_LAB_MODELS_INBOX=...`

Lab для каждого `.blend` запускает Blender headless (`dump_blend_info` + `rig_check`-логика),
для `.fbx` — помечает «maybe» без rig-check.

Сводка:

```
.viu/lab/cascadeur/artifacts/models_summary.md
.viu/lab/cascadeur/artifacts/models_summary.json
```

Колонка **Каскадёр**: good (≥70) / maybe / poor — по совместимости скелета с Humanoid.

## Пайплайн (8 шагов)

1. Статус (Inbox/Export/exe)
2. **Скан моделей + rig-check**
3. Web-исследование (docs, export FBX)
4. **Случайная модель** → Cascadeur Inbox
5. Запуск + монитор
6. **Фокус мышью** — только в **away** и только Windows; курсор сразу возвращается на место
7. Скрин UI
8. Отчёт → **awaiting_rating** (+ Telegram в away)

Прерывание: любая **кнопка GUI** или **«Обновить Вью»** → `paused`, journal сохранён.

## Автономный режим + Telegram

«Меня нет» → lab делает **+1 шаг** каждые `VIU_LAB_INTERVAL_MIN` минут.

После каждого шага — **краткий** отчёт в бот (`🧪 Lab — шаг N`).
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
VIU_CASCADEUR_EXE=C:\Program Files\Cascadeur\Cascadeur.exe
```

`OLLAMA_MAX_VRAM` подсказывается при lab-шагах с web/LLM.

## Мышь — не отбирает

Lab **не захватывает** курсор (нет hook, нет блокировки ввода).

- Шаг «мышь» **только в режиме «меня нет»** (`VIU_LAB_MOUSE_AWAY_ONLY=1` по умолчанию).
- Пока ты **дома** — lab вообще не трогает мышь.
- В away: один клик в центр Cascadeur → **сразу** курсор возвращается туда, где был.
- На `awaiting_rating` lab idle — мышь полностью твоя.

Отключить совсем: `VIU_LAB_MOUSE=0`.

## LLM для лаборатории

| Задача | Модель |
|--------|--------|
| Кнопки / пайплайн | **без LLM** (скрипты) |
| Web-конспект, rig-summary текст | **gpt-4o-mini** или **gpt-4o** (OpenAI в GUI) |
| Локально при лимите VRAM | **qwen2.5:14b** / **llama3.1:8b** (Ollama) |
| Vision по скринам | только по запросу; не параллельно с Cascadeur |

Не грузить тяжёлую local + Cascadeur + Unity одновременно на 6 GB VRAM.

## Кнопки / инструменты

- **Лаборатория: Cascadeur** — `lab_start` + первый шаг
- **Оценить лабораторию** — форма оценок
- `lab_step`, `lab_status`, `lab_rate` — для чата/агента

## Отложено: NSFW / фанфик-референсы

Идея: читать **18+ fantasy** как учебник **сюжетных приёмов** (не пересказ), конспект в `lab/literature/`.

**Статус: записано, не включено.** Нужен явный флаг `VIU_LAB_NSFW_RESEARCH=1` и локальная папка `References/literature/` — реализуем отдельно, когда Ден скажет.

## Связанные документы

- [CASCADEUR.md](./CASCADEUR.md) — пути Inbox/Export
- [EYES.md](./EYES.md) — скрины окон
- [VIU_HEARTBEAT.md](./VIU_HEARTBEAT.md) — heartbeat ≠ lab
