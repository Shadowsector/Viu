# Blender-клип → Cascadeur

Минимальный путь: Вью делает простой Action в Blender, печёт FBX, кладёт в Cascadeur Inbox.

## Зачем

- Blender: **центр** — позы-hold + переходы (`blend_to`) на канон-риге.
- Cascadeur: только полировка (физика, контакты).
- Unity: Export → `U:\Anabarra\Animations` → «Обновить аниматор».

Двое+ персонажей — **не** dual-mocap: клип Шани + клип партнёра + сокеты/IK.

## Инструменты

| Tool | Назначение |
|------|------------|
| `blender_pose_character` | `pose_character("Shanya", "all_fours")` — найти blend и поставить позу |
| `blender_blend_to` | `blend_to("sit", from=stand, frames=12)` |
| `blender_make_anim` | Низкий уровень: preset + optional from_preset |
| `blender_export_cascadeur_anim` | Export FBX с `bake_anim=True` |
| `blender_anim_to_cascadeur` | Всё сразу + pending LabImport (`mode=animation`) |

### Holds (библиотека поз)

`stand`, `sit`, `kneel`, `all_fours`, `lie`

### Motion

`idle`, `wave`, `nod`, `look_left`, `look_right`, `stretch`

Кости: Unity Humanoid (`Hips`, `LeftUpperLeg`…) + Mixamo aliases — см. `RIG_STANDARD.md`.

## Папки

```
Library/Lab/Anims/BlenderOut/       ← .blend с клипом
Library/Lab/Anims/CascadeurReady/   ← *_anim.fbx
Library/Cascadeur/Inbox/            ← копия для импорта
```

Риг Шани: `Lab/Models/CascadeurReady/*Shanya*.blend` (или `blend_file=` явно).

## Пример мысли Вью

1. старт `stand` → финиш `sit`, 12 кадров  
2. `blender_blend_to character=shanya to_pose=sit from_pose=stand frames=12`  
3. export FBX → (опц.) Cascadeur polish → каталог (`sit_down` / `sit_idle`)

## Ручной импорт в Cascadeur

Если Commands не сработали:

1. New scene  
2. File → Import → Fbx/Dae  
3. Preset **Scene**, INCLUDE **Animations** ✓, **Open first take** ✓  
4. Rig Mode Helper → No  

Или: Reload scripts → **Commands → Viu → LabImport**.
