# Пайплайн Вью: ComfyUI → видео → Cascadeur → клип

**Автор идеи:** Den (2026-07-14).  
**Статус:** утверждено как целевой контур лаборатории анимаций. Реализация — поэтапно.

---

## Идея

Вью сама:

1. Ставит / держит **ComfyUI** (локально).
2. Пишет промпт («Шаня спит на спине, ворочается»).
3. Гоняет workflow → **чёткое короткое видео** (мало фона, один актёр, стабильная камера).
4. Режет/экспортирует **MP4** с числом кадров ≈ окну MoCap в Cascadeur.
5. Скриптом кладёт video как **Reference** в Cascadeur, жмёт MoCap (или готовит plane + pending).
6. Экспортирует FBX клип с **понятным именем** (`shanya_sleep_toss_v3.fbx`) → `Animations\` / catalog.
7. **Последний кадр** видео → стартовый image для следующей генерации (непрерывность поз).
8. NSFW — в том же контуре, без ручного промптинга Дена (флаг / отдельная очередь).

Плюс: может крутиться часами в away. Den оценивает журнал, не кликает каждый MoCap.

---

## Обязательное дополнение: дерево переходов

Генерация клипов без порядка даст «телепорты».

Вью держит **граф**:

```
sit_idle ──stand_up──► idle ──sit_down──► sit_idle
idle ──lie_down──► sleep_idle ──get_up──► idle
idle ◄──► walk ◄──► run
```

Правила:

- Из `sit_idle` **нельзя** сразу в `walk` — сначала `stand_up`.
- Каждый новый клип = узел + рёбра «из каких состояний можно войти / куда выйти».
- Animator / runtime выбирает путь; если ребра нет — Вью **генерирует** недостающий transition (Comfy → MoCap) или качает Mixamo.

Это и есть «алгоритм, в каком порядке проигрывать».

Данные: `animation_catalog.json` поля `enters_from[]`, `exits_to[]`.  
Режиссёр Comfy (`comfy_director`) смотрит дыры каталога и **приоритет transition**, у которых `enters_from` уже закрыты (есть ref/клип) — чтобы не снимать `stand_up` раньше `sit_idle`.

---

## Требования к видео (чтобы Cascadeur MoCap не сдох)

| Да | Нет |
|----|-----|
| Один персонаж, полный рост | Толпа, крупный план только лица |
| Статичная / почти статичная камера | Сильный pan/zoom |
| Чистый фон / мало деталей | Мельтешение, текст, UI |
| Хороший контраст силуэта | Мешковатая одежда, скрывающая суставы |
| FPS = таймлайну Cascadeur (24/30) | Произвольный FPS без сверки |
| Короткие клипы 1–4 с на одно действие | Минута «кино» |

Промпт-шаблон Вью (канон Дена):

```
a fit girl with a big fake breast and perfect body is [процесс + антураж]
Negative: Tongue out, wet hair
```

Отдельного «Action» / «Действие» в промпте нет — только хвост после `is`.  
Дубли ¾ (разный seed) → MP4. Стоячие: vertical | лежачие: horizontal.

После генерации: выбор лучшего → `Lab/Refs/kept/` + last-frame `Lab/Refs/seeds/`  
+ `enters_from` / `exits_to` в `animation_catalog.json` и `.viu/comfy_clips.json`.

---

## Технический контур (этапы реализации)

| Этап | Что | Зависит |
|------|-----|---------|
| 0 | Эталон Шаня + QRT в Cascadeur | сейчас |
| 1 | Путь `U:\Viu\ComfyUI` + автозапуск API | **готово** |
| 2 | Wan 2.1 T2V/I2V + `comfy_run` / triple | **готово** (нужен API workflow JSON один раз) |
| 2b | Промпт → Telegram → 3 дубля ¾ | **готово** (`lab topic=comfy` / `comfy_mocap`) |
| 2c | Выбор лучшего + last-frame seed + граф | **готово** (`comfy_clip_pick` / «Оценить клипы Comfy») |
| 3 | `cascadeur_import_reference` + MoCap assist | Python / pending |
| 4 | `cascadeur_export_clip` → Animations + catalog | |
| 5 | Last-frame → next seed image (I2V) | seed PNG пишется; I2V queue — next |
| 6 | Transition graph в catalog + runtime | **поля enters_from/exits_to в catalog** |
| 7 | NSFW queue (отдельный флаг) | |

VRAM: Comfy **или** Cascadeur **или** Unity — не вместе на 6–12 GB (очередь lab).

### Инструменты сейчас

```
comfy_status / comfy_ensure
comfy_mocap action=auto  → режиссёр (catalog) выбирает кадр; home→Telegram, away→сама
comfy_mocap action=…     → явный action; home→Telegram approve → 3× дубля ¾ → Lab/Refs
comfy_triple action=…    → 3 дубля ¾ без Telegram
lab_start topic=comfy
```

Дубли на каждый промпт: **take_a / take_b / take_c** (все ¾, разный seed + timing).  
Away: авто-одобрение + keep `take_b`. Режиссёр идёт по графу `enters_from`/`exits_to`, закрывает дыры через `ref_video`.
Режиссёр (`viu/lab/comfy_director.py`): дыры wave 1 из `animation_catalog`, **не** idle по умолчанию.

Env: `VIU_COMFY_URL`, `VIU_COMFY_ROOT=U:/Viu/ComfyUI`.  
Workflows: `.viu/comfy/workflows/t2v.json`, `i2v.json`.

Пути:

```
U:\Anabarra\Library\Lab\Refs\          ← сырые кандидаты mp4
U:\Anabarra\Library\Lab\Refs\kept\     ← выбранные для MoCap
U:\Anabarra\Library\Lab\Refs\rejected\ ← отклонённые ракурсы
U:\Anabarra\Library\Lab\Refs\seeds\    ← last-frame PNG → следующий клип
U:\Anabarra\Library\Lab\ComfyOut\      ← сырой выход Comfy
U:\Viu\.viu\comfy_clips.json           ← оценки и связи
U:\Anabarra\Animations\                ← финальные FBX
```

---

## Роли

| Кто | Делает |
|-----|--------|
| **Вью** | Промпт, Comfy, MoCap-скрипт, имена, граф, journal, NSFW-очередь |
| **Den** | Оценивает клипы, правит эталонный риг, стоп-кадр если MoCap врёт |
| **Cursor** | Инструменты API, lab steps, граф в catalog |

---

## Связь с текущим планом

Не отменяет Wave 1 Mixamo (быстрые sit/walk для игры **сейчас**).  
Comfy-пайплайн — **фабрика** поверх эталона, когда Walk/стопы и сарай уже не горят.

См. также: [VIU_AUTOMATION_2026.md](./VIU_AUTOMATION_2026.md), [WALK_FEET_FIX.md](./WALK_FEET_FIX.md).
