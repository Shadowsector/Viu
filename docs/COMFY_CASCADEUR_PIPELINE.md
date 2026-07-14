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

Данные: расширить `animation_catalog.json` полями `enters_from[]`, `exits_to[]` (план).

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

Промпт-шаблон Вью (черновик):

```
full body, single female character, side or 3/4 view, plain background,
stable camera, no text, no blur, clear limbs, [ACTION], loopable motion
```

---

## Технический контур (этапы реализации)

| Этап | Что | Зависит |
|------|-----|---------|
| 0 | Эталон Шаня + QRT в Cascadeur | сейчас |
| 1 | Путь `U:\Viu\ComfyUI` + автозапуск API | **готово** |
| 2 | Wan 2.1 T2V/I2V + `comfy_run` / triple | **готово** (нужен API workflow JSON один раз) |
| 2b | Промпт → Telegram → 3 ракурса | **готово** (`lab topic=comfy` / `comfy_mocap`) |
| 3 | `cascadeur_import_reference` + MoCap assist | Python / pending |
| 4 | `cascadeur_export_clip` → Animations + catalog | |
| 5 | Last-frame → next seed image | частично (папка seeds) |
| 6 | Transition graph в catalog + runtime | |
| 7 | NSFW queue (отдельный флаг) | |

VRAM: Comfy **или** Cascadeur **или** Unity — не вместе на 6–12 GB (очередь lab).

### Инструменты сейчас

```
comfy_status / comfy_ensure
comfy_mocap action=…     → Telegram approve → 3× Lab/Refs
comfy_triple action=…    → 3 ракурса без Telegram
lab_start topic=comfy
```

Ракурсы на каждый промпт: **side / three_quarter / front**.

Env: `VIU_COMFY_URL`, `VIU_COMFY_ROOT=U:/Viu/ComfyUI`.  
Workflows: `.viu/comfy/workflows/t2v.json`, `i2v.json`.

Пути:

```
U:\Anabarra\Library\Lab\Refs\          ← mp4 + last frame png
U:\Anabarra\Library\Lab\ComfyOut\      ← сырой выход Comfy
U:\Anabarra\Animations\                ← финальные FBX
U:\Viu\.viu\lab\cascadeur\journal.md   ← что сгенерила и зачем
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
