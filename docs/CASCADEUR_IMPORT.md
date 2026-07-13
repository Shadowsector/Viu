# Import FBX в Cascadeur — пошагово

Для лаборатории Вью и ручной работы Дена. Официальные docs:
[Import FBX/DAE](https://cascadeur.com/help/getting_started/import_fbxdae),
[Import from Blender](https://cascadeur.com/help/getting_started/import_from_blender),
[Python Commands](https://cascadeur.com/help/tools/animation_tools/python_scripting_in_cascadeur).

## Почему welcome screen и нет модели

1. **Welcome** — нет открытой **сцены** (scene tab). Import идёт в текущую сцену.
2. **Reload scripts «ничего не сделал»** — скрипт лежал не там (`scripts/python/user` вместо `resources/scripts/python/commands`), либо нажали **Reload commands** (он **не** подхватывает новые файлы).
3. **Без Vision** Вью не знает координаты кнопок UI — только Python-команда, File→Import или ассоциация `.fbx`.

## Куда класть Python-команды

```
U:\Cascadeur\App\Cascadeur\resources\scripts\python\commands\
```

Файлы: `viu_lab_import.py`, `viu_lab_pending.json`.

Проверка: `cascadeur_status` в чате Вью — блок **Commands**.

После первого deploy:

1. **Commands → Reload scripts** (именно scripts!)
2. В меню Commands должен появиться **Viu.Lab Import**
3. Если нет — **перезапуск Cascadeur**

`VIU_CASCADEUR_SCRIPTS=` — только если у тебя кастомный `ScriptsDir` в `settings.ini`.

## Ручной импорт (UI) — Blender FBX → Cascadeur

Персонаж из Blender (Menkara и т.п.):

1. **Фокус** — Cascadeur активное окно (у тебя: клик по 3-му монитору).
2. **New scene** — если welcome / нет вкладки сцены.
3. **File → Import → Fbx/Dae**
4. В диалоге Import:
   - **Preset:** **Model** (скелет + mesh из FBX) или **Scene** (вся сцена)
   - **Import mode:** **Add new**
   - **Meshes:** включено
   - **Animation:** по желанию (для T-pose/static можно выкл.)
   - **Fbx up axis:** **Y** (как у Blender export)
5. **Import** → выбрать  
   `U:\Anabarra\Library\Cascadeur\Inbox\lab_Menkara_v1_lab.fbx`
6. Проверить Outliner — armature + mesh.

### Частые проблемы (из docs)

| Симптом | Что проверить |
|---------|----------------|
| Модель огромная/крошечная | Scale в Blender (Unit Scale 0.01), Apply transforms |
| Нет скелета | Preset Model/Scene, не Animation |
| Welcome не уходит | New scene вручную |
| Текстуры | Отдельно, после import mesh |

## Автоматизация Вью (lab шаг 6)

1. Deploy `viu_lab_import.py` в `.../commands/`
2. `viu_lab_pending.json` с путём FBX
3. Фокус окна Cascadeur (`SetForegroundWindow`, без мыши когда ты дома)
4. Команда **Viu.Lab Import** создаёт **New scene** если нужно и вызывает `FbxLoader.import_scene()`

Vision понадобится позже, чтобы **проверить** скрин (welcome vs модель в viewport) — не для кликов по кнопкам.

## Следующий шаг пайплайна

Export из Cascadeur → `U:\Anabarra\Animations` → «Обновить аниматор» в Unity.
