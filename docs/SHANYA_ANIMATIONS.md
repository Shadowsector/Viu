# Каталог анимаций Шани

Как **prop_catalog** для предметов: у каждого движения есть категория и **человеческое описание** — когда применяется, как выглядит, зачем нужно. Viu матчит Mixamo FBX по имени и знает, в какой `Animator` state класть.

Файл данных: `.viu/animation_catalog.json` (создаётся при первом запуске из seed).

---

## Категории (кошка дома + приключения)

| ID | По-русски | Смысл |
|----|-----------|--------|
| `locomotion` | Локомоция | Идёт, бежит, крадётся, гордая походка |
| `transition` | Переходы | Села, встала, легла — **не** поворот на бегу (поворот в коде) |
| `rest` | Отдых | Сидит, спит, зевает, потягивается |
| `routine` | Быт дома | Умывается, оглядывается — «балдеет» |
| `hygiene` | Гигиена | Душ, ванна |
| `social` | Общение | Привет, махнуть |
| `emotion` | Эмоции | Радость, испуг, любопытство |
| `interaction` | Предметы | Взять, бросить — affordances |
| `food` | Еда | Ест, пьёт, готовит |
| `fight` | Бой | Когти, получила удар |
| `adventure` | Приключение | Climb (полный цикл!), jump, fall, спрятаться за деревом |
| `dance` | Танец | Праздник, награда |
| `NSFW` | NSFW | Только вручную помеченные клипы |
| `special` | Особое | Споткнулась, редкие |

---

## Пример записи: climb_up

**Когда:** дерево, забор, уступ сарая — affordance `climb`, Viu предложила, если «не лезет».

**Как выглядит:** хват, **нога на горизонталь**, подтягивание, второй шаг, **выпрямление в стойку наверху** — не обрыв на «висит на руках».

**Зачем:** полный цикл взбирания; без него только crossfade из Idle выглядит фальшиво.

**Mixamo:** Climbing, Climb Up Wall, Free Hang Climb.

---

## Волны (что качать первым)

### Wave 1 — дом у таскбара + базовый adventure

`idle`, `walk`, `run`, `sit_down`, `stand_up`, `lie_down`, `sit_idle`, `sleep_idle`, `yawn`, `stretch`, `look_around`, `take`, `throw`, `jump`, `fall`, `climb_up`, `attack_claws`

### Wave 2 — жизнь и props

`sneak`, `groom`, `greeting`, `eat`, `drink`, `hit_react`, `hide_peek`, `scout`

### Wave 3 — атмосфера

`walk_proud`, `shower`, `bath`, `cook`, `dance`, `stumble`

---

## Переходные клипы vs микширование

| Ситуация | Качать отдельный FBX? |
|----------|------------------------|
| A/D разворот | **Нет** — `ShanyaLocomotion` крутит модель |
| Idle ↔ Walk / Run | **Нет** — blend 0.1–0.2 с по `Speed` |
| Стоя → сидит | **Да** — `sit_down` → loop `sit_idle` |
| Сидит → стоит | **Да** — `stand_up` |
| Стоя → спит | **Да** — `lie_down` → `sleep_idle` |
| Take / throw / attack | **Нет** — one-shot + Trigger |
| **Climb** | **Да** — один **полный** клип до стойки наверху |

---

## Куда кидать файлы

