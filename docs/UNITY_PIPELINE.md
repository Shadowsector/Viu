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

На персонаже в сцене:

- **Animator → Avatar** = `Shanya_ErisaAvatar` (от модели)  
- **Animator → Controller** = твой Animator Controller  

## Проверка через Viu

```bat
set VIU_UNITY_PROJECT=C:\Users\Den\Anabarra\Unity\My project
check_unity.bat
```

Или в GUI:

> «Сделай unity_report и скажи, почему не работает Play»

Инструменты: `unity_log`, `unity_scan`, `unity_workflow`, `unity_report`.

## Play не работает — чеклист

### «All compiler errors have to be fixed before you can enter playmode!»

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
