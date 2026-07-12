# Вью — развитие 2026 (зафиксированные выводы)

**Дата:** 12 июля 2026  
**Источники:** Den, Grok (vision doc), Cursor agent (rev48–50)

---

## 1. Общая цель

Вью — **надёжный технический партнёр**, не кнопконажиматель. Берёт рутину (ассеты, deploy, validate, build), Den — вижн и творчество в Unity/Blender.

---

## 2. Архитектурные принципы (согласовано)

| Принцип | Смысл |
|---------|--------|
| **Direct tools > LLM** | Рутина = Python + batch Unity/Blender без модели |
| **Scene = source of truth** | `OverlayDesktop.unity` правит Den; build не пересоздаёт сцену |
| **Fullscreen overlay** | Окно на весь монитор; «у таскбара» = камера + якоря, не полоска HWND |
| **LLM для творчества** | Предложения по анимациям, лор, разметка affordances — не для compile/deploy |
| **Инициативность** | Director + «Следующий шаг»; away mode + decision queue |

---

## 3. Фаза 1 — Стабильность (текущий спринт, rev50)

### 3.1 Material Pipeline

**Проблема:** Runtime `MaterialFix` чинит единицы; фиолетовый barn / белые волосы — Editor-side missing albedo.

**Решение (rev50):**

- Unity: **Viu → Overlay → Rebind All Materials**
- Viu GUI: **Overlay: rebind материалы**
- Tool: `unity_overlay_rebind`
- Материалы сохраняются в `Assets/*/ViuOverlayMats/r50/`
- Viu копирует текстуры при export; Rebind **привязывает** их к .mat в сцене

**Workflow:**

```
Export FBX + Textures/  →  Rebind All Materials  →  Validate  →  Build exe
```

### 3.2 Scene Validation

**Расширено (rev50):** `ValidateOverlayScene` проверяет:

- Шаня + Humanoid avatar + Walk
- RuntimeRev deploy
- Якоря 4/4 (warn/error)
- Materials: bad shader + missing albedo → **FAIL**
- Camera presets, Dollhouse

Отчёт: `overlay_validate.log` + Console.

- Unity: **Viu → Overlay → Validate Overlay Scene**
- Viu GUI: **Overlay: проверить сцену**
- Tool: `unity_overlay_validate`

### 3.3 Build Workflow

**Разделено:**

| Действие | Что делает |
|----------|------------|
| Validate | Только проверка |
| Rebind | Только материалы + save scene |
| Build | Только exe (`BuildWindowsOnly`) |
| Playtest | Deploy + textures + build + launch (legacy кнопка) |

GUI «Ещё — игра»: три кнопки + «полный playtest».

---

## 4. Фаза 2 — Ассистент по ассетам (следующая)

- Автоматический retarget анимаций (поверх `rig_check` / Humanoid)
- Blender Bridge — команды в открытый Blender
- Affordance System — prop catalog → gameplay hooks
- Material sidecar `.viu.json` → Unity importer (не только Rebind)

---

## 5. Фаза 3 — NSFW-техника (roadmap, не блокирует overlay)

Техническая помощь с ригами и ассетами (не explicit-тексты):

- Penis Rig (самонаводящийся)
- Target System (Vagina / Anus / Mouth)
- Futa Toggle
- Body Variants (одетая / обнажённая)

---

## 6. Что сознательно отложено

- **Vision QA (eyes)** — ненадёжен (wrong HWND, llava noise); log-verdict первичен
- **Полоска окна у таскбара** — отменена (rev49)
- **Bootstrap каждый build** — отменён (rev48)

---

## 7. Роли: Viu vs Unity vs Cursor

```
Den          — Scene layout, материалы OK, якоря, Ctrl+S
Viu          — Inbox pipeline, deploy C#, Validate/Rebind/Build, director
Cursor cloud — C# templates, Python tools, docs, PR (без playtest на машине Den)
```

---

## 8. Критерий «Phase 1 готова»

1. Validate → 0 material FAIL после Rebind
2. Build exe без CS errors
3. `overlay_boot.log`: `runtime-rev=50`, fullscreen geometry
4. Barn + Shanya визуально OK у Den (глазами — пока без eyes)

---

См. также: `OVERLAY_MODES.md`, `OVERLAY_BASELINE.md`, `VIU_CONCEPT.md`, `ASSET_PIPELINE.md`.
