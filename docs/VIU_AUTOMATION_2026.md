# Вью — автоматизация игры и анимаций (зафиксировано)

**Дата:** 2026-07-14  
**Контекст:** после CascadeurReady batch, lab SUCCESS на Menkara, оценка 4.2.

---

## Принцип

Вью — **конвейер и QA**, не «кнопконажиматель UI Cascadeur».  
Cascadeur — **цех анимации** (руками + Python).  
ComfyUI — **фабрика референсов** (поза/видео), не готовый FBX humanoid.

```
модель → CascadeurReady FBX ✓
       → Cascadeur (Den / MoCap / QRT)
       → Animations\ → unity_sync ✓
Comfy  → Lab/Refs → MoCap / vision QA
Mixamo → Inbox → catalog → Animator ✓
```

---

## Порядок работ (не прыгать)

| # | Задача | Статус |
|---|--------|--------|
| 1 | **Wave 1 Mixamo** — закрыть missing в каталоге | ← сейчас |
| 2 | **Эталон Шаня** — чистый Walk (не Run-as-Walk) + QRT | очередь |
| 3 | **Lab export** FBX → `Animations\` | очередь |
| 4 | **`comfy_pose` / Comfy HTTP** → `Lab/Refs` | очередь |
| 5 | **Lab MoCap assist** (референс + timeline) | позже |
| 6 | **Affordance → clip** (дерево без climb → предложить) | позже |
| 7 | Video-Comfy + NSFW Phase 3 | позже |

---

## Что не автоматизировать

- Полный auto-QRT на весь Inbox (битые blend остаются)
- Vision-клики по UI Cascadeur
- Генерация locomotion целиком в AI
- «Единый скелет» на зверей в Cascadeur

---

## ComfyUI (когда подключим)

| Выход | Куда |
|-------|------|
| Картинка позы | Cascadeur MoCap from image |
| Короткое видео | Reference video → MoCap |
| Концепт prop/локации | Inbox → prop pipeline |

VRAM: **не** параллельно с Cascadeur + Unity (очередь как у lab, ~6 GB).

Путь референсов (план): `U:\Anabarra\Library\Lab\Refs\`

---

## Связанные доки

- [SHANYA_ANIMATIONS.md](./SHANYA_ANIMATIONS.md) — каталог, Wave, **починка Walk**
- [BARN_LIVELINESS.md](./BARN_LIVELINESS.md) — сарай, камера, жизнь дома
- [CASCADEUR.md](./CASCADEUR.md) — FBX / CascadeurReady
- [VIU_LAB.md](./VIU_LAB.md) — lab pipeline
- [VISION.md](./VISION.md) — долгосрочное видение
- [VIU_ROADMAP_2026.md](./VIU_ROADMAP_2026.md) — фазы
