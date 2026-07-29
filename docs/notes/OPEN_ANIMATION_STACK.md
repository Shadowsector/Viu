# Заметка: стек анимаций и Cascadeur (обновлено 2026-07-29)

**Канон:** [`ANIMATION_CANON.md`](../ANIMATION_CANON.md) — читать первым.  
Старая стратегия «Comfy → Cascadeur MoCap как ядро» **снята**: Cascadeur только полировка.

---

## Вывод

Полного OSS-заменителя Cascadeur (физика + AI-позы в одном UI) **нет**.  
Нам это и не нужно как единственный путь: клипы берём с канон-рига, Cascadeur — доводка.

---

## Роли инструментов

| Нужно | Что используем |
|-------|----------------|
| Auto-rig biped | **AccuRIG 2** (бесплатно), fallback Mixamo |
| Библиотека motion | Mixamo, ActorCore |
| Простые ключи | Blender (`blender_make_anim`) |
| Quad / контакты | **Control Pose** + markers (`INTERACTION_PIPELINE`) |
| Полировка / физика | Cascadeur на канон-теле |
| Реф / режиссура | Comfy (не обязательный скелет) |
| Previz Inbox | Mesh2Motion (не финал) |
| Пилот video→SMPL | WHAM / 4D-Humans — позже |

---

## Было → стало

```
Было:   Inbox → (кривой FBX) → Cascadeur MoCap ← Comfy mp4
Стало:  Inbox → AccuRIG/канон → клипы (библиотека/ключи/CP)
              → Cascadeur polish (опц.) → Unity
```

---

## Ссылки

- AccuRIG — https://www.reallusion.com/auto-rig/accurig/
- Mixamo — https://www.mixamo.com/
- Mesh2Motion — веб auto-rig + клипы
- Cascadeur quadruped Quick Rig — с 2025.3 (Pro+)
- WHAM / 4D-Humans — monocular → SMPL (пилот)

*Обновлять по мере появления новых инструментов; не синхронизировать с релизами автоматически.*
