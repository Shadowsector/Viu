# Существа — два шага в Blender

Пайплайн с **другой стороны**: сначала готовим модель, потом размечаем и сравниваем с Шаней.

| Шаг | Кнопка во Вью | Панель Blender (N → Viu) |
|-----|---------------|--------------------------|
| 1 | **Подготовить модели** | **Viu — подготовка** |
| 2 | **Студия существ** | **Viu — студия** |

После каждого шага — **Синхр. подготовки** / **Синхр. студии**.

---

## Inbox

Единая папка:

```
U:\Anabarra\Library\Lab\Creatures\Inbox\
```

Сюда все модели (волки, гоблины, humanoid). `Models\Inbox` и `CascadeurReady` для существ больше не нужны.

---

## Пайплайн папок (текстуры)

| Стадия | Папка | Текстуры |
|--------|--------|----------|
| Сырое | `Inbox/<slug>/` | `textures/` рядом — **только импорт** |
| Prepared | `Prepared/<slug>/` | packed в blend + `texture_manifest.json` |
| Игра | `Processed/<slug>/` | `<slug>_ready.fbx` + `texture_manifest.json` |

В prep: **Упаковать текстуры** или автоматически при Save prepared.

Unity/Cascadeur читают **только** `Processed/<slug>/`.

---

## Wardrobe (наборы одежды)

Между prep и студией: **Разметка одежды** → панель **Viu — wardrobe**.

- Переключай меши (накидка, штаны, купальник…)
- **Сохранить набор** → `Prepared/<slug>/outfit_sets.json`
- Пресеты: только тело, снять одежду, показать/спрятать genital mesh
- ⚠ предупреждение если genital + штаны (clipping)
- **Синхр. wardrobe** → каталог (`outfit_sets_path`, `genital_rig`)

Примеры id: `casual_01`, `swim_01`, `swim_02`, `nsfw_partial`, `nsfw_full`, `bath`

---

## Шаг 1 — Подготовка (`prepared.blend`)

1. Положи модель в **Creatures/Inbox**
2. **Разметить существ** (скан) — опционально, каталог нужен для очереди
3. **Подготовить модели**
4. В Blender → **Viu — подготовка**:
   - **Спрятать IK / WGT**
   - **Показать меши тела**
   - **Bursting Head Repair** — diffeomorphic / Blender 4+: scale лицевых костей = 0 из-за драйверов
   - **Проверить текстуры**
   - **Сбросить позу (rest)** → вручную выставь **A-pose**
   - Удали лишнее (мечи, дубли)
   - **Сохранить prepared.blend** — только эта модель
5. **Синхр. подготовки**

Выход:

```
Lab\Creatures\Prepared\<slug>\<slug>_prepared.blend
```

---

## Шаг 2 — Студия + разметка (эталон **FBX**)

1. **Студия существ** (очередь = только с `prepared.blend`)
2. Blender → **Viu — студия**:
   - **Класс** (mini / quad_med / humanoid …) + **Locomotion** (biped = 2 ноги, quadruped = 4)
   - **Применить разметку**
   - Сравни с **Шаней** слева
   - **Применить рост**
   - **Снять скрины**
   - **Сохранить эталон FBX** — только существо, не Шаня
   - **Скрины ок** или **Заметка для Вью**
3. **Синхр. студии**

Выход:

```
Lab\Creatures\Processed\<slug>\front.png, side.png
Lab\Creatures\Processed\<slug>\<slug>_ready.fbx
```

Разметка из Blender попадает в `creature_catalog.json` (size_class, locomotion, рост, photo_ok).

### Анатомия для анимаций

Вместо галочки «NSFW»:

| Поле | Значения |
|------|----------|
| **Гениталии** | нет · пенис · вагина · futa |
| **Контакт без гениталий** | рот/язык · щупальца · руки/лапы |

Примеры:
- **Мимик / живой цветок** — гениталии «нет», контакт «рот/язык»
- **Осьминог** — «нет» + «щупальца» (locomotion=tentacle)
- **Гоблин-муж** — «пенис»
- **Кентаврша** — «вагина» или «futa»

Ключ анимаций: `size__locomotion__penis` или `size__locomotion__oral+tentacle`.

Окно **Разметить существ** во Вью — те же поля.

---

## Bursting Head Repair

Баг Blender 4+ и diffeomorphic-ригов: scale лицевых костей падает в 0 (драйверы).

Кнопка в **подготовке** и **студии**:
- удаляет drivers на `pose.bones[...].scale`
- ставит scale = 1
- чинит **Copy Scale** constraints на родительских костях лица/головы

---

## Как сказать Вью, что не так

**Заметка** + **Заметка для Вью** → `Lab\Creatures\Studio\reports\<slug>_issue.json` + viewport PNG → **Синхр. студии**.

---

## Шаня

Для студии: `Lab\Models\CascadeurReady\Shanya.fbx` (тело, не rig-.blend с WGT).

---

## Interaction

Когда **Скрины ок** и есть `<slug>_ready.fbx`:

1. **Сцена: blocking**
2. **Сцена: master ref**
