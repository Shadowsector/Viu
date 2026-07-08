# Структура папок Анабарры

Куда что класть на диске `U:` — чтобы не путать **игру**, **программу Вью** и **входящие файлы**.

## Два корня — запомни разницу

| Путь | Что это |
|------|---------|
| **`U:\Viu`** | Программа Вью: Python, exe, обновления. **Не** складывай сюда blend, текстуры, каталог. |
| **`U:\Anabarra`** | Игра и все рабочие файлы: Unity, библиотека, данные Вью. |

> **`U:\Anabarra\Anabarra`** (если есть отдельно) — не основной Unity-проект.  
> Рабочий Unity: **`U:\Anabarra\Unity\Anabarra`**.

---

## Дерево каталогов

```
U:\Anabarra\
├── .viu\                          ← данные Вью (каталог, roadmap, логи)
│   ├── prop_catalog.json
│   ├── affordances\
│   └── logs\
├── Unity\
│   └── Anabarra\                  ← Unity-проект (Assets, Builds, оверлей)
├── Library\                       ← библиотека ассетов для разбора
│   ├── Blender\incoming\          ← .blend и папки-паки (blend + Textures)
│   ├── Props\incoming\fbx|obj|glb
│   ├── Archives\incoming\         ← zip / rar / 7z (не распаковывает Вью)
│   ├── References\images\         ← png, jpg (референсы)
│   └── Incoming\unsorted\         ← всё непонятное
└── Animations\                    ← вход для FBX анимаций (→ Unity)

U:\Viu\                            ← только программа
```

---

## Куда что кидать (твой workflow)

### 1. Скачал что-то новое

Положи в **Downloads** (Windows или свой путь):

- один `.blend` / `.fbx`;
- **папку** с blend + Textures;
- **архив** (.zip, .rar, .7z) — можно не распаковывать.

### 2. «Разобрать Downloads» в GUI

Вью переносит **верхний уровень** Downloads в `U:\Anabarra\Library\...` и **убирает оттуда** (перенос = исчезло из Downloads).

| Что | Куда |
|-----|------|
| `.blend` | `Library\Blender\incoming\` |
| Папка с blend + Textures | `Library\Blender\incoming\<имя папки>\` |
| `.fbx` | `Library\Props\incoming\fbx\` |
| `.zip` / `.rar` / `.7z` | `Library\Archives\incoming\` |
| `.png` / `.jpg` | `Library\References\images\` |

Архивы **не распаковывает**. Распаковал сам → снова в Downloads (или сразу в Library) → снова «Разобрать».

### 3. «Разметить предметы»

- **`.blend`** — Вью создаёт **карточку на каждый MESH** в файле (домик = много строк в очереди).
- **`.fbx`** и др. — одна карточка на файл.

### 4. В Unity попадает уже отобранное

После разметки и экспорта — prefab в `Assets\...` Unity-проекта. Библиотека — черновик и склад, не финальная игра.

---

## Составной объект (комната / домик в одном .blend)

В Blender назови объекты так:

| Префикс имени | Роль | В GUI |
|---------------|------|-------|
| `Shell_` | стены, пол, крыша | «Shell — без разметки» |
| `Interactive_` | стул, печь, дверь | вес + галочки (сидеть, открыть…) |
| `Decor_` | ваза, картина | можно пропустить или decor |

Коллекции в Blender: `Shell`, `Interactive`, `Decor` — удобно, но Вью смотрит на **имена MESH-объектов**.

Пример:

```
hut.blend
  Shell_WallFront
  Shell_Floor
  Interactive_Bed
  Interactive_Stove
  Decor_Lamp
```

После скана в очереди:

```
hut.blend › Shell_WallFront
hut.blend › Interactive_Bed
…
```

---

## Переменные окружения (если пути нестандартные)

```
VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
VIU_DATA_DIR=U:\Anabarra\.viu
VIU_LIBRARY_ROOT=U:\Anabarra\Library
VIU_DOWNLOADS_DIR=C:\Users\ТвоёИмя\Downloads
VIU_ANABARRA_ROOT=U:\Anabarra
```

Если Unity уже на `U:\Anabarra\Unity\Anabarra`, часто достаточно только `VIU_DATA_DIR`.

---

## Где посмотреть пути в Вью

- Кнопка / инструмент **project_status** — покажет текущие пути.
- При первом «Разобрать Downloads» папки Library создаются автоматически.