**Один Inbox:** `U:\Viu\Inbox\`

| Что | Кнопка |
|-----|--------|
| Один Mixamo `.fbx` | **«Принять анимацию (Inbox)»** → окно описания |
| `.blend` / props / картинки | **«Разобрать Inbox (модели)»** |
| Описать pending | **«Очередь анимаций»** |

**По одной анимации** — так ты не забудешь, что скачал.

## Scope (кому клип)

| Scope | Шаня | NPC-девушки | Когда выбирать |
|-------|------|-------------|----------------|
| **Девушки-biped (Шаня + NPC)** | ✓ | ✓ | Mixamo для всех female humanoid — **бег назад, walk, sit…** |
| **Только Шаня (уникальное)** | ✓ | ✗ | Особая походка, NSFW, «только главная» |
| **NPC: девушки (без Шани)** | ✗ | ✓ | Клип только для подруг/NPC |
| **Любой biped (м/ж)** | ✗* | частично | Мужские NPC, универсальные клипы |
| **Четвероногие** | ✗ | ✗ | Кошки-звери, другой скелет |

\*Пока не кладём в Shanya Animator — задумано для м/ж NPC позже.

**Бег спиной / отступление** → **«Девушки-biped (Шаня + NPC)»**, не «Любой biped».

Старая версия ошибочно трактовала «Женщины-biped» как «только NPC, не Шаня» — исправлено.

## Кнопки (меню по задачам)

- **Ещё — модели** — blend, props, экспорт домика  
- **Ещё — анимации** — принять FBX, очередь, обновить аниматор  
- **Ещё — Cascadeur** — статус (позже правка клипов)  
- **Ещё — игра** — оверлей, Unity, тест-сцена  

«Импорт FBX анимации» (file picker) убран — дублировал Inbox.

---

## Mixamo: настройки

- **Without Skin**
- **In Place** — для jump, attack, climb, sit (где есть)
- Walk/Run — обычный forward ok, root motion в Unity выключим

Имя файла: `Climbing.fbx` или `X Bot@Female Sitting Down.fbx` — matcher найдёт запись. Для надёжности: `Shanya_ClimbUp.fbx`.

Не поняла имя → override в `Assets/Characters/Shanya/Animations/viu_clips.json`:

```json
{ "file": "X Bot@Female Climbing.fbx", "state": "ClimbUp" }
```

### Overlay locomotion (зафиксировано 2026-07-12, Walk — 2026-07-14)

| State | FBX | Примечание |
|-------|-----|------------|
| Idle | `X Bot@Idle.fbx` | Create From This Model |
| Walk | **`Shanya_Walk.fbx` или Mixamo Female Walk** | **не** Run |
| Walk (fallback) | `Shanya_Run.fbx` | только если нет Walk; state.speed **0.55** |

Полный чеклист «не откатывать» → [`OVERLAY_BASELINE.md`](./OVERLAY_BASELINE.md).

### Почему ноги «заплетаются» на ходьбе

Это **не скорость** — стопы подворачиваются из‑за Humanoid retarget / кривого Walk-клипа.

**Чёткая инструкция:** [`WALK_FEET_FIX.md`](./WALK_FEET_FIX.md) (диагностика Avatar → Mixamo Female Walk → Configure стоп → Cascadeur).

Кратко: нужен настоящий **Female Walk** (`Shanya_Walk.fbx`), Avatar модели с зелёными Foot/Toes, клипы только **Create From This Model**.

---

## Jump — на месте или спрыгнуть?

**Оба**, разные клипы:

| slug | Что | Когда |
|------|-----|--------|
| `jump` | Прыжок **на месте** / вверх (In Place) | Перепрыгнуть низкое, игривость, старт с земли |
| `fall` | Падение / приземление | Сорвалась, прыжок с высоты, failed land |
| позже `jump_off` | Спрыгнуть **с** уступа (опционально) | Крыша сарая, ветка — отдельный клип, когда понадобится |

Для Wave 1 качай **Jump** (In Place) + **Falling Idle** / Hard Landing.  
Спрыгивание с сарая = `jump` с края + `fall`, либо позже отдельный клип в Cascadeur/Comfy.

---

## Mixamo — что скачать сейчас (Wave 1 + сарай)

Клади **по одному** FBX в `U:\Viu\Inbox\`:

| Приоритет | Mixamo (поиск) | slug каталога | Зачем |
|-----------|----------------|---------------|--------|
| 1 | **Female Walk** / Walking | `walk` | заменить Run-as-Walk |
| 2 | Sitting Down | `sit_down` | стул в сарае |
| 3 | Female Sitting / Sitting Idle | `sit_idle` | сидит |
| 4 | Standing Up | `stand_up` | встаёт |
| 5 | Lying Down / Sleeping Idle | `lie_down` / `sleep_idle` | солома |
| 6 | Yawn / Stretching | `yawn` / `stretch` | быт |
| 7 | Looking Around | `look_around` | у окна |
| 8 | Climbing | `climb_up` | дерево / сарай |
| 9 | Jump / Falling Idle | `jump` / `fall` | adventure |
| 10 | Picking Up / Throw | `take` / `throw` | props |
| 11 | Waving | `greeting` | Wave 2 |
| 12 | Female Walk Backward | `walk_back` | отступление S |

Настройки: **Without Skin**; In Place — для jump/sit/climb где есть.

---

## Инструменты Viu

```
animation_catalog_show          — весь каталог или missing_only=1
animation_catalog_show slug=climb_up
animation_catalog_match file=U:/Viu/Inbox/Climbing.fbx
route_inbox                     — разобрать Inbox
unity_import_staging            — если FBX уже в Animations/
unity_sync_animations           — пересобрать Animator
```

Автоматизация / сарай: [VIU_AUTOMATION_2026.md](./VIU_AUTOMATION_2026.md), [BARN_LIVELINESS.md](./BARN_LIVELINESS.md).

---

## Связь с «жизнью» Шани (будущее)

1. Viu читает **animation_catalog** + **prop affordances** + сцену.
2. Нет `sleep_idle`, но нет prop с `sleep` → «негде спать — коврик?»
3. Есть дерево, нет `climb_up` → «скачай Climbing с Mixamo».
4. Деньги — отдельная система (wave позже).

---

## NSFW

Клипы только с `category: NSFW` в каталоге и явной пометкой. Viu не предлагает в обычном reflect без флага.
