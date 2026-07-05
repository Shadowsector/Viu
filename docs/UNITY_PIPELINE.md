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

1. Console → **красные CS** (скрипты) — исправить или удалить `TutorialInfo`  
2. Console → **Rig Error** — Create From This Model на анимации  
3. **▶ Play** смотреть вкладку **Game**, не Scene  
4. Лишняя одежда выключена в Hierarchy  
5. Animator: Controller + Avatar модели  

## Переменные окружения

| Переменная | Назначение |
|------------|------------|
| `VIU_UNITY_PROJECT` | Путь к корню Unity-проекта (где папка `Assets`) |
