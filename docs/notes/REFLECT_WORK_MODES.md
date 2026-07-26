# Reflect vs Work — два состояния

Канон: [`VIU_SELF.md`](../VIU_SELF.md) § «Два режима мозга». Код: `viu/modes.py`.

| | Простой разговор | Работа |
|--|------------------|--------|
| Внутри | `reflect` | `work` |
| Когда | всё по умолчанию | «следующий шаг», «сделай…», handoff/GitHub с действием |
| Модель | `VIU_MODEL_REFLECT` | `VIU_MODEL_WORK` / code |
| Tools | нет | да |
| Память | короткий digest `VIU_MEMORY`, не весь файл | через tools / system.md |

**Не путать с файлами:**
- `VIU_MEMORY.md` — память, не «режим»
- `U:\Anabarra\ViuPrompts\reflect_mode.py` — личный голос чата (переживает update)
- `viu/prompts/reflect_mode.py` — пакетный fallback

Сегодня (#85/#86): чат больше не зачитывает весь `VIU_MEMORY.md`.  
Голое «Попробуешь?» снова чат, не tools.
