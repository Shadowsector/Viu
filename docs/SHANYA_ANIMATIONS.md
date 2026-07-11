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

| Scope | Смысл |
|-------|--------|
| `shanya_humanoid` | **Только Шаня** — Humanoid Erisa. Default для Mixamo в Animations/ |
| `humanoid_female` | Другие female NPC — **не** подмешивается в Shanya Animator |
| `humanoid_any` | Любой biped — отдельный prefab |
| `creature_quadruped` | **Не для Шани** — Viu не ставит в Shanya controller |

Fast Run → scope «Только Шаня» → state Run в `Shanya_Idle_Stand.controller`.

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

---

## Связь с «жизнью» Шани (будущее)

1. Viu читает **animation_catalog** + **prop affordances** + сцену.
2. Нет `sleep_idle`, но нет prop с `sleep` → «негде спать — коврик?»
3. Есть дерево, нет `climb_up` → «скачай Climbing с Mixamo».
4. Деньги — отдельная система (wave позже).

---

## NSFW

Клипы только с `category: NSFW` в каталоге и явной пометкой. Viu не предлагает в обычном reflect без флага.
