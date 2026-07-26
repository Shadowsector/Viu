# PNG character cards — 【AIS_Chara】

Лог Вью (`png-char-cards-probe-20260726b`, 2026-07-26): в `U:\TempUnityCard`
**40 PNG**, данные **после IEND**, маркер `【AIS_Chara】` + MessagePack.

Это карточки AI★Girl / Illusion (семейство Koikatsu), **не** JSON в tEXt.

## Структура файла

```
[PNG preview 252×352]
[IEND]
product_no:int32
header:len(b) + 「【AIS_Chara】」
version:len(b) + 「1.0.0」
face_thumb:len(i) + bytes
lstInfo:len(i) + MessagePack { lstInfo: [{name,version,pos,size},…] }
payload:len(q) + blocks…
```

Блоки: `Custom`, `Coordinate`, `Parameter`, `Status`, `Parameter2`, `GameInfo*`, `KKEx`, …

`Custom` = три MessagePack подряд (face / body / hair), у face — `shapeValueFace` (слайдеры).

## Код Вью

| Модуль | Зачем |
|--------|--------|
| `viu/ais_chara.py` | десериализатор → `AnabarraAppearance` |
| `character_card_probe` | каталог карточек |
| `character_card_deserialize` | один файл |

Зависимость: `pip install msgpack` (на машине Дена).

```text
character_card_probe path=U:\TempUnityCard limit=10
character_card_deserialize path=U:\TempUnityCard\AI_002103.png
```

Дампы: `.viu/character_cards_extract/*__anabarra.json`

## AnabarraAppearance

- `face_shape_values` — слайдеры лица  
- `body_shape_values` — тело  
- `hair_ids` / `hair_parts` — ID причёсок  
- `character_name`, `raw_parameter` — из Parameter  
- `face_detail` — прочие поля face без огромных массивов  

Ориентир формата: [KoikatuCharaLoader](https://github.com/great-majority/KoikatuCharaLoader).
