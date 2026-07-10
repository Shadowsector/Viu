# Три папки на диске U:

Вью управляет **тремя зонами**. Она **не лезет** на `C:\Users\...\Downloads`, пока ты сам не задашь `VIU_INBOX_DIR`.

---

## 1. `U:\Viu\` — программа

```
U:\Viu\
├── Viu.cmd, viu\…          ← код и exe
├── .viu\                   ← каталог предметов, roadmap, логи
│   ├── prop_catalog.json
│   └── affordances\
└── Inbox\                  ← СЮДА кладёшь пак для разбора (один за раз)
```

**Inbox** — твоя «Для_анализа». Имя латиницей (`Inbox`), чтобы не ломать скрипты; смысл тот же.

### Что класть в Inbox

Один пак — не сотни файлов:

```
U:\Viu\Inbox\
└── hut_pack\                 ← одна папка на задачу
    ├── hut.blend             ← уже подчищенный (лишнее удалил)
    ├── Textures\
    └── notes.txt             ← опционально: «домик, режу переднюю стену»
```

Или один файл: `stool.blend`, `walk.fbx`, архив `.zip`.

После **«Разобрать Inbox»** пак **исчезает из Inbox** и оказывается в `U:\Anabarra\Library\`.

---

## 2. `U:\Anabarra\` — игра

```
U:\Anabarra\
├── Unity\Anabarra\         ← Unity-проект (Assets, Builds, оверлей)
├── Library\                ← склад после разбора Inbox
│   ├── Blender\
│   ├── Props\fbx\ …
│   ├── Archives\
│   └── Processed\          ← сюда позже: результат обработки Вью
└── Animations\             ← FBX анимаций → Unity
```

> **`U:\Anabarra\Anabarra`** или старая копия **Viu внутри Anabarra** — лишнее.  
> Можно удалить вручную после бэкапа; рабочая Вью — только **`U:\Viu`**.

---

## 3. `U:\Desktop Mascot\` — архив (не автоскан)

Сотни мешей, текстур, анимаций — **склад-архив**. Вью **не сканирует** эту папку сама (избыточно и медленно).

**Workflow:**

1. В Total Commander / проводнике нашёл нужное в Desktop Mascot.
2. Подготовил: вырезал лишнее, положил Textures, написал `notes.txt`.
3. Скопировал **одну папку** → `U:\Viu\Inbox\`.
4. В GUI: **«Разобрать Inbox»** → **«Разметить предметы»**.

---

## Почему Вью полезла на C:\Downloads?

Раньше fallback был `Path.home() / "Downloads"` — типичный Windows-путь на **C:**.  
Теперь по умолчанию: **`U:\Viu\Inbox`**.

---

## Одна кнопка: «Принять asset»

1. Положи в **`U:\Viu\Inbox`**: `Old Stables.blend` + папка **`textures`** (рядом!)
2. Задай **`VIU_BLENDER_EXE`**, если Blender не в PATH (см. ниже)
3. **«Принять asset»** — не «Разобрать Inbox» отдельно

Если уже нажал «Разобрать» и blend в Library — **«Принять asset»** найдёт его там сам.
Если `textures` уехали в `References\images\` — Вью **вернёт их рядом** с blend.

```
VIU_BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 5.1\blender.exe
```

Концепция целиком: [`VIU_CONCEPT.md`](./VIU_CONCEPT.md).

---

**Workflow для сарайчика с Textures:**

1. `U:\Viu\Inbox\hut_pack\hut.blend` + `Textures\`
2. **«Подготовить asset для Unity»** (не «Разобрать Inbox» — можно сразу prepare)
3. Вью в фоновом Blender:
   - перепривязывает текстуры из `Textures\`;
   - **pack** — вшивает картинки в `.blend` (не слетят);
   - **скрывает** землю/фон по имени (`Ground`, `Terrain`, …);
   - убирает **SUN**, оставляет точечный/spot свет;
   - упрощает **World** (без HDRI);
   - сохраняет в `U:\Anabarra\Library\Processed\hut_pack\hut_prepared.blend`
4. Открывает **Blender** — только осмотр (стены, свет). **Переименовывать меши не нужно**
5. **«Следующий шаг»** — разметка Props во Вью (Building/Landscape → shell автоматически)

> **Pack ≠ bake.** Pack кладёт файлы png/jpg *внутрь* blend. UV-bake (одна текстура на меш) — позже, если понадобится для Unity.

---

В Blender **не обязательно** переименовывать меши. Роли задаются во Вью по коллекции Outliner:
- **Building / Landscape** → shell (автоматически)
- **Props** → интерактив (кровать, дверь, бочка…) — вес и галочки
- **Stuff / пыль / трава** → decor (автоматически)

В «Разметить предметы» — карточка на каждый Prop. Shell — кнопка **«Shell — без разметки»**.

---

## Переменные (если нужно переопределить)

```
VIU_INBOX_DIR=U:\Viu\Inbox
VIU_DATA_DIR=U:\Viu\.viu
VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
VIU_LIBRARY_ROOT=U:\Anabarra\Library
VIU_MASCOT_DIR=U:\Desktop Mascot
```

**Не задавай** `VIU_DOWNLOADS_DIR=C:\...` — если не хочешь, чтобы Вью ходила на C:.

---

## Что дальше (идея, не всё уже автоматом)

| Шаг | Кто | Что |
|-----|-----|-----|
| Подготовка | Ты | blend + textures + notes.txt → Inbox |
| Приём | Вью | Inbox → Library, скан в каталог |
| Разметка | Ты | GUI: вес, роль, действия |
| **Экспорт** | **Вью** | **«Экспорт в Unity (FBX)»** или «Следующий шаг» → `Assets/Environment/` |
| Игра | Unity | prefab, dollhouse wall script |

Проверить пути: в чате «project_status».
