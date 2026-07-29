# Blender-клип → Cascadeur

Минимальный путь: Вью делает простой Action в Blender, печёт FBX, кладёт в Cascadeur Inbox.

## Зачем

- Blender: быстрый грубый ключ (idle / wave / nod…).
- Cascadeur: полировка (физика, контакты, правки поз).
- Unity: Export → `U:\Anabarra\Animations` → «Обновить аниматор».

Это **не** замена Mixamo/Comfy MoCap и не полный AI-аниматор.

## Инструменты

| Tool | Назначение |
|------|------------|
| `blender_make_anim` | Создать Action на арматуре |
| `blender_export_cascadeur_anim` | Export FBX с `bake_anim=True` |
| `blender_anim_to_cascadeur` | Всё сразу + pending LabImport (`mode=animation`) |

Пресеты: `idle`, `wave`, `nod`, `look_left`, `look_right`, `stretch`.

## Папки

```
Library/Lab/Anims/BlenderOut/       ← .blend с клипом
Library/Lab/Anims/CascadeurReady/   ← *_anim.fbx
Library/Cascadeur/Inbox/            ← копия для импорта
```

## Ручной импорт в Cascadeur

Если Commands не сработали:

1. New scene  
2. File → Import → Fbx/Dae  
3. Preset **Scene**, INCLUDE **Animations** ✓, **Open first take** ✓  
4. Rig Mode Helper → No  

Или: Reload scripts → **Commands → Viu → LabImport**.
