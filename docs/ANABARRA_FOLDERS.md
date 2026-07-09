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

## Разметка .blend с кучей предметов

В Blender назови меши: `Shell_*`, `Interactive_*`, `Decor_*`.  
В «Разметить предметы» — карточка на каждый меш. Shell — кнопка **«Shell — без разметки»**.

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
| Обработка | Вью (позже) | текстуры, экспорт FBX → `Library\Processed\` |
| Игра | Unity | prefab в Assets |

Проверить пути: в чате «project_status».
