# Установка Viu на Windows (zip)

## Почему 404 на ссылках?

Репозиторий **Shadowsector/Viu** сейчас **приватный**.  
`raw.githubusercontent.com` и автоскачивание **не работают без токена**.

Варианты:
1. **Сделать репозиторий Public** (Settings → Danger zone → Change visibility) — тогда автоапдейт заработает сам.
2. Или задать токен: `set VIU_GITHUB_TOKEN=ghp_...` (read repo).

## Установка из zip (сейчас)

1. GitHub → Viu → Code → Download ZIP (ветка `cursor/viu-agent-core-65c2`)
2. Распакуй в `U:\Viu` (чтобы был `U:\Viu\Viu.cmd`)
3. **Двойной клик `Viu.cmd`** — не `start_viu.bat`, не другие bat.

Если ошибка — запусти **`diagnose.bat`**, пришли весь текст окна.

## Один файл для запуска

| Файл | Назначение |
|------|------------|
| **Viu.cmd** | Запуск (главный) |
| **diagnose.bat** | Диагностика, окно не закрывается |
| Остальные .bat | Ведут на Viu.cmd или diagnose |

## После первого успешного запуска

- Ярлык: `make_shortcut.bat`
- Обновление (если repo public): `update_viu.bat`
- Или в окне Viu: **Обновить Viu**
