# Направление работ сейчас (канон для Вью и Дена)

Обновлено: 2026-07-17. Читай вместе с `COMFY_CASCADEUR_PIPELINE.md`, `CREATURE_PIPELINE.md`, `INTERACTION_PIPELINE.md`, `SHANYA_ANIMATIONS.md`.

## Цель пайплайна анимаций

**Модульные клипы + граф переходов**, не одна длинная анимация на действие.

- **Переходы** (`sit_down`, `stand_up`, `lie_down`, `get_up`) — one-shot, не loop.
- **Циклы** (`idle`, `sit_idle`, `sleep_idle`, `walk`, `run`) — **обязательно loopable**
  (первый и последний кадр стыкуются; иначе клип бессмысленен для Animator).
- Comfy снимает **дыру графа** (`catalog_slug` + `enters_from`/`exits_to`), не «Idle Stand» от скуки.
- Пока есть дыры wave 1 кроме `idle` — **не снимать idle**.

## Куда класть файлы

| Что | Куда |
|-----|------|
| Кандидаты MoCap (копия из Comfy) | `U:\Anabarra\Library\Lab\Refs\` |
| Одобренные | `Lab\Refs\kept\` + seed PNG в `seeds\` |
| Сырой вывод ComfyUI | `U:\Viu\ComfyUI\output\` — **промежуточный**; Вью копирует в Refs |
| Готовые FBX | `U:\Anabarra\Animations\` |

Native Comfy всегда пишет в свой `output/` — Вью **обязана** скопировать в Lab/Refs и работать оттуда.

## Одобрение клипов (нативно)

1. Дома: после тройки дублей Вью **сама открывает окно выбора** и пишет в чат/Telegram.
2. Ответ: в окне, или в чате/Telegram «лучший: take_b», или «ок» на промпт до съёмки.
3. Away: авто-одобрение промпта + keep `take_b`.

Не нужно «вспомнить кнопку из апдейта» — выбор всплывает сам.

## Очередь работ (приоритет)

1. Comfy → **Refs** + граф без idle-спама + looped idle/walk  
2. Влить Cascadeur MoCap (kept → Reference → export)  
3. Morph-инвентарь существ (без bake)  
4. Сокеты Шани в Unity **или** Animator по графу wave 1  
5. I2V-очередь; NSFW Comfy-очередь  
6. Хвост/щупальца — secondary physics, не MoCap-first (Шняк — Blender/procedural)
7. **Совместные анимации** — `INTERACTION_PIPELINE.md`, пилот `shanya_wolf_approach`

## Как Вью общается

- **Дома:** перед съёмкой советуется (промпт + альтернативы графа); после съёмки просит выбрать дубль.
- **Heartbeat:** предлагает следующую дыру графа / идею, не молчит.
- **Нет дома:** автономия по графу, без спама idle.
