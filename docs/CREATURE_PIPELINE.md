# План: существа → описание → MoCap → сцена

## Command R для сюжета (не про монстров)

В `U:\Viu\.env`:

```env
VIU_MODEL_REFLECT=viu-command-r
```

Перезапуск Вью → на кнопке **Дома · viu-command-r**.  
Для обычного чата/ERP верни `viu-cydonia`. Work/code не трогай.

Нужен тег: `create_viu_ollama_models.bat` (база `command-r` уже в Ollama).

---

## Пайплайн внешности монстра (зафиксировано)

Цель: у Вью в `creature_catalog.json` есть **скрин + EN-промпт + RU-описание**,
связанные с уже известным size_class / locomotion / ростом — чтобы понимать,
как анимировать и что кормить в Comfy.

```
[1] Inbox → scan → size/loco (уже есть)
[2] Lineup в Blender → нормализация роста (уже есть)
[3] Скрин front/side → PNG
[4] VL (llava) или позже Comfy WD14 → appearance_en / appearance_ru / tags
[5] Запись в каталог + status=ready
[6] Reflect видит блок «Существа (внешность…)» → лучше советует анимацию
[7] Позже: seed PNG → Comfy I2V/T2V клипы под MoCap
```

### Сейчас в коде

| Шаг | Статус |
|-----|--------|
| Scan / size / lineup | ✅ |
| Поля `photo_*`, `appearance_en/ru/tags` | ✅ |
| `creature_describe` (Ollama VL по PNG) | ✅ |
| Inject в reflect notes | ✅ |
| Авто-рендер front/side после lineup (Blender → Processed) | ✅ |
| Comfy WD14 / Interrogator workflow | ⏳ (тот же schema) |
| Авто seed → MoCap клип | ⏳ (шаг 7) |

### Как пользоваться (v1)

1. Разметить рост (`Разметить существ` / lineup).
2. **«Линейка существ»** — после Blender в каталоге появятся `photo_front` / `photo_side`  
   (`Lab/Creatures/Processed/<slug>/front.png`, `side.png`).  
   Ручной скрин по-прежнему можно положить туда же.
3. В чате Вью / tool:

```text
creature_describe query=Goblin image=U:\...\front.png
```

4. Проверить `.viu/creature_catalog.json` → `appearance_en`, `appearance_ru`.
5. Обсуждать анимацию — Вью подтянет описание в заметки.

### Почему не сразу Comfy img2prompt

Ollama **llava** уже стоит; WD14 в Comfy — отдельный workflow + ноды.
Схема каталога одна: потом `creature_describe` сможет звать Comfy вместо VL,
поля те же.

### Дальше по приоритету

1. Кнопка «Описать» в GUI разметки существ.
2. Comfy caption node (опционально).
3. MoCap seed из `photo_front` (шаг 5–7 старого плана).

Старый чеклист morphs / genital / сокеты — ниже без изменений смысла.

**Совместные анимации (multi-actor):** см. `docs/INTERACTION_PIPELINE.md`, `docs/INTERACTION_SETUP.md` (куда класть FBX).

---

## Чеклист после линейки (как было)

1. Добить разметку (класс + рост).
2. Инвентаризация morphs.
3. Аккуратная нормализация (без bake shape keys).
4. Genital / NSFW-риг.
5. A-pose фото → описание (↑) → потом Comfy клипы.
6. Сокеты на девушках (Unity).
