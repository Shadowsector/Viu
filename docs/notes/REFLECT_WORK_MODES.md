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

## Почему характер «отъезжал» после апдейтов (#85–#94)

При `VIU_REFLECT_NO_SYSTEM=1` (дефолт) Viu **не шлёт system** — задумано, чтобы не драться с Modelfile.
Но вместе с system отбрасывались и **REFLECT_VOICE**, и JSON-minimal. Оставался тонкий jailbreak Magnum/Euryale → чужой тон, **Owner**, потеря озорства.

Дополнительно:
- полный снимок Anabarra откатывал plumbing (#93 → voice-only allowlist);
- короткий якорь «Кто вы / Owner» (#94) не возвращал характер.

**Сейчас при NO_SYSTEM** в user-turn едет `reflect_voice_user_block()`: полный голос (из пакета или Anabarra) + «Ден» + JSON-minimal + digest памяти. System role по-прежнему не шлём.

Править голос — в Anabarra `REFLECT_VOICE`. Флаги/память — из пакета.
