# Viu ↔ Cascadeur

Шаг 3 дорожной карты: правка FBX-анимаций между Blender/Mixamo и Unity.

## Пути

| Папка | Назначение |
|-------|------------|
| `U:\Anabarra\Library\Cascadeur\Inbox\` | FBX положить сюда → открыть в Cascadeur |
| `U:\Anabarra\Library\Lab\Models\CascadeurReady\` | **Чистые FBX** после batch export из Blender |
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

**Commands → Reload scripts** (не Reload commands!) → **Viu.Lab Import**.

Проверка: **cascadeur_status** в чате Вью.

## Workflow

1. `.blend` в `Lab/Models/Inbox` (или Cascadeur Inbox)
2. **Batch export:** чат `blender_export_cascadeur_batch` → `CascadeurReady/*_cascadeur.fbx` (без WGT, deform bones)
3. Import в Cascadeur (Scene preset) — lab берёт FBX из CascadeurReady
4. Правка в Cascadeur (Den)
5. Export → `U:\Anabarra\Animations`
6. Вью: **Обновить аниматор** (Unity закрыт)

Авто-запуск Cascadeur из Вью — **лаборатория** (см. [VIU_LAB.md](./VIU_LAB.md)): окно на 3-м мониторе, скрины, journal, оценки.

## Клип из Blender → Cascadeur

Вью может сделать **простой** клип в Blender и сразу отправить в Cascadeur на полировку:

| Инструмент | Что делает |
|------------|------------|
| `blender_make_anim` | Action на арматуре: `idle`, `wave`, `nod`, `look_left`, `look_right`, `stretch` |
| `blender_export_cascadeur_anim` | FBX с `bake_anim` (без WGT) |
| `blender_anim_to_cascadeur` | make → export → Inbox + LabImport `mode=animation` |

Пример в work-чате:

```text
blender_anim_to_cascadeur blend_file=U:\Anabarra\…\Shanya.blend preset=wave
```

Артефакты: `Library/Lab/Anims/BlenderOut/`, `Library/Lab/Anims/CascadeurReady/`.  
Это **не** финальная анимация — грубый ключ; физика и позы — в Cascadeur.
