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

## Почему после апдейта «отъезжал» reflect

Раньше в Anabarra клался **полный снимок** `reflect_mode.py`. Он переживал zip/git update и при импорте **целиком** подменял пакет — откатывались фиксы (#85 memory-echo, #86 NO_SYSTEM+digest, #90 modes).

Теперь:
1. Seed / миграция → файл только с `REFLECT_VOICE` и строками (маркер `REFLECT_OVERRIDE_FORMAT`).
2. `load_reflect_mode_override` применяет **allowlist** строк; функции из Anabarra игнорируются.
3. Старый полный снимок при старте/апдейте → `.bak-full-*` + voice-only.

Править в Anabarra можно голос. `VIU_REFLECT_NO_SYSTEM` и логика памяти — всегда из `U:\Viu`.

Сегодня (#85/#86/#90 + guard): чат не зачитывает весь `VIU_MEMORY.md`; голое «Попробуешь?» — чат, не tools; апдейт не откатывает plumbing.
