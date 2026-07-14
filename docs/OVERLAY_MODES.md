# Overlay — три режима (Phase A)

**Policy:** `BuildWindows` **не пересоздаёт** сцену. Источник правды — `OverlayDesktop.unity` в Unity Editor.

## Режимы

| Режим | Окно | Камера | Когда |
|-------|------|--------|-------|
| **Facade** | **весь экран** (прозрачный) | ortho ~5.5, feet у таскбара | дом снаружи, жизнь у порога |
| **Corridor** | весь экран | лёгкий depth blend | Шаня идёт к сараю |
| **Instance** | весь экран | ortho ~2.15, крупный план интерьера | внутри barn (dollhouse) |

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

Кнопка Viu «Overlay: rebind материалы» = deploy + Rebind + save scene (сцена **не** двигается).

## Меню Unity (Viu)

- **Bootstrap Overlay Scene (once)** — полная первичная сборка
- **Rebind All Materials** — текстуры → .mat r50
- **Validate Overlay Scene** — проверка (overlay_validate.log)
- **Build Windows Overlay** — Validate + exe
- **Build Windows Overlay (no validate)** — только exe

Кнопки Viu GUI «Ещё — игра»: Validate → Rebind → Build (или полный playtest).

## Baseline (не ломать)

Прозрачность UpdateLayeredWindow rev37, Idle/Walk — см. `OVERLAY_BASELINE.md`.
