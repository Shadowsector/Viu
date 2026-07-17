# Unity — пайплайн Шани (Анабарра)

Простой маршрут от Blender до первой анимации в Unity.

## Где мы сейчас (типичный прогресс)

1. ✅ `Shanya_Erisa.blend` — модель, outfit, rig_map  
2. ✅ Export FBX → `Assets/Characters/Shanya/`  
3. ✅ Unity Humanoid Configure на модели  
4. 🚧 Mixamo Idle + Animator Controller + Play  

## WGT-предупреждения (жёлтые)

Сообщения вида:

`Can't calculate tangents, because mesh 'WGT-rig_…' doesn't contain normals`

Это **виджеты рига Blender** (кружки/кубики для аниматора). В игру они **не нужны**.

**Не блокируют Play**, но засоряют Console.

### Исправление (в Blender, перед следующим FBX)

1. Outliner → найти меши **`WGT-*`**, **`Circle`**, **`Sphere`** (виджеты).  
2. Скрыть или удалить (не трогая Body и одежду).  
3. Переэкспорт FBX.

### Быстро в Unity (без переэкспорта)

Hierarchy → раскрыть `Shanya_Erisa` → снять галочки со всех **`WGT.*`** объектов.

## Mixamo + Humanoid

| Файл | Rig |
|------|-----|
| Модель `Shanya_Erisa*.fbx` | Humanoid → **Create From This Model** |
| Анимация `X Bot@Idle.fbx` | Humanoid → **Create From This Model** |

**Никогда** Copy From Other Avatar между Mixamo и Эризой.

> **Overlay baseline (rev37):** прозрачность и пины Idle/Walk зафиксированы в [`OVERLAY_BASELINE.md`](OVERLAY_BASELINE.md) — не откатывать ColorKey-only и не ломать `X Bot@Idle` + `Shanya_Run` как Walk.

На персонаже в сцене:

- **Animator → Avatar** = `Shanya_ErisaAvatar` (от модели)  
- **Animator → Controller** = твой Animator Controller  

## Автонастройка Шани (новое в Viu)

После импорта FBX в чистый проект **6.3 LTS**:

### Вариант A — через меню Unity

1. **`setup_shanya.bat`** или **`unity_init_project`** (manifest + Editor-скрипты).
2. Импорт FBX → Humanoid Configure на модели.
3. Меню **Viu → Setup Shanya (Idle)**.
4. Outfit: **Viu → Outfit → Dressed / Swimsuit / Shower**.
5. **`unity_verify`** — проверка по логам.

### Экспорт из Blender

```bat
python -m viu tool blender_export_shanya --blend_file "U:\...\Shanya_Erisa.blend"
```

Скрывает WGT/Circle/Sphere, экспортирует Mesh+Armature без bake animation.

### Вариант A2 — через меню Unity (подробно)

1. В Viu или вручную: положи Editor-скрипт — инструмент **`unity_deploy_setup`**
   (или `python -m viu tool unity_deploy_setup`).
2. Открой Unity → дождись компиляции.
3. Меню **Viu → Setup Shanya (Idle)** — создаст Animator Controller, повесит Idle,
   отключит WGT.* в сцене.

### Вариант B — batchmode (Unity **закрыт**)

```bat
set VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
set VIU_UNITY_EXE=C:\Program Files\Unity\Hub\Editor\6000.3.19f1\Editor\Unity.exe
python -m viu tool unity_run_setup
```

### Safe Mode из-за пакетов

Инструмент **`unity_fix_manifest`** убирает Input System и AI Navigation из
`Packages/manifest.json` (Unity закрыт), затем открой проект снова.

## Проверка через Viu

```bat
cd U:\Viu
set VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
check_unity.bat
```

Или в GUI:

> «Сделай unity_report и скажи, почему не работает Play»

Инструменты: `unity_log`, `unity_scan`, `unity_workflow`, `unity_report`, `unity_scan_animations`, `unity_sync_animations`.

## Автоскан анимаций (новое)

Папка для клипов:

```
Assets/Characters/Shanya/Animations/
  X Bot@Idle.fbx
  X Bot@Walking.fbx
  Shanya_Idle_Stand.controller   ← создаётся автоматически
  viu_clips.json                 ← опционально, для непонятных имён
```

