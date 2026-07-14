# Вью — автоматизация игры и анимаций (зафиксировано)

**Дата:** 2026-07-14 (обновлено: пайплайн Den Comfy→Cascadeur)

---

## Принцип

Вью — **конвейер и продюсер анимаций**.  
Cascadeur — цех (MoCap + правка).  
ComfyUI — фабрика видео-референсов.  
Mixamo — быстрые клипы «прямо сейчас».

Главный целевой контур (идея Den):  
**[`COMFY_CASCADEUR_PIPELINE.md`](./COMFY_CASCADEUR_PIPELINE.md)**  
Comfy (промпт) → чёткое MP4 → Cascadeur MoCap → FBX + имя → catalog + **граф переходов** (sit→stand_up→idle, без телепортов). NSFW — в той же очереди.

```
Mixamo (быстро) ──► Inbox ──► Animator
Comfy video ──► Lab/Refs ──► Cascadeur MoCap ──► Animations\ ──► catalog + graph
```

---

## Порядок работ

| # | Задача | Док |
|---|--------|-----|
| 1 | Wave 1 Mixamo (sit/walk/…) | [SHANYA_ANIMATIONS.md](./SHANYA_ANIMATIONS.md) |
| 2 | **Стопы Walk** (не скорость) | [WALK_FEET_FIX.md](./WALK_FEET_FIX.md) |
| 3 | Сарай по шагам | [BARN_EDIT_STEPS.md](./BARN_EDIT_STEPS.md) |
| 4 | Эталон Шаня в Cascadeur + QRT | CASCADEUR.md |
| 5 | Lab export FBX | очередь |
| 6 | Comfy install + `comfy_run` | COMFY_CASCADEUR_PIPELINE.md |
| 7 | MoCap script + last-frame chain | то же |
| 8 | Граф переходов в catalog | то же |

---

## Что не автоматизировать

- Vision-клики по UI Cascadeur  
- Единый скелет на всех зверей  
- Генерация без графа переходов (будет телепорт sit→walk)

---

## Связанные доки

- [COMFY_CASCADEUR_PIPELINE.md](./COMFY_CASCADEUR_PIPELINE.md) — **твой** пайплайн  
- [WALK_FEET_FIX.md](./WALK_FEET_FIX.md) — подворот стоп  
- [BARN_EDIT_STEPS.md](./BARN_EDIT_STEPS.md) — сарай клик за кликом  
- [BARN_LIVELINESS.md](./BARN_LIVELINESS.md) — критерии «живо»  
- [VIU_LAB.md](./VIU_LAB.md), [VISION.md](./VISION.md)
