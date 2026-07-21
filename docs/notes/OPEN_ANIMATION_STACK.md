# Заметка: open-source vs Cascadeur (2026-07-18)

**Контекст:** обсуждение с Деном — есть ли бесплатная замена Cascadeur целиком.  
**Статус:** идеи на потом, не в активный roadmap.  
**Связано:** `COMFY_CASCADEUR_PIPELINE.md`, `INTERACTION_PIPELINE.md`, `CREATURE_PIPELINE.md`.

---

## Вывод в одну строку

Полного open-source аналога Cascadeur (покадровка + физика контактов + AI-позы в одном UI) **нет**. Можно собрать **модульный** стек; для Viu сейчас разумнее **не менять ядро**, а точечно добавлять OSS там, где больно.

---

## Что даёт Cascadeur нам (и чем не закрыт список «бесплатных замен»)

| Нужно Viu | Cascadeur | Типичный OSS из обзора |
|-----------|-----------|-------------------------|
| MoCap с ref-видео (Comfy) | да | FreeMoCap/OpenCap — другой вход (живой актёр / мультикам) |
| Физика / контакты двух актёров | сильная сторона | Blender вручную или constraints в assembly |
| Quadruped (Control Pose) | в плане пайплайна | отдельные инструменты, нет единого UI |
| Быстрая правка humanoid после capture | да | Blender — мощно, медленнее |

**Interaction-пайплайн** (`master ref → isolated → mocap/CP → assembly`) — своё; ни Mesh2Motion, ни ARDY его не заменяют.

---

## Кандидаты из обзора (когда вернёмся к теме)

### Blender + Rigify
- Уже база: blocking, lineup, creature catalog, CascadeurReady export.
- Auto-Rig Pro — платный, не «чистый OSS».

### Mesh2Motion (браузер, Mixamo-like)
- **Когда полезен:** новые существа в Inbox без рига, быстрый idle/walk для теста.
- **Ограничения:** нестандартные силуэты (волк, слизень, кентавр) — лотерея; не финальная физика контактов.
- **Идея для Viu:** опциональный шаг `creature_inbox` → «попробовать Mesh2Motion» → обратно в Blender.

### FreeMoCap / OpenCap
- Захват **реального** человека (камеры / телефон), не Comfy-ref.
- Имеет смысл как **доп. источник ref** («Ден снял себя»), не как замена Comfy → Cascadeur.

### NVIDIA ARDY (text → motion)
- Прототипы, R&D; интеграция, стиль персонажа, multi-actor — отдельная головная боль.
- Только lab, не критический путь.

---

## Стратегия «если обсуждать снова»

```
Сейчас не ломать:  Blender blocking → Comfy ref → Cascadeur → Unity
Добавлять точечно: Mesh2Motion (rig inbox), Rigify (доводка)
Опционально:       FreeMoCap/OpenCap (live ref), ARDY (эксперименты)
Своё ядро:         multi-actor catalog + assembly в Blender
```

**Не делать без причины:** массовая замена Cascadeur на OSS только ради лицензии — дорого по времени, interaction-пайплайн ещё не закрыт.

---

## Триггеры «пора вернуться к теме»

- Cascadeur станет узким местом по лицензии / цене / API.
- Появится стабильный OSS video-to-rig для quadruped с приемлемым качеством.
- Нужен массовый auto-rig для 50+ существ в Inbox без ручного Rigify.
- Lab interaction дойдёт до assembly — станет ясно, сколько правок реально в Cascadeur vs Blender.

---

## Ссылки (внешние, на момент заметки)

- Mesh2Motion — веб auto-rig + стандартные клипы
- FreeMoCap — Python, мультикам mocap
- OpenCap — smartphone + AI
- NVIDIA ARDY — text → human motion (real-time)

*Обновлять по мере появления новых инструментов; не синхронизировать с релизами автоматически.*
