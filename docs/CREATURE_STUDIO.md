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

Окно **Разметить существ** во Вью — по-прежнему есть для быстрой правки без Blender.

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
