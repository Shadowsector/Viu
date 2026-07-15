# Монстры: что делать по шагам

Обновление Вью тянет ветку **`cursor/viu-agent-core-65c2`**.  
Каталог существ туда уже влит — после «Обновить Вью» перезапусти окно.

---

## Зачем это

Много скачанных моделей → привести к **нескольким размерам**.  
Тогда анимации пишутся **на размер** (гоблин-класс, волк-класс…), а не на каждого монстра отдельно.

Внутри класса рост чуть плавает (узкий допуск), lineup в Blender показывает всех **рядом с Шаней**.

---

## Шаг 0. Куда класть файлы

Папка:

```
U:\Anabarra\Library\Lab\Creatures\Inbox\
```

- Кинь туда `.fbx` / `.blend` / `.glb` монстров.
- Если текстуры **отдельной папкой** — положи рядом `textures\` (или `Textures\`) в той же папке, что модель.
- Пока **не** жми Bootstrap Unity и не тащи в Cascadeur — сначала каталог.

---

## Шаг 1. Скан → таблица

**Где писать:** чат в **окне Вью** или Telegram — **ровно одну** строку (не два раза подряд без пробела).

**Напиши одно из:**

```
creature_catalog_scan
```

или по-русски:

```
сканируй существ
```

Это **прямая команда**: Вью сразу сканирует папку, **без** болтовни LLM.  
Если ответила «укажите параметры» / «чем помочь» — команда **не** сработала (старая сборка или склейка имени). Сделай «Обновить Вью» и повтори.

**Что произойдёт:**
- Вью обойдёт `Lab/Creatures/Inbox` (и заодно Lab/Models/Inbox).
- Создаст/обновит `.viu/creature_catalog.json`.
- Класс роста **не** назначит сама — только список и подсказки.
- Создаст `.viu/girl_sockets.json`.

Очередь без класса:

```
creature_catalog_show mode=pending
```

или: `очередь существ`

---

## Шаг 2. Ты назначаешь размер (главное)

Для **каждой** модели из pending скажи Вью, к какому классу она относится.

**Пример:**

```
creature_catalog_set_size id=abc12345 size=small locomotion=biped
```

или по имени:

```
creature_catalog_set_size slug=goblin_a size=small locomotion=biped
```

### Какие `size` бывают

| size | Target | Допуск | Кто |
|------|--------|--------|-----|
| `mini` | 30 см | 27–33 см | феи |
| `small` | 80 см | 74–86 см | гоблины |
| `humanoid` | 175 см | 168–182 см | антропоморфы ~рост Шани |
| `large` | 235 см | 225–245 см | крупные твари |
| `huge` | 360 см | 330–390 см | хватает Шаню за талию |
| `quad_mini` | 30 см | 26–34 см | куницы… |
| `quad_med` | 75 см | 68–82 см | собака/волк |
| `quad_large` | 160 см | 150–170 см | лошадь/корова |

### `locomotion` (как ходит)

`biped` · `quadruped` · `amorph` (слизень) · `tentacle` · `mimic` · `flyer`

### Два размера у одной модели

Маленький гоблин и «большой вариант» одной болванки:

```
creature_catalog_set_size slug=goblin_a size=small size_alt=humanoid locomotion=biped
```

### NSFW-метка (пока флаг)

```
creature_catalog_set_size slug=orc_boss size=large locomotion=biped nsfw=1
```

**Что произойдёт:** в каталоге у записи появятся `size_class`, целевой рост, `anim_bucket` вроде `small__biped`.  
Позже все с одним bucket будут делить анимации.

Повтори шаг 2, пока `mode=pending` не станет пустым.

---

## Шаг 3. Увидеть рост рядом с Шаней

Когда хотя бы несколько размечены:

```
creature_lineup
```

или только гоблины:

```
creature_lineup size=small
```

Если Шаня не нашлась сама:

```
creature_lineup shanya_path=U:\путь\к\Shanya.fbx
```

**Что произойдёт:**
- Вью напишет файлы в  
  `U:\Anabarra\Library\Lab\Creatures\Lineup\`
  - `lineup_job.json` — список кого ставить
  - `viu_creature_lineup.py` — скрипт Blender
  - потом появится `creature_lineup.blend`

**Ты запускаешь Blender** (один раз):

```bat
blender --background --python "U:\Anabarra\Library\Lab\Creatures\Lineup\viu_creature_lineup.py" -- "U:\Anabarra\Library\Lab\Creatures\Lineup\lineup_job.json"
```

(путь к `blender.exe` — как у тебя в PATH или полный)

**Результат:** открой `creature_lineup.blend` — **Шаня слева**, монстры в ряд, каждый уже **подогнан к target своего класса**. Глазами проверь: кто выбивается → смени ему `size` (шаг 2) и lineup снова.

---

## Шаг 4. Пока не делаем (следующая очередь)

Это **ещё не** автоматизировано в этой версии:

| Позже | Смысл |
|-------|--------|
| Bake текстур / pack | можно руками в Blender |
| Genital-риг + flaccid | после эталонного prefab |
| A-pose фото → Comfy | как у Шани, но seed = монстр |
| Сокеты на теле Шани в Unity | oral / vaginal / anal / руки / cleavage |

Сейчас цель шагов 1–3: **таблица + твои классы + визуальная линейка роста**.

---

## Шпаргалка команд

| Команда | Зачем |
|---------|--------|
| `creature_catalog_scan` | собрать таблицу из Inbox |
| `creature_catalog_show mode=pending` | кого ещё не разметил |
| `creature_catalog_show mode=classes` | таблица размеров |
| `creature_catalog_show mode=sockets` | мишени на девушках |
| `creature_catalog_set_size …` | назначить класс |
| `creature_lineup` | подготовить сравнение с Шаней в Blender |

Список всех: `creature_catalog_show mode=all`

---

## Если «Обновить Вью» пишет «и так новая»

Кнопка смотрит ветку **`cursor/viu-agent-core-65c2`**.  
Нужен коммит с каталогом существ **на этой** ветке (не только на `creature-catalog`).  
После пуша в agent-core: снова «Обновить Вью» → должен подтянуть новый SHA → перезапуск.
