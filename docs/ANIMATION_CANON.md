# Канон анимаций: клипы без Cascadeur-MoCap, Cascadeur = полировка

**Статус:** канон с 2026-07-29 (решение Дена).  
**Связано:** `RIG_STANDARD.md`, `VIU_DIRECTION.md`, `INTERACTION_PIPELINE.md`, `SHANYA_ANIMATIONS.md`, `notes/OPEN_ANIMATION_STACK.md`.

---

## Одна строка

Анимацию **сначала** получаем на канон-риге (библиотека / ключи / Control Pose).  
**Cascadeur** — только полировка уже живого клипа на **чистом** канон-теле.  
Video MoCap Cascadeur **не** блокер и не единственный источник скелета.

---

## Два рига, не один на всех

| Класс | Канон | Клипы |
|-------|--------|--------|
| Бипеды (Шаня, гоблины, NPC) | **один Unity Humanoid** (AccuRIG → FBX Unity *или* Mixamo-совместимый) | общий пул Mixamo / ActorCore / Blender keys |
| Четвероногие (волк…) | **отдельный quad-шаблон** | свои walk/idle; Control Pose по маркерам |
| Слизни / хвост / щупальца | не Humanoid | blendshapes / secondary / ключи |

Волк на Mixamo-скелет «чтобы один риг» — **не делаем**.  
Шаня-галоп на четырёх — **отдельные клипы** на biped-риге (см. `notes/SHANYA_QUADRUPED_SPRINT_RIG.md`), не смена скелета навсегда.

В Cascadeur / `CascadeurReady` кладём **только** канон-FBX (без WGT), не сырой Inbox.

---

## Конвейер

```
Inbox mesh
  → (опц.) правка лица — см. ниже
  → AccuRIG / Mixamo auto-rig  →  канон FBX
  → клипы: Mixamo · ActorCore · blender_make_anim · CP (quad)
  → (опц.) Cascadeur: Unbake + AutoPhysics + правки
  → Unity Humanoid / Animator + граф каталога
```

Comfy остаётся: дыры графа, рефы, шоу-дубли, FaceRefs.  
**Не** ждём «MoCap с mp4 на кривой модели».

### Control Pose (как в interaction)

Для quad и контактов: isolated ref / маркеры → ключи на quad-риге  
(Blender или Cascadeur Point/AutoPosing) → assembly.  
Это фаза 4 `INTERACTION_PIPELINE.md`, не Video MoCap.

---

## Веса (skin weights) — когда заново

| Действие | Веса |
|----------|------|
| Только `rig_apply` (переименовать кости) | **Не** перерисовываем — группы едут с костями |
| AccuRIG / новый скелет + bind | **Авто-веса** заново; руками только проблемные зоны |
| Transfer Weights со старого похожего рига | Часто хватает + точечные правки |
| Retarget клипа на уже skinned меш | Веса **не** трогаем |

Ручная карта «с нуля» почти не нужна.

---

## Лица: чуть симпатичнее (до бинда)

**Стоит**, если герой (Шаня / Вью-меш), **узко**, до финального AccuRIG.

1. Найти лицо-донор (похожий силуэт головы, A/T-pose рядом).
2. Vertex group только **лицо** (нос–скулы–подбородок; не шея целиком).
3. Shrinkwrap / Surface Deform с **низким factor** (~0.3–0.6), не «половина тела».
4. Проверить UV и шов шеи; приплыли текстуры — откат / sculpt вместо wrap.
5. Потом канон-риг (один раз авто-веса).

**Не стоит:** полный shrinkwrap на HS2-лекало как игровой меш  
(уже в `body_pipeline`: в Unity не едет).  
Для Comfy-лиц — по-прежнему `Lab/FaceRefs` + ReActor, это другой канал.

---

## Инструменты (рабочие)

| Шаг | Инструмент |
|-----|------------|
| Auto-rig biped | **AccuRIG 2** (бесплатно) → export Unity FBX |
| Библиотека motion | Mixamo + ActorCore (через AccuRIG) |
| Ключи / простые клипы | Blender (`blender_make_anim` …) |
| Quad / контакты | Control Pose + markers |
| Полировка | Cascadeur на каноне |
| Имена костей Unity | `rig_check` / `RIG_STANDARD.md` |

Previz Inbox: Mesh2Motion — ок для пробы, не финал.  
WHAM / 4D-Humans — пилот позже, не wave 1.

---

## Чеклист wave 1 (biped)

1. [ ] Эталон biped в `CascadeurReady` / Unity Humanoid (Шаня или AccuRIG-канон).
2. [ ] (Опц.) лёгкая правка лица до бинда.
3. [ ] Wave 1 клипы с Mixamo/ActorCore по `SHANYA_ANIMATIONS.md` — без Cascadeur MoCap.
4. [ ] Cascadeur только если клип уже играет и нужна физика/контакт.
5. [ ] Quad: один шаблон волка; CP, не Humanoid retarget.
