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

## Куда кидать файлы (единый Inbox)

**Один вход:** `U:\Viu\Inbox\`

| Что | Куда Viu кладёт |
|-----|-----------------|
| `.blend` + textures (папка) | prepare → Processed |
| `.blend` один файл | `Library/Blender` → prepare |
| FBX анимация (Mixamo) | `U:\Anabarra\Animations` + `Assets/Characters/Shanya/Animations/` |
| FBX prop/домик | `Library/Props/fbx` |
| Картинки | `Library/References/images` |

**Инструменты:**

- GUI: позже «Разобрать Inbox»; сейчас **`route_inbox`** или «Следующий шаг» для blend.
- Агент: `route_inbox`, `animation_catalog_match`, `animation_catalog_show`.

**Окно Вью (чат):** опиши, что положил — «скачал Climbing и Yawn в Inbox»; Viu вызовет `route_inbox` и сопоставит с каталогом.

Drag-and-drop в окно — в планах; пока физически тот же **Inbox**.

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
