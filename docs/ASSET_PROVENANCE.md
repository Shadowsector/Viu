# Provenance ассетов + Desktop Mascot

Канон для Дена и Вью. Связано с [`ANABARRA_FOLDERS.md`](./ANABARRA_FOLDERS.md), [`UNITY_PIPELINE.md`](./UNITY_PIPELINE.md).

## Три зоны (без изменений)

| Папка | Роль |
|-------|------|
| `U:\Viu` | программа |
| `U:\Anabarra` | игра + Inbox |
| `U:\Desktop Mascot` | **архив** — Вью **не** сканирует рекурсивно |

Workflow: нашёл в хламнике → скопировал **один** пак → Inbox → дальше пайплайн.

## Категории архива (top-level)

`Animations`, `Clothes`, `Cocks`, `Monsters`, `NS Animations`, `Props`, `Toys`, `Women`

Маршрут в Inbox:

| Категория | Inbox |
|-----------|--------|
| Women / Clothes / Monsters / Toys / Cocks | `Inbox/creatures/` |
| Animations / NS Animations | `Inbox/animations/` |
| Props | корень `Inbox/` |

## Provenance

Файл: `.viu/asset_provenance.json`

На пак достаточно одной карточки: `source`, `author`, `license`, `url`.

| Источник | Когда ок |
|----------|----------|
| Smutbase (CC0 / CC-BY / …) | да; смотри NC и **ND** |
| `mine` (Studio / Cascadeur / свой Blender) | да |
| Patreon | только с явной фразой автора «можно в свой проект» |

**CC BY-ND** (пилот Erisa): для личной Анабарры — ок; публично выкладывать модификацию нельзя.

## Пилот: Shanya / Erisa (RedEyes)

- URL: `https://smutba.se/project/f66e34d7-fcbb-4a26-861c-7cd4fd0ab2cc/`
- Лицензия: **CC BY-ND 4.0**
- Локально: `U:\Desktop Mascot\Women\…`
- Пайплайн: референс пропорций → Shrinkwrap на рабочее тело → Rigify → Unity (`UNITY_PIPELINE.md`)

## Инструменты Вью

```text
asset_archive_inventory          # top-level архива; или pack_dir= один пак
asset_archive_stage source=… category=Women
asset_provenance action=ensure_pilots
asset_provenance action=add id=… license=CC0 url=…
```

## Тесты

`pytest tests/test_asset_archive.py -q`
