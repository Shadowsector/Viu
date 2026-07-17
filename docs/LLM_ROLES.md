# Модели Ollama для Вью (роли)

Сейчас в окне Ollama / `VIU_MODEL` — **одна** модель по умолчанию.  
Можно задать **разные** теги по роли — Вью подставляет их **на каждый запрос** (не «переключает навсегда» после первого сообщения).

## `.env`

```env
VIU_PROVIDER=openai
VIU_BASE_URL=http://127.0.0.1:11434/v1
VIU_API_KEY=ollama
VIU_MODEL=llama3.3:70b          # запасной / координация

# Опционально — роли (пусто = VIU_MODEL):
VIU_MODEL_REFLECT=dolphin-llama3:70b   # Telegram / живой чат / сюжет / NSFW-тон
VIU_MODEL_WORK=qwen2.5:32b             # «следующий шаг», lab, инструменты
VIU_MODEL_CODE=qwen2.5-coder:32b       # явные code/баг/скрипт в work
```

## Что сработает, что нет

| Идея | Вердикт |
|------|---------|
| Reflect = Dolphin, work = Qwen | **Да** — уже в коде |
| «Первым сообщением включила Dolphin навсегда» | Не нужно — роль выбирается **каждый** запрос |
| 4×70B одновременно в VRAM | **Нет** — Ollama будет выгружать/грузить, паузы |
| Vision-модель для «поговорим про визуал» | Отдельно: vision LLM ≠ чат; у нас глаза — `vision_observe` / Comfy |
| Авто-роутер «сюжет vs код» внутри Telegram | Пока нет; Telegram = reflect. Work — кнопки / «сделай» |

Практично: **две** модели (reflect + work), не четыре 70B.

## Что скачать (~70B / рядом)

| Роль | Модель | Зачем |
|------|--------|--------|
| Reflect / сюжет / тепло | `dolphin-llama3:70b` или abliterated Llama 3.3 70B | Меньше морали, живой тон |
| Reflect + русский | uncensored **Qwen 2.5/3 32–72B** | Часто чище язык, чем stock Llama |
| Work / агент | `qwen2.5:32b` или `72b` | Инструкции + инструменты |
| Code | `qwen2.5-coder:32b` | Правки скриптов, логи |
| Vision (глаза) | `llava` / `qwen2.5-vl` — **не** вместо чата | Только картинки |

Команды:

```bash
ollama pull dolphin-llama3:70b
ollama pull qwen2.5:32b
# опционально
ollama pull qwen2.5-coder:32b
```

Возможности пайплайна (Comfy → Cascadeur → Unity) Вью читает из промпта + `docs/` — модель должна **знать план**, а не «базовые знания Cascadeur».
