# Viu ↔ Cascadeur

Шаг 3 дорожной карты: правка FBX-анимаций между Blender/Mixamo и Unity.

## Пути

| Папка | Назначение |
|-------|------------|
| `U:\Anabarra\Library\Cascadeur\Inbox\` | FBX положить сюда → открыть в Cascadeur |
| `U:\Anabarra\Animations\` | Export из Cascadeur → «Обновить аниматор» в Unity |

## Настройка

В `U:\Viu\.env` (опционально — если exe лежит в стандартном месте, Вью найдёт сама):

```env
VIU_CASCADEUR_EXE=U:\Cascadeur\App\Cascadeur\cascadeur.exe
VIU_CASCADEUR_SCRIPTS=   # опционально — папка Commands (user scripts)
```

Авто-поиск без `.env`: `U:\Cascadeur\App\Cascadeur\cascadeur.exe`, затем `Program Files\Cascadeur\`.

### Import FBX из lab

Вью кладёт `viu_lab_import.py` в папку user-команд Cascadeur и пишет `viu_lab_pending.json` с путём FBX.
В Cascadeur: **Commands → Reload scripts → Viu.Lab Import** (или File → Import после `os.startfile` на FBX).

Проверка: в Telegram или чате — **cascadeur_status** (инструмент Вью).

## Workflow

1. Mixamo / Blender → FBX в `Library/Cascadeur/Inbox`
2. Правка в Cascadeur (Den)
3. Export → `U:\Anabarra\Animations`
4. Вью: **Обновить аниматор** (Unity закрыт)

Авто-запуск Cascadeur из Вью — **лаборатория** (см. [VIU_LAB.md](./VIU_LAB.md)): окно на 3-м мониторе, скрины, journal, оценки.
