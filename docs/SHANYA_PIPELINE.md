# Шаня: один пайплайн (тело + HS2-анимации)

Простыми словами: **не изобретаем второй Blender вручную**.  
Тело Шани идёт тем же полуавтоматом, что и существа.  
HS2 даёт **движения**, не заменяет Tracer как меш в игре.

Связано: [`CREATURE_STUDIO.md`](./CREATURE_STUDIO.md), [`UNITY_PIPELINE.md`](./UNITY_PIPELINE.md),  
[`HS2_ANIMATIONS.md`](./HS2_ANIMATIONS.md) (ветка PR #66), [`NOW.md`](./NOW.md).

---

## Где мы съехали

Сделали чеклист «открой Blender сам» — а во Вью уже есть:

- **1. Очистить модель** — текстуры pack + prepared.blend  
- **3. Фото роста и эталон** — рост ~1.7 м, скрины, **эталон FBX**  
- **`blender_export_shanya`** — FBX без WGT  

И отдельно (PR #66): выдирание **анимаций** из HS2 → Inbox → Animator.

---

## Две фазы (не смешивать)

```
ФАЗА A — ТЕЛО (сейчас)
  Tracer (Beerware) → prep/текстуры → рост → риг-check → FBX → Unity Humanoid

ФАЗА B — ДВИЖЕНИЯ (после того как тело играет)
  HS2 клипы → fbx_dump → (ретаргет) → Inbox/animations → каталог → Animator
```

Comfy / Cascadeur MoCap — по-прежнему **на паузе**, пока тело не стоит в оверлее.

---

## Фаза A — тело Tracer = «существо slug=shanya»

Клади пак как обычное существо:

```text
U:\Anabarra\Inbox\creatures\shanya\
  (главный .blend Tracer + textures / скины по README пака)
```

| Шаг | Кнопка Вью | Что делает |
|-----|------------|------------|
| A0 | (чат) `asset_provenance ensure_pilots` | карточка Beerware |
| A1 | **Blender — существа → 1. Очистить модель** | pack текстур, prepared.blend |
| A2 | *(по желанию)* Shrinkwrap на HS2-лекало | только форма; HS2 **не** в Unity |
| A3 | **3. Фото роста и эталон** | рост humanoid ~1.70 м, скрины, `_ready.fbx` |
| A4 | `rig_check` (риг пака уже есть) | без нового Rigify |
| A5 | эталон FBX + `blender_export_shanya` при необходимости | → `Assets/Characters/Shanya/` |
| A6 | Unity Humanoid + копия в `Lab/Models/CascadeurReady/Shanya.fbx` | эталон роста для **других** существ |
| A7 | **▶ Запустить тестовую сцену** | проверка |

Wardrobe (одежда) для Шани — позже, не блокирует первый Play.

«Запечь текстуры» в нашем каноне = **упаковать / перепривязать** в prep  
(`texture_manifest.json`), не обязательно UV-atlas bake.

---

## Фаза B — анимации из HS2 (PR #66)

Когда Шаня уже Humanoid в Unity:

1. Смержить #66, обновить Вью.  
2. Экспорт клипа из HS2 (MeshExporter/Studio) → `Library\HS2\fbx_dump\`.  
3. Кнопка **«HS2 — выдернуть анимации»** → Inbox.  
4. Если скелет не стыкуется с Tracer — **ретаргет** на Mixamo X Bot (Blender).  
5. Принять анимацию → Animator (Idle первым).

Скан `abdata` — справочник «что есть в игре», не замена FBX-дампа.

HS2-**карта персонажа** как меш в билде — нет. Только лекало или источник клипов.

---

## Что взять из «того и другого»

| Из конвейера существ | Из HS2 (#66) | Из чеклиста body_pipeline |
|----------------------|--------------|---------------------------|
| prep, рост, эталон FBX | клипы → Inbox → Unity | простые подсказки «что жать» |
| texture pack | ретаргет на humanoid | provenance Tracer Beerware |
| один slug `shanya` | каталог slug’ов анимаций | reset/set шагов |

Оптимум: **body_pipeline = дирижёр кнопок существ**, а не параллельный ручной Blender.

---

## Порядок работ

1. Прогнать Tracer через **prep → студия (рост) → FBX → Humanoid → оверлей**.  
2. Положить `Shanya.fbx` в CascadeurReady (эталон для монстров).  
3. Влить #66 → первый Idle/Walk с HS2.  
4. Потом остальные существа тем же prep/студия; анимации — по каталогу.
