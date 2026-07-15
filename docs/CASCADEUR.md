# Viu ↔ Cascadeur

Шаг 3 дорожной карты: правка FBX-анимаций между Blender/Mixamo и Unity.

## Пути

| Папка | Назначение |
|-------|------------|
| `U:\Anabarra\Library\Cascadeur\Inbox\` | FBX положить сюда → открыть в Cascadeur |
| `U:\Anabarra\Library\Lab\Models\CascadeurReady\` | **Чистые FBX** после batch export из Blender |
| `U:\Anabarra\Library\Lab\Refs\kept\` | Comfy mp4 → Reference / MoCap |
| `U:\Anabarra\Library\Lab\Cascadeur\Refs\` | Staging копия видео для Cascadeur |
| `U:\Anabarra\Animations\` | Export из Cascadeur → «Обновить аниматор» в Unity |

## Настройка

В `U:\Viu\.env` (опционально — если exe лежит в стандартном месте, Вью найдёт сама):

```env
VIU_CASCADEUR_EXE=U:\Cascadeur\App\Cascadeur\cascadeur.exe
VIU_CASCADEUR_SCRIPTS=   # только если ScriptsDir в settings.ini нестандартный
```

Авто-поиск без `.env`: `U:\Cascadeur\App\Cascadeur\cascadeur.exe`, затем `Program Files\Cascadeur\`.

### Import FBX

Подробно: [CASCADEUR_IMPORT.md](./CASCADEUR_IMPORT.md).

Папка Python-команд:

```
U:\Cascadeur\App\Cascadeur\resources\scripts\python\commands\
```

**Commands → Reload scripts** (не Reload commands!) → **Viu.Lab Import** (FBX) /
**Viu.ImportReference** (видео) / **Viu.ExportClip** (FBX клип).

Проверка: **cascadeur_status** в чате Вью.

### Comfy → MoCap

См. [COMFY_CASCADEUR_PIPELINE.md](./COMFY_CASCADEUR_PIPELINE.md).

1. `comfy_mocap` → выбрать клип → авто `cascadeur_import_reference`
2. Cascadeur: **Viu → ImportReference** → Timeline → **Mocap**
3. `cascadeur_export_clip` → `Animations/shanya_<slug>.fbx` + catalog

## Workflow

1. `.blend` в `Lab/Models/Inbox` (или Cascadeur Inbox)
2. **Batch export:** чат `blender_export_cascadeur_batch` → `CascadeurReady/*_cascadeur.fbx` (без WGT, deform bones)
3. Import в Cascadeur (Scene preset) — lab берёт FBX из CascadeurReady
4. Правка в Cascadeur (Den)
5. Export → `U:\Anabarra\Animations`
6. Вью: **Обновить аниматор** (Unity закрыт)

Авто-запуск Cascadeur из Вью — **лаборатория** (см. [VIU_LAB.md](./VIU_LAB.md)): окно на 3-м мониторе, скрины, journal, оценки.
