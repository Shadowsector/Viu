# Подготовка диска для совместных анимаций (Ден)

Корни по умолчанию: `U:\Viu` (программа), `U:\Anabarra` (игра + Library).

Пилот: **`shanya_wolf_approach`** — Шаня + волк.

---

## 1. Шаня (FBX)

Положи **один** файл FBX (или `.blend`) в **любое** из мест — Вью ищет по порядку:

| Приоритет | Путь |
|-----------|------|
| 1 (лучше) | `U:\Anabarra\Library\Lab\Models\CascadeurReady\` |
| 2 | `U:\Anabarra\Library\Lab\Models\Inbox\` |
| 3 | `U:\Anabarra\Library\Characters\Shanya\` |
| 4 | `U:\Anabarra\Library\Blender\Shanya\` |
| 5 | `U:\Anabarra\Unity\Anabarra\Assets\Characters\Shanya\` (рекурсивно) |

**Имя файла:** в имени должно быть `Shanya` или `shanya` (регистр не важен).  
Примеры: `Shanya.fbx`, `Shanya_Erisa.fbx`, `shanya_rig.fbx`.

```
U:\Anabarra\Library\Lab\Models\CascadeurReady\Shanya.fbx
```

Проверка: после blocking в логе не должно быть `MISSING Shanya`.

---

## 2. Волк (creature_catalog, slug `wolf_alpha`)

### Шаг A — файл в Inbox

```
U:\Anabarra\Library\Lab\Creatures\Inbox\wolf_alpha.fbx
```

Важно: имя **`wolf_alpha`** (до расширения) → после скана slug в каталоге будет `wolf_alpha`.  
Если файл называется `Wolf.fbx`, slug станет `wolf` — тогда в каталоге поправь slug вручную (шаг D).

Текстуры — рядом:

```
U:\Anabarra\Library\Lab\Creatures\Inbox\wolf_alpha.fbx
U:\Anabarra\Library\Lab\Creatures\Inbox\textures\   (или wolf_alpha\textures\)
```

### Шаг B — скан

В чате Вью:

```text
creature_catalog_scan
```

Или кнопка **«Разметить существ»** → скан подтянется сам.

### Шаг C — размер (обязательно)

Волк = четвероногий средний:

```text
creature_catalog_set_size slug=wolf_alpha size=quad_med locomotion=quadruped
```

Или в GUI «Разметить существ» → класс **quad_med**, locomotion **quadruped**.

### Шаг D — если slug не `wolf_alpha`

Открой `U:\Viu\.viu\creature_catalog.json`, найди запись волка, выставь:

```json
"slug": "wolf_alpha",
"name": "wolf_alpha",
"path": "U:\\Anabarra\\Library\\Lab\\Creatures\\Inbox\\wolf_alpha.fbx",
"size_class": "quad_med",
"locomotion": "quadruped",
"status": "sized"
```

(путь — как у тебя на диске, двойные слэши в JSON)

### Шаг E — lineup (рекомендуется)

Нормализует рост и даст `photo_front` / `photo_side` для Comfy:

```text
creature_lineup
```

или кнопка **«Линейка существ»**.

После lineup в каталоге:

- `measured_height_m` / `target_height_m` ≈ **0.75** м (quad_med)
- PNG: `U:\Anabarra\Library\Lab\Creatures\Processed\wolf_alpha\front.png`

---

## 3. Чеклист перед `interaction_blocking`

| # | Проверка |
|---|----------|
| 1 | `Shanya*.fbx` в CascadeurReady или Inbox |
| 2 | `wolf_alpha.fbx` в `Lab\Creatures\Inbox\` |
| 3 | `creature_catalog_scan` выполнен |
| 4 | у волка `size_class=quad_med`, `slug=wolf_alpha` |
| 5 | ComfyUI поднят (`comfy_ensure`) — для master draft |

Проверить каталог:

```text
interaction_catalog_show slug=shanya_wolf_approach
creature_catalog_show
```

---

## 4. Запуск пайплайна

```text
interaction_blocking slug=shanya_wolf_approach
interaction_master_draft slug=shanya_wolf_approach
```

Или lab:

```text
lab_start topic=interaction catalog_slug=shanya_wolf_approach reset=1
lab_run_all topic=interaction
```

---

## 5. Куда Вью пишет результат

| Этап | Путь |
|------|------|
| Blocking | `U:\Anabarra\Library\Lab\Interactions\shanya_wolf_approach\blocking\blocking.blend` |
| Choreography lock | `...\blocking\choreography_lock.json` |
| Master draft (Comfy) | `...\master\master_draft.mp4` |
| Master approved | `...\master\master_approved.mp4` (после одобрения) |

Каталог сцен: `U:\Viu\.viu\interaction_catalog.json`

---

## 6. Типичные ошибки

| Сообщение | Решение |
|-----------|---------|
| `Не найдены модели: initiator:wolf_alpha` | Нет slug в каталоге или битый `path` |
| `MISSING Shanya` | Нет FBX с Shanya в путях из §1 |
| Comfy offline | `comfy_ensure` или запусти `U:\Viu\ComfyUI\` |
| `size_class` пустой | `creature_catalog_set_size` для волка |

См. также: `docs/INTERACTION_PIPELINE.md`, `docs/CREATURE_CATALOG.md`.
