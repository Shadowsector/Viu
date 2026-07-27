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
- `U:\Anabarra\ViuPrompts\reflect_mode.py` — **только голос** чата (переживает update)
- `viu/prompts/reflect_mode.py` — пакет: голос-fallback + флаги/функции
- `.viu/vision.md` — мечта/жизнь/сюжет (creative), без техбэклога

## Жизнь Вью должна доезжать

По умолчанию `VIU_REFLECT_NO_SYSTEM` **выкл.**: в Ollama уходит **system** с `REFLECT_VOICE` (характер + жизнь из reflect / Anabarra).

В bare-чат всегда ещё `format_reflect_life_block()`: канон Шаньки + creative `vision.md` (мечта, отношения) — не только когда спросили «про сюжет».

`VIU_REFLECT_NO_SYSTEM=1` — отладка «только Modelfile»; тогда якорь имени + жизнь/память едут в user.

После апдейта: новый чат (старая история тянет старый тон).
