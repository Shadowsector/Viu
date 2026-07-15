# Каталог существ и нормализация роста

**Цель:** меньше уникальных анимаций — все модели сводятся к **size_class × locomotion**,  
рост внутри класса можно чуть варьировать; анимации общие на bucket.

## Классы роста

### Бипеды / антропоморфы

| id | Target | Допуск | Пример |
|----|--------|--------|--------|
| `mini` | 0.30 m | 0.22–0.40 | феи |
| `small` | 0.80 m | 0.60–1.00 | гоблины |
| `humanoid` | 1.75 m | 1.55–1.95 | антропоморфы ~Шаня |
| `large` | 2.35 m | 2.10–2.60 | 220–250 см |
| `huge` | 3.60 m | 2.80–5.00 | хватает Шаню за талию |

### Четвероногие (высота)

| id | Target | Пример |
|----|--------|--------|
| `quad_mini` | 0.30 m | куницы |
| `quad_med` | 0.75 m | собака / волк |
| `quad_large` | 1.60 m | лошадь / корова |

**Dual-size:** у записи `size_class` + `size_alt[]` (например гоблин `small` и вариант `humanoid`).

## Locomotion

`biped` · `quadruped` · `amorph` · `tentacle` · `mimic` · `flyer` · `unknown`

Набор анимаций = `{size_class}__{locomotion}` (поле `anim_bucket`).

## Сокеты на девушках

Файл: `.viu/girl_sockets.json` (создаётся при скане).

| id | Назначение |
|----|------------|
| `socket_oral` | рот |
| `socket_vaginal` | вагина |
| `socket_anal` | анус |
| `socket_hand_l` / `socket_hand_r` | ладони |
| `socket_cleavage` | меж грудей |

Penetrator (монстр / NSFW-prop) целится в активный socket.  
Flaccid/erect — состояния одного genital-рига (позже).

## Папки

```
U:\Anabarra\Library\Lab\Creatures\Inbox\       ← сырые модели
U:\Anabarra\Library\Lab\Creatures\Processed\   ← после scale / bake
U:\Anabarra\Library\Lab\Creatures\Lineup\      ← lineup_job + creature_lineup.blend
U:\Viu\.viu\creature_catalog.json
U:\Viu\.viu\girl_sockets.json
```

Текстуры рядом (`textures/`) — флаг `textures_external` при скане.

## Инструменты Вью

```
creature_catalog_scan              → таблица из Inbox
creature_catalog_show mode=pending → очередь разметки
creature_catalog_set_size id=… size=small locomotion=biped size_alt=humanoid
creature_lineup size=small,humanoid shanya_path=…
```

Lineup: Blender-скрипт ставит **Шаню слева** и существ в ряд, каждый scale к `target_height` класса — визуальное сравнение в одном кадре.

```bash
blender --background --python "…/Lineup/viu_creature_lineup.py" -- "…/Lineup/lineup_job.json"
```

## Порядок работы (Ден)

1. Кинуть модели в `Lab/Creatures/Inbox` (текстуры рядом, если отдельно).
2. `creature_catalog_scan`.
3. Пройти `pending`: для каждого `set_size` (+ dual / locomotion / nsfw).
4. `creature_lineup` → открыть `creature_lineup.blend`, поправить глазками.
5. Позже: bake текстур, genital prefab, A-pose фото → Comfy (отдельные шаги).

## Связь с анимациями

Девушки 150–170 см → один Humanoid-набор.  
Монстры → клипы на `anim_bucket`, не на имя файла.
