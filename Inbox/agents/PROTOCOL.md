# Канал work ↔ home

Две машины, один репозиторий. Прямых каналов нет: только git.

| Кто | Машина | Роль | Копия репозитория |
|---|---|---|---|
| `work` | рабочий ПК Дена | студия: UE 5.8, AnimLab, приёмка моделей и клипов | `C:\Viu` |
| `home` | домашний ПК | поставщик: исходники, модели, экспорт FBX | `U:\Viu` |

Язык сообщений — русский, коротко. Имена файлов и команд — латиницей.

## 1. Текст — ветка `main`

Папки:

- `Inbox/agents/requests/` — заявки;
- `Inbox/agents/replies/` — ответы;
- `Inbox/agents/receipts/` — подтверждения получения;
- `Inbox/agents/docs/` — небольшие документы, которые нужны другой стороне.

Имя файла: `YYYY-MM-DD_NNN_short-slug.md`, где `NNN` — порядковый номер за день.

Фронтматтер (обязательно):

```yaml
---
id: w-2026-10-23-001
from: work
to: home
kind: request
status: open
created: 2026-10-23T18:16:03+03:00
payload: payload/w-2026-10-23-000
---
```

- `from` / `to`: `work` или `home`.
- `kind`: `request`, `reply`, `receipt`, `note`.
- `status`: `open`, `done`, `failed`, `blocked`.
- `payload`: имя ветки с файлами, если есть.

Правила:

- Перед записью: `git pull --rebase`.
- В `main` никогда не делать `push --force`. Force-push допустим только в свою ветку `payload/*`.
- Один файл — одна тема. Секреты и токены не писать.
- После закрытия заявки текст можно удалить; `receipts/` не удаляем — это журнал.

## 2. Файлы — отдельная ветка на каждый пакет

Ветка: `payload/<id>`, где `<id>` = `w-...` (работа) или `h-...` (дом).
В командах ниже `C:\Viu` — рабочая копия; на домашней машине замени на `U:\Viu`, а `C:\viu_staging` — на `U:\viu_staging`.

В ветке лежит только:

```text
payload/
  manifest.json
  <файлы и папки пакета>
```

`manifest.json`:

```json
{
  "id": "h-2026-10-23-001",
  "from": "home",
  "created": "2026-10-23T18:20:00+03:00",
  "files": [
    {"path": "payload/ru/ru.fbx", "size": 123456, "sha256": "..."}
  ]
}
```

### Отправитель

```powershell
git -C C:\Viu pull --rebase
git -C C:\Viu switch -c payload/h-2026-10-23-001
# положить файлы в C:\Viu\payload\ и посчитать sha256
git -C C:\Viu add payload
git -C C:\Viu commit -m "payload h-2026-10-23-001"
git -C C:\Viu push -u origin payload/h-2026-10-23-001
git -C C:\Viu switch main
```

Затем пишет заявку/ответ в `main` и указывает ветку в `payload:`.

### Получатель

```powershell
git -C C:\Viu fetch origin payload/h-2026-10-23-001
New-Item -ItemType Directory -Force C:\viu_staging\h-2026-10-23-001
git -C C:\Viu archive --format=zip -o "$env:TEMP\payload-h-2026-10-23-001.zip" origin/payload/h-2026-10-23-001 payload
Expand-Archive -LiteralPath "$env:TEMP\payload-h-2026-10-23-001.zip" -DestinationPath C:\viu_staging\h-2026-10-23-001 -Force
Get-ChildItem -LiteralPath C:\viu_staging\h-2026-10-23-001 -Recurse -File | Get-FileHash -Algorithm SHA256
```

Сверить хэши с `manifest.json`, распаковать в рабочую папку и написать receipt.

### Закрытие

После успешного receipt отправитель удаляет ветку:

```powershell
git -C C:\Viu push origin --delete payload/h-2026-10-23-001
```

Файлы живут только до подтверждения. Если ветку удалили раньше — попросить перезалить.

## 3. Receipt

Файл `Inbox/agents/receipts/<id>.md`:

```yaml
---
id: h-2026-10-23-001
from: work
to: home
kind: receipt
status: done
created: 2026-10-23T18:40:00+03:00
---
```

В теле: совпали ли sha256, куда распаковано, что импортировано, какие проблемы.

## 4. Лимиты и оговорки

- GitHub: файл ≤ 100 МБ, один push ≤ 2 ГБ. Больше — бить на части или zip.
- Git LFS не используем.
- Бинарники в `main` не коммитим; `Inbox/` остаётся человеческой папкой (она в `.gitignore`).
- Если пакет не нужен после приёмки — удаляем и локальную копию в `C:\viu_staging`.
