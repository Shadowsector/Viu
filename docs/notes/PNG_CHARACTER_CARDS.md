# PNG character cards — 【AIS_Chara】 + ассеты

## Папки (создаёт `character_card_setup`)

| Путь | Зачем |
|------|--------|
| `U:\Anabarra\Inbox\ais_cards\` | PNG-карточки |
| `U:\Anabarra\Inbox\ais_assets\` | россыпь ассетов (fbx/zip/png/…) |
| `U:\Viu\.viu\character_cards_extract\` | JSON после десериализации |

## Процесс

1. **Обновить Вью** + `pip install msgpack`
2. `character_card_setup copy_from=U:\TempUnityCard` — папки + копия карточек  
   (или кинь PNG руками в `ais_cards/`)
3. `character_card_probe` — вытащит `*__anabarra.json` (слайдеры, hair_ids)
4. Скинь вразнобой ассеты в `ais_assets/`
5. `character_card_match json=…\AI_002103__anabarra.json` — поиск по ID/имени

## Инструменты

| Tool | |
|------|--|
| `character_card_setup` | папки + README (+ copy_from) |
| `character_card_probe` | каталог PNG → JSON |
| `character_card_deserialize` | один PNG |
| `character_card_match` | JSON → кандидаты в ais_assets |

Матчинг эвристический: `hair_ids` / числа в имени файла / токены имени / kkex / имена внутри zip.  
Это не «собери модель», а **найти что похоже** из кучи файлов.

## Формат карточки

PNG + MessagePack после IEND, маркер `【AIS_Chara】`. См. `viu/ais_chara.py`.
