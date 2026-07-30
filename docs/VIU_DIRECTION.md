# Направление работ сейчас (канон для Вью и Дена)

Обновлено: 2026-07-29. Читай вместе с `ANIMATION_CANON.md`, `COMFY_CASCADEUR_PIPELINE.md`,
`CREATURE_PIPELINE.md`, `INTERACTION_PIPELINE.md`, `SHANYA_ANIMATIONS.md`.

## Цель пайплайна анимаций

**Модульные клипы + граф переходов**, не одна длинная анимация на действие.

- **Переходы** (`sit_down`, `stand_up`, `lie_down`, `get_up`) — one-shot, не loop.
- **Циклы** (`idle`, `sit_idle`, `sleep_idle`, `walk`, `run`) — **обязательно loopable**
  (первый и последний кадр стыкуются; иначе клип бессмысленен для Animator).
- Клипы **сначала** на канон-риге (Mixamo / ActorCore / Blender / Control Pose).
  **Cascadeur = полировка**, не обязательный Video MoCap (см. `ANIMATION_CANON.md`).
- Comfy — дыры графа, рефы, шоу; не единственный источник скелета.
- Пока есть дыры wave 1 кроме `idle` — **не снимать idle**.

## Куда класть файлы

| Что | Куда |
|-----|------|
| Кандидаты Comfy / рефы | `U:\Anabarra\Library\Lab\Refs\` |
| Одобренные | `Lab\Refs\kept\` + seed PNG в `seeds\` |
| Сырой вывод ComfyUI | `U:\Viu\ComfyUI\output\` — **промежуточный**; Вью копирует в Refs |
| Канон-тела (чистый FBX) | `Lab\Models\CascadeurReady\` |
| Готовые FBX | `U:\Anabarra\Animations\` |

Native Comfy всегда пишет в свой `output/` — Вью **обязана** скопировать в Lab/Refs и работать оттуда.

## Одобрение клипов (нативно)

1. Дома: после тройки дублей Вью **сама открывает окно выбора** и пишет в чат/Telegram.
2. Ответ: в окне, или в чате/Telegram «лучший: take_b», или «ок» на промпт до съёмки.
3. Away: авто-одобрение промпта + keep `take_b`.

Не нужно «вспомнить кнопку из апдейта» — выбор всплывает сам.

## Очередь работ (приоритет)

1. **Канон biped** (AccuRIG/Mixamo → Unity Humanoid) + wave 1 клипы из библиотеки  
2. (Опц.) лёгкая правка лиц героев **до** финального бинда (`ANIMATION_CANON.md`)  
3. Comfy → Refs / граф / шоу — по дырам, без ставки на Cascadeur MoCap  
4. Cascadeur — полировка клипов, которые уже играют на каноне  
5. Quad-шаблон + Control Pose (волк; пилот interaction)  
6. Morph-инвентарь существ (без bake)  
7. Сокеты Шани / Animator по графу wave 1  
8. Хвост/щупальца — secondary physics  
9. Совместные анимации — `INTERACTION_PIPELINE.md`, пилот `shanya_wolf_approach`

## Как Вью общается

- **Фото в Telegram:** Ден кидает кадр + пожелание → Вью сама пишет Wan-промпт, подбирает LoRA, снимает, болтает, присылает результат (без панели).
- **Дома / панель Съёмка:** ручная правка промпта/LoRA/лица, потом «Снять».
- **Heartbeat:** предлагает следующую дыру графа / идею, не молчит.
- **Нет дома:** автономия по графу, без спама idle.
