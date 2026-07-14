# Overlay — рабочий baseline (не откатывать)

**Зафиксировано:** 2026-07-12, подтверждено Деном после rev37.  
**Deploy rev:** `37` (`VIU_DEPLOY_REV`, `RuntimeRev`, `@viu-deploy-rev 37`).

Если снова «магента на весь экран» или «T-pose / всегда бежит» — **сначала сверься с этим файлом**, не переписывай с нуля.

---

## Победы (работает)

### 1. Прозрачность окна — UpdateLayeredWindow (rev37)

| Что | Значение |
|-----|----------|
| Primary path | `ShanyaDesktopOverlay.useUpdateLayeredWindow = true` |
| Механизм | Camera → RenderTexture → AsyncGPUReadback → `UpdateLayeredWindow(ULW_ALPHA)` |
| Chroma | **`#FF0080`** (`Color32(255,0,128)`) — **не** `#FF00FF` (это missing-shader в Unity) |
| HDR / MSAA | выключены на overlay-камере |
| Fallback | ColorKey (`SetLayeredWindowAttributes`) — **только если ULW не поднялся** |

**В `overlay_boot.log` должно быть:**

```
runtime-rev=37
Transparency=UpdateLayeredWindow (per-pixel alpha) OK
```

**Мёртвый путь (не возвращать как primary):** ColorKey + DWM margins=-1 + BitBlt. На Unity 6 / Win11 / RTX 3060 API пишет `SetLayeredWindowAttributes=True`, а окно **остаётся solid magenta** — так было на rev36.

**Не делать при ULW:** не вызывать `SetLayeredWindowAttributes` на том же HWND — конфликтует с per-pixel alpha.

Запуск: `LaunchOverlay.vbs` / `.bat` (можно оставить `-force-d3d11-bitblt-model` для fallback; ULW BitBlt не требует).

---

### 2. Анимации локомоции (Idle / Walk)

| State | FBX (Den preview OK) | Import rig |
|-------|----------------------|------------|
| **Idle** | `X Bot@Idle.fbx` | Humanoid → **Create From This Model** |
| Walk | `Shanya_Walk.fbx` (предпочтительно) или Mixamo Female Walk | Create From This Model |
| Walk (fallback) | `Shanya_Run.fbx` | state.speed **0.55** + locomotion throttle |

Пины: `viu_clips.json` → `overlay_preferred.Idle` / `Walk`, плюс `ShanyaAnimationSync.TryAddPinnedClip`.

**Поведение в рантайме:**

- В покое — Idle, по A/D — Walk (не «всегда Run»).
- `WalkThreshold = 0.25f` — не дребезг от стика.
- **Не** `GetAxisRaw("Horizontal")` — только оси с deadzone (см. `ShanyaLocomotion`).
- **Не** подставлять `Idle_Stand` если нет Walk — лучше FAIL в лог, чем слайд с Idle_Stand.
- `applyRootMotion = false`, CrossFade Idle ↔ Walk.

**Тело в сцене:** только `Shanya_Erisa` (модель). **Никогда** класть `Shanya_Run.fbx` / `Shanya_Fall.fbx` как персонажа — T-pose.

---

### 3. Сборка и deploy

- `deploy_clips_manifest(overwrite=True)` при смене пинов — иначе stale `viu_clips.json`.
- Build FAIL → **не** переименовывать рабочий `AnabarraOverlay.exe` в `.broken` (rev36+).
- Проверка rev в exe: строка `runtime-rev=37` в boot-логе.

---

## Запреты (DO NOT REGRESS)

1. **Chroma `#FF00FF`** на камере или как «универсальный ключ».
2. **ColorKey-only** как единственная прозрачность на Win11.
3. **Copy From Other Avatar** с Erisa на Mixamo-анимации → `Torso for Hips not found`.
4. **Fill Rig Source** / копирование rig между разными скелетами (см. `UNITY_PIPELINE.md`).
5. **`GetAxisRaw`** для overlay locomotion.
6. **Idle_Stand fallback** при отсутствии Walk.
7. **Переименование exe в `.broken`** при failed build.
8. **Сборка без throw** при ошибках `ShanyaAnimationSync` / overlay setup.

---

## Диагностика

| Симптом | Смотри |
|---------|--------|
| Solid magenta, boot rev36 | Старый exe или ULW не включился |
| Solid magenta, `ColorKey=True` | Нужен rev37 ULW, ColorKey мёртв |
| T-pose | В сцене clip-FBX вместо Erisa; или пустой Animator |
| Всегда бежит | Run в Walk + нет threshold / GetAxisRaw |
| Слайд без анимации | `hasWalk=False`, stale clips, Idle_Stand убран — пересинк |
| Дом magenta | URP Lit, не Standard; `FixOverlayMaterials` |

---

## Коридор и кукольный дом (rev40)

По `VISION.md` §6.5: полоса ~10 м в глубину; сарай — **дальняя стенка** коридора.

| Режим | `DollhouseWall.atHome` | Вид |
|-------|------------------------|-----|
| Снаружи (старт) | `false` | Фасад сарая как стенка |
| У двери (Z ≥ door) | `true` | Передняя стенка скрыта → кукольный дом |

- **W** — вглубь к сараю (спиной), мельче
- **S** — к камере (лицом), крупнее
- Компонент: `ShanyaOverlayCorridor.cs` — масштаб + `EnterHome`/`ExitHome`

## Открыто (следующие задачи)

Rev38 (2026-07-12): feet lower (0.07), home yaw 180°, W/S Z walk in Locomotion, stable camera feet offset (no run bobbing).

Если после rebuild всё ещё не так — F5 сохраняет `overlay_tune.json`, правь `characterDepthZ` / `feetLiftMeters`.

---

## Связанные файлы

| Файл | Роль |
|------|------|
| `ShanyaDesktopOverlay.cs` | ULW + boot log |
| `ShanyaAnimationSync.cs` | Пины клипов, Create From This Model |
| `ShanyaLocomotion.cs` | A/D, threshold, Run-as-Walk speed |
| `ShanyaOverlayDepth.cs` | W/S по Z |
| `ShanyaOverlayCamera.cs` | feet fraction, follow |
| `viu_clips.json` | overlay_preferred |
| `viu/integrations/unity/setup.py` | `VIU_DEPLOY_REV` |
| `docs/UNITY_PIPELINE.md` | Mixamo / Humanoid правила |
