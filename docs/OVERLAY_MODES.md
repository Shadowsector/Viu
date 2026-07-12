# Overlay — три режима (Phase A)

**Policy:** `BuildWindows` **не пересоздаёт** сцену. Источник правды — `OverlayDesktop.unity` в Unity Editor.

## Режимы

| Режим | Окно | Камера | Когда |
|-------|------|--------|-------|
| **Facade** | полоска у таскбара (~280px) | ortho ~5.5, feet 0.07 | дом снаружи, жизнь у порога |
| **Corridor** | та же полоска | лёгкий depth blend | Шаня идёт к сараю |
| **Instance** | полоска **выше** (`instanceHeightPixels`) | ortho ~2.4, крупный план | внутри barn (dollhouse) |

Runtime: `OverlayModeController` + `OverlayCameraPresets` + `ShanyaDesktopOverlay.ApplyDisplayMode`.

## Якоря (правит Ден в Scene)

Под `Viu_Anchors/` (создаются при Bootstrap):

- `Anchor_CharacterStart` — старт Шани, Z коридора
- `Anchor_BarnEntrance` — дверь / дальний Z
- `Anchor_HomeRoot` — pivot дома
- `Anchor_TaskbarFeetLine` — линия стоп (reference)

Компонент: `OverlaySceneAnchor`.

## Viu vs Unity

| Viu | Unity |
|-----|-------|
| Inbox → FBX → Textures | Scene, prefabs, материалы |
| Deploy scripts | Play mode, якоря, props |
| **Validate** + **Build exe** | Ctrl+S сцены |
| **Bootstrap once** | первичная расстановка |

## Меню Unity (Viu)

- **Bootstrap Overlay Scene (once)** — полная первичная сборка (как раньше Prepare)
- **Validate Overlay Scene** — проверка перед build
- **Build Windows Overlay** — Validate + exe

Кнопка Viu «Оверлей: у панели задач» = deploy + Validate + build (сцена **не** двигается).

## Baseline (не ломать)

Прозрачность UpdateLayeredWindow rev37, Idle/Walk — см. `OVERLAY_BASELINE.md`.
