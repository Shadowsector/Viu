# PNG character cards — разбор зашитого JSON

Старые ассеты «карточек» персонажей: обычный PNG, внутри которого лежит
конфиг кастомизации (слайдеры лица, ID причёсок и т.п.).

## Где лежат примеры

`U:\TempUnityCard\` — несколько PNG от Дена для разбора формата.

## Инструмент Вью

```text
character_card_probe path=U:\TempUnityCard
```

Что делает:

1. Читает чанки `tEXt` / `zTXt` / `iTXt` (в т.ч. base64 JSON, как у `chara`)
2. Смотрит хвост **после `IEND`**
3. Если JSON не найден — грубый brace-scan по байтам файла
4. Пишет дампы в `.viu/character_cards_extract/*.json`
5. В отчёте — `summary_json` с ключами для Cursor

Код: `viu/character_card_png.py`, tool: `viu/tools/character_card_tool.py`.

## Дальше

После того как Вью прогонит probe и отдаст handoff/ключи JSON —
Cursor пишет класс-десериализатор под структуру данных Анабарры.
