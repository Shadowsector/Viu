# Viu ↔ Cascadeur

Шаг 3 дорожной карты: правка FBX-анимаций между Blender/Mixamo и Unity.

## Пути

| Папка | Назначение |
|-------|------------|
| `U:\Anabarra\Library\Cascadeur\Inbox\` | FBX положить сюда → открыть в Cascadeur |
| `U:\Anabarra\Animations\` | Export из Cascadeur → «Обновить аниматор» в Unity |

## Настройка

В `U:\Viu\.env`:

```env
VIU_CASCADEUR_EXE=C:\Program Files\Cascadeur\Cascadeur.exe
```

Проверка: в Telegram или чате — **cascadeur_status** (инструмент Вью).

## Workflow

1. Mixamo / Blender → FBX в `Library/Cascadeur/Inbox`
2. Правка в Cascadeur (Den)
3. Export → `U:\Anabarra\Animations`
4. Вью: **Обновить аниматор** (Unity закрыт)

Авто-запуск Cascadeur из Вью — позже; сейчас пути и статус.
