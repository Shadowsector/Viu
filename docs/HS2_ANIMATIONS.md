# Анимации из Honey Select 2

Цель: довести движения из HS2 до **одного FBX в Inbox** → «Принять анимацию» → Unity / `animation_catalog`.

## Два пути

### A. FBX из MeshExporter / Studio (рекомендуется)

1. Экспортируй анимацию с скелетом в FBX.
2. Положи в `U:\Anabarra\Library\HS2\fbx_dump\` (или `VIU_HS2_FBX_DUMP`).
3. В GUI: **Unity — анимации → «0b. HS2 — выдернуть анимации»** → **FBX дамп → Inbox**.
4. **«Принять анимацию (Inbox)»** — по одному файлу.

Имена файлов подсказывают slug каталога (`sit_idle`, `walk`, …).

### B. Ретаргет на Mixamo (если Unity не ест HS2-скелет)

1. Положи `Mixamo_XBot.fbx` (или `X Bot.fbx`) в `Library\HS2\` или задай `VIU_HS2_RETARGET_RIG`.
2. HS2 FBX в `fbx_dump`.
3. В окне HS2: **Ретаргет (Blender)** — нужен Blender (`VIU_BLENDER_EXE`).
4. Результат копируется в `Inbox\animations\`.

### C. Скан abdata (список клипов в игре)

Для каталога «что есть в игре», без автоматического FBX:

```text
set VIU_HS2_ROOT=...\Honey Select 2
pip install UnityPy
hs2_anim_scan
```

Кэш: `Library\HS2\animation_scan.json`. Экспорт JSON одного клипа: `hs2_anim_export_json clip_name=...`.

Прямой bake abdata → FBX без Blender пока не поддерживается — используй A или MeshExporter.

## Инструменты агента

| Инструмент | Действие |
|------------|----------|
| `hs2_anim_status` | пути, UnityPy, риг |
| `hs2_anim_scan` | список AnimationClip |
| `hs2_anim_import_fbx` | дамп → Inbox |
| `hs2_anim_retarget` | Blender → humanoid → Inbox |
| `accept_animation_inbox` | как для Mixamo |

## Переменные окружения

| Переменная | Смысл |
|------------|--------|
| `VIU_HS2_ROOT` | Корень HS2 (папка с `abdata`) |
| `VIU_HS2_FBX_DUMP` | Папка FBX-дампа |
| `VIU_HS2_RETARGET_RIG` | Mixamo FBX для ретаргета |

## Связь с I2V

Скрины поз для MoCap — **«Эталоны I2V (HS2)»**; этот документ — про **скелетные анимации** в Unity.
