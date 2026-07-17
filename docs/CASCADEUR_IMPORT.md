# Import FBX в Cascadeur — пошагово

Для лаборатории Вью и ручной работы Дена.

## Проверенный ручной путь (Den, Menkara ✓)

1. **Фокус** — Cascadeur активное окно (клик по 3-му монитору, если нужно).
2. **New scene** — убрать welcome / создать вкладку сцены.
3. **File → Import → Fbx/Dae**
4. Диалог **FBX/DAE IMPORT**:
   - **Presets:** **Scene**
   - **Import mode:** **Add new**
   - **INCLUDE:** Animations ✓, Objects ✓, Blendshapes ✓
   - **Open first take:** ✓ (как на скрине)
5. Кнопка **Import** →  
   `U:\Anabarra\Library\Cascadeur\Inbox\lab_Menkara_v1_lab.fbx`
6. **Rig Mode Helper** — «Enter rig mode to rig the imported model?» → **No**  
   (для lab достаточно просмотра; rig — отдельный шаг позже)
7. Outliner: `Menkara_Body`, `Armor`, `00_Menkara`, … — модель на месте.

## Почему Reload scripts «ничего не сделал»

Reload scripts **не показывает сообщение** — он молча обновляет меню.

Частые причины, почему кажется, что ничего не произошло:

| Причина | Что делать |
|---------|------------|
| Ищешь пункт не там | Команда в **подменю**: **Commands → Viu → LabImport** (точка в имени = submenu) |
| Нажали Reload **commands** | Нужен **Reload scripts** — только он подхватывает **новые** `.py` |
| Скрипт не в той папке | `U:\Cascadeur\App\Cascadeur\resources\scripts\python\commands\` |
| Ошибка в `.py` | **Window → Event log** — там traceback |
| Первый deploy | Иногда нужен **перезапуск Cascadeur** |

Проверка: `cascadeur_status` в чате Вью.

## Python Console (обход Commands menu)

Если Reload scripts не помогает:

1. Lab создаёт  
   `U:\Viu\.viu\lab\cascadeur\artifacts\viu_lab_import_console.py`
2. Cascadeur: **Window → Python console**
3. **Load** → выбрать этот файл → **Execute**
4. В Event log: `Viu lab import OK: ...`

## Куда класть command-скрипт

```
U:\Cascadeur\App\Cascadeur\resources\scripts\python\commands\
  viu_lab_import.py
  viu_lab_pending.json
```

`command_name()` → `"Viu.LabImport"` → пункт **Viu → LabImport**.

## Автоматизация без Vision

Вью **не тыкает** по UI вслепую. Варианты:

- Python API: `FbxLoader.import_scene()` (console/command)
- File → Import вручную (проверено)
- **Vision позже** — только проверка скрина (welcome vs модель), не поиск кнопок

## Следующий шаг

Export → `U:\Anabarra\Animations` → «Обновить аниматор» в Unity.
