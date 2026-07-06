# Viu (Вью)

**Вью** — автономный самоулучшающийся агент и соавтор в разработке 3D-игры
«Анабарра». Это базовая архитектура ядра агента: цикл рассуждений (ReAct),
система инструментов, долгосрочная память, планировщик и модуль самоулучшения.

Техническое задание — в [`AGENT_CORE.md`](./AGENT_CORE.md).

## Возможности (реализовано в MVP)

- **Цикл рассуждений (ReAct)** — «рассуждение → действие → наблюдение»,
  провайдер-агностичный JSON-протокол.
- **Провайдеры LLM** — `mock` (офлайн, для тестов и демо) и `openai`
  (любой OpenAI-совместимый API: OpenAI, Ollama, LM Studio, vLLM, LocalAI).
- **Инструменты**:
  - файлы: `read_file`, `write_file`, `list_dir` (в песочнице каталога);
  - система: `run_shell` (управление локальным ПО);
  - интернет: `web_search`, `web_fetch`;
  - память: `memory_write`, `memory_search`;
  - планирование: `plan_create`, `plan_update`, `plan_show`;
  - **самоулучшение**: `self_inspect` (чтение своего кода), `add_tool`
    (создание новых инструментов на лету), `improve_prompt` (фиксация уроков);
  - **Blender**: `blender_info` (сведения о сцене/файле), `blender_command`
    (управление живым Blender), `blender_screenshot` (снимок для vision-модели) —
    см. [`docs/BLENDER_SETUP.md`](./docs/BLENDER_SETUP.md);
  - **Единый скелет**: `rig_standard`, `rig_check`, `rig_apply` — сверка и
    приведение скелета модели к стандарту Unity Humanoid, см.
    [`docs/RIG_STANDARD.md`](./docs/RIG_STANDARD.md).
- **Долгосрочная память** — JSON-хранилище с поиском по ключевым словам.
- **Планирование** — многоэтапные планы со статусами, переживают перезапуски.
- **Самоулучшение** — агент читает свой код, добавляет себе инструменты
  (динамическая загрузка из `viu/tools/custom/`) и накапливает уроки.

## Установка

Рантайм зависит только от стандартной библиотеки Python 3.10+.

```bash
pip install -e .          # установить как пакет (появится команда `viu`)
pip install -e ".[dev]"   # + pytest для разработки
```

## Запуск (Windows)

**Один файл:** `start_viu.bat` — графическое окно без чёрной консоли (`pythonw`).

1. Один раз: `make_shortcut.bat` → ярлык **«Вью»** на рабочем столе.
2. Двойной клик по ярлыку или `start_viu.bat`.

В окне слева — **кнопки** (Unity, Blender, сервис). Справа — чат с агентом.
Терминальные окна не всплывают: отчёты и инструменты пишутся в чат.

При старте Viu проверяет обновления (`git pull`, ветка `VIU_UPDATE_BRANCH`).
Настройки Ollama и пути — в начале `start_viu.bat`:

| Переменная | Назначение |
|------------|------------|
| `VIU_UNITY_PROJECT` | Unity-проект Анабарра |
| `VIU_ANIM_STAGING` | Папка входа для FBX (`U:\Anabarra\Animations`) |
| `VIU_AUTO_UPDATE` | `1` — проверять патчи при запуске |

Старые `check_unity.bat`, `setup_shanya.bat` и т.д. только открывают то же окно.
См. [`scripts/README.md`](./scripts/README.md).

### Не открывается окно (мелькнул чёрный экран)

1. Запусти **`start_viu.bat`** ещё раз — теперь при ошибке окно **останется** с текстом.
2. Открой **`viu_startup.log`** в папке Viu.
3. Частые причины:
   - Python не в PATH → установи с [python.org](https://www.python.org/downloads/) (галочка «Add to PATH»).
   - Пакет не виден → `cd U:\Viu` и `pip install -e .`
   - Нет tkinter → переустанови Python с компонентом **tcl/tk**.
4. Ярлык лучше пересоздать: `make_shortcut.bat` (теперь ведёт на `start_viu.vbs`).
5. Прямой тест: `python run_gui.pyw` — должно открыться окно или показать ошибку.

## Быстрый старт

```bash
# Интерактивный чат с Вью:
python -m viu chat

# Прямой вызов одного инструмента (без модели), напр. показать стандартный скелет:
python -m viu tool rig_standard

# Офлайн-демонстрация всего цикла (без API-ключа и сети):
python -m viu demo

# Список инструментов:
python -m viu tools

# Показать конфигурацию:
python -m viu config

# Реальный запуск через OpenAI-совместимый API:
export VIU_PROVIDER=openai
export VIU_API_KEY=sk-...
export VIU_MODEL=gpt-4o-mini
python -m viu run "Составь план прототипа уровня для Анабарры"
```

## Конфигурация (переменные окружения)

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `VIU_PROVIDER` | `mock` | `mock` или `openai` |
| `VIU_API_KEY` | — | ключ OpenAI-совместимого API |
| `VIU_BASE_URL` | `https://api.openai.com/v1` | адрес API |
| `VIU_MODEL` | `gpt-4o-mini` | имя модели |
| `VIU_ROOT` | текущий каталог | песочница для файлов/shell |
| `VIU_DATA_DIR` | `./.viu` | память, планы, логи |
| `VIU_MAX_STEPS` | `12` | лимит шагов цикла |
| `VIU_ALLOW_SHELL` | `1` | разрешить `run_shell` |
| `VIU_ALLOW_NETWORK` | `1` | разрешить web-инструменты |

## Структура

```
viu/
  agent.py            # ядро: цикл ReAct
  config.py           # конфигурация
  demo.py             # офлайн-сценарий демонстрации
  __main__.py         # CLI
  llm/                # провайдеры LLM (base, mock, openai_compatible)
  tools/              # система инструментов + custom/ для самоулучшения
  memory/             # долгосрочная память
  planning/           # планировщик
  prompts/            # системный промпт
tests/                # pytest
```

## Тесты

```bash
pytest -q
```

## Дальнейшие шаги

Каркас готов к расширению под конкретный движок игры «Анабарра»
(Godot / Unity / Unreal / собственный) — выбор движка и специализированные
инструменты (генерация ассетов, работа со сценами, сборка) добавляются
поверх этой основы.