### Как работает

1. **`unity_deploy_setup`** или **`unity_init_project`** — копирует `ShanyaAnimationSync.cs`, `ShanyaLocomotion.cs`, `viu_clips.json`.
2. Кладёшь FBX в `Animations/` → если Unity **открыт**, `AssetPostprocessor` вызывает **Viu → Sync Animations** автоматически.
3. Если Unity **закрыт** — **`unity_sync_animations`** (batchmode) или `VIU_UNITY_AUTO_SYNC=1` + watcher в GUI.
4. Имена: `Idle`, `Walk`, `Run` в имени файла; иначе — запись в `viu_clips.json`:
   ```json
   { "overrides": [{ "file": "Take 001.fbx", "state": "Walk" }] }
   ```
5. На персонаже: **ShanyaLocomotion** (A/D → параметр `Speed`, Idle ↔ Walk). **Setup Shanya** добавляет его сам.

### Переменные окружения

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `VIU_UNITY_PROJECT` | — | Корень Unity-проекта |
| `VIU_ANIM_SCAN_SEC` | `300` | Интервал фонового скана в GUI |
| `VIU_UNITY_AUTO_SYNC` | `0` | `1` = batch sync при новых FBX (Unity закрыт) |

## Play не работает — чеклист

### Ошибки в NavMeshLinkEditor / InputActionMapDrawer / AnimatorBindingCache

Это **не твои скрипты** и **не Шаня** — это сломались **пакеты Unity**
(AI Navigation, Input System, Animator). Часто после обновления редактора или битой папки `Library`.

**Быстрый путь для проверки анимации (рекомендуем):**

1. **File → New Project → Universal 3D** (новый чистый проект, другое имя, напр. `AnabarraTest`).
2. Импорт только `Shanya_Erisa.fbx` + Mixamo Idle + Animator — **без лишних пакетов**.
3. Play там — если работает, старый проект можно починить или забросить.

**Починка текущего проекта:**

1. Закрой Unity.
2. Удали папку **`Library`** в корне проекта (Unity пересоберёт при открытии — 5–15 мин).
3. Открой проект снова.
4. **Window → Package Manager** → обнови **Universal RP**, **Input System**, **AI Navigation**.
5. Удали **`Assets/TutorialInfo`** если есть.

**Если NavMesh не нужен сейчас:** Package Manager → **AI Navigation** → Remove.

### Как прислать все ошибки Viu

```bat
cd U:\Viu
set VIU_UNITY_PROJECT=U:\Anabarra\Unity\Anabarra
check_unity.bat
```

Пришли файл **`U:\Viu\unity_report.txt`** — там будут вердикт и все CS-ошибки из Editor.log.

Или в Unity Console: кнопка **Clear**, потом **Copy** (правый верхний угол Console) — вставь в чат.


**Это не анимация и не Rig.** Unity не компилирует C#-скрипты.

1. **Window → General → Console** (Ctrl+Shift+C).
2. Кликни **красную** строку с `error CS####` — откроется файл.
3. **Частый фикс в новом URP-проекте:** удали папку **`Assets/TutorialInfo`** целиком
   (ПКМ → Delete). Unity перекомпилирует — Play заработает.
4. Если ошибка в **твоём** скрипте — поправь или удали его.

Пока эта красная ошибка есть, **анимация не проверится** — Play просто не запускается.

### После того как Play заработал

1. Console → нет Rig Error  
2. **▶ Play** → вкладка **Game**  
3. Animator: Controller + Avatar модели  
4. Лишняя одежда и WGT.* выключены в Hierarchy  

## Переменные окружения

| Переменная | Назначение |
|------------|------------|
| `VIU_UNITY_PROJECT` | Путь к корню Unity-проекта (где папка `Assets`) |

## Desktop overlay (Anabarra)

Рабочий baseline **rev37** (прозрачность + анимации) — [`OVERLAY_BASELINE.md`](OVERLAY_BASELINE.md).  
Не возвращать ColorKey-only; не менять chroma на `#FF00FF`.
