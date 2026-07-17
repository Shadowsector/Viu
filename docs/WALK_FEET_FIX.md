# Починка стоп Шани при ходьбе

**Симптом:** ноги «заплетаются», стопы странно **подворачиваются** (не «бежит слишком быстро»).  
**Скорость анимации тут ни при чём** — это кривой **retarget Humanoid** или неверный клип/Avatar.

---

## Почему так бывает

Unity переносит позу с Mixamo-скелета на Эрису через **muscle space**. Если:

- у клипа Avatar = чужой / Copy From Erisa на Mixamo-файл, или  
- у модели Avatar криво смаплены **Left/Right Foot / Toes**, или  
- в Walk крутится **Run** с чужой постановкой стоп,

то пальцы и щиколотки «ломаются» даже на нормальной скорости.

---

## Шаг A — диагностика (2 минуты)

1. Открой Unity → `OverlayDesktop` → выдели Шаню.
2. Inspector → **Animator**:
   - **Avatar** = `Shanya_Erisa…Avatar` (от **модели**, не от клипа).
   - Controller = `Shanya_Overlay_Locomotion` (или как у тебя называется overlay ctrl).
3. Project → найди файл, который в Walk (часто `Shanya_Run.fbx` или `X Bot@…`).
4. Выдели **этот FBX** → Inspector → **Rig**:
   - Animation Type = **Humanoid**
   - Avatar Definition = **Create From This Model** (не Copy From Other Avatar)
5. Нажми **Configure…** на клипе:
   - зелёные кости стоп? если красные / Missing — вот причина.

---

## Шаг B — правильный Walk с Mixamo (основной фикс)

1. [mixamo.com](https://www.mixamo.com) → персонаж **любой Female** (или X Bot — не важно, Without Skin).
2. Поиск: **`Female Walk`** или **`Walking`** (не Jog, не Run).
3. Скачать:
   - Format: **FBX Binary**
   - Skin: **Without Skin**
   - Frames: 30 или 60
   - **In Place** — включи, если есть галка (шаги на месте).
4. Переименуй файл в:  
   `U:\Viu\Inbox\Shanya_Walk.fbx`
5. Вью → **«Принять анимацию (Inbox)»**  
   - slug/state: **walk** / Walk  
   - scope: **Девушки-biped (Шаня + NPC)**
6. Вью → **«Обновить аниматор»** (или `unity_sync_animations`).
7. Проверь `Assets/Characters/Shanya/Animations/viu_clips.json`:

```json
"overlay_preferred": {
  "Idle": "X Bot@Idle.fbx",
  "Walk": "Shanya_Walk.fbx"
}
```

8. Пересобери оверлей / Play → A/D.

Если стопы **всё ещё** ломаются → шаг C.

---

## Шаг C — Avatar модели (стопы Эрисы)

1. Project → `Shanya_Erisa*.fbx` (тело) → Rig → Humanoid → **Configure**.
2. Вкладка **Mapping** / Body:
   - **Left Foot**, **Right Foot**, **Left Toes**, **Right Toes** должны быть назначены (зелёные).
3. Pose → **Enforce T-Pose** / Reset, если кости стоп развернуты на 90°.
4. **Done** → Apply.
5. На объекте Шани в сцене: Animator.Avatar = этот же Avatar заново (перетащить).
6. Play снова.

Типичный баг DAZ/Erisa: **Toes** пустые или Foot смотрит не туда → Unity крутит ankle «через себя».

---

## Шаг D — доводка в Cascadeur (если A–C не хватило)

Когда эталон Шани уже в CascadeurReady / сцене:

1. Import `*_cascadeur.fbx` или твой эталон.
2. Quick Rigging → Generate (если ещё нет).
3. Импортируй **анимацию** Walk (preset Animation) **на этот же скелет**  
   или нарисуй/MoCap короткий цикл.
4. На кадрах контакта с «полом»: выровняй стопу (плоскость стопы параллельна полу, без roll внутрь).
5. Export FBX → `U:\Anabarra\Animations\Shanya_Walk.fbx`
6. Sync в Viu.

---

## Чего не делать

| Нельзя | Почему |
|--------|--------|
| Copy From Other Avatar (Erisa → Mixamo clip) | Ломает Hips/Torso, стопы едут |
| Оставить Run в Walk «навсегда» | Другая постановка стопы |
| Править только `animator.speed` | Ты прав — к подвороту не относится |
| Класть клип-FBX как тело в сцену | T-pose / полный развал |

---

## Критерий «ок»

В профиль: пятка→носок, стопа не уходит внутрь на 45°, колени не «целуются».  
Если Idle нормальный, а Walk ломает — виноват **клип/retarget Walk**, не модель целиком.
