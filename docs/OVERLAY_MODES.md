# Overlay — три режима (Phase A)

**Policy:** `BuildWindows` **не пересоздаёт** сцену. Источник правды — `OverlayDesktop.unity` в Unity Editor.

## Режимы

| Режим | Окно | Камера | Когда |
|-------|------|--------|-------|
| **Facade** | **весь экран** (прозрачный) | ortho ~5.5, feet у таскбара | дом снаружи, жизнь у порога |
| **Corridor** | весь экран | лёгкий depth blend | Шаня идёт к сараю |
| **Instance** | весь экран | ortho ~2.4, крупный план | внутри barn (dollhouse) |

Окно всегда на весь монитор — иначе Шаня не сможет лезть вверх (деревья, иконки, здания).
«У таскбара» = **камера** и якорь дома, не высота HWND.

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
