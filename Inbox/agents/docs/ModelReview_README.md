# ModelReview — вход / выход

Папка для **просмотра всех моделей персонажей в UE** и принятия решения по каждой.
Решение Дена: грузить всех сразу и листать по одной.

## Структура

```
U:\Anabarra\ModelReview\
  in\                      ВХОД — то, что грузится в UE
    <slug>\
      <slug>.fbx           модель для импорта (UE не читает .blend)
      *.png / *.tga        текстуры плоско рядом (не embedded, без .fbm — меньше конфликтов)
      meta.json            откуда взято, рост, поза, проблемы, статус
  out\                     ВЫХОД — результат просмотра
    approved\<slug>\       одобренные (ссылка на исходник + решение)
    rejected\<slug>\       отклонённые + причина
    shots\<slug>.png       скриншот модели в сцене
    review_log.jsonl       журнал решений (одна строка на модель)
  _queue.json              очередь: 297 персонажей, лучший файл, все копии
  _СПИСОК.md               то же человеческим языком, по источникам
```

**Расклад текстур — плоский.** FBX ссылается на голые имена файлов
(`path_mode="STRIP"`), картинки лежат в той же папке. UE находит их без
дополнительных настроек; никаких `textures\` и `<slug>.fbm\`.

## Что считается моделью

Только **персонажи** (бипеды, квады, монстры). Не входят:

- пропсы, мебель, окружение (`Desktop Mascot\Props`, `Toys`, юнити-сторед);
- отдельные части тела (гениталии из `Desktop Mascot\Cocks` — это пропсы, не персонажи);
- анимационные FBX (`Idle`, `Run`, `X Bot@…`, `Slime_Collect` и т.п.);
- варианты поз одного персонажа (`_apose`, `_tpose`, `_aligned`, `Shanya_quad_*`) — свёрнуты в одного.

## Источники (лучший файл на персонажа)

| Источник | Штук | Что это |
|---|---|---|
| `Anabarra\Inbox\creatures` | 101 | основной пул |
| `Library\Lust\<char>\body` | 44 | чужая игра, уже риггованные |
| `Desktop Mascot\{Women,Monsters}` | 82 | разрозненные модели |
| `Library\Lab2\00_Trash` | 37 | то, что уцелело после чистки дублей |
| `Unity\Anabarra\Assets\{Characters,Monsters}` | 20 | уже в игре |
| `3D Models` | 7 | RE / Shanya |
| `Library\Lab\Creatures\Prepared` | 5 | подготовленные (оригинал утерян) |
| `Viu\sandbox\biped_scan` | 1 | прошлая стандартизация |

Всего **297** персонажей: 112 уже в каталоге, **185 вне каталога**.

## Контракт

- `in\<slug>\` — **единица просмотра**. Один персонаж = одна папка.
- Если модель уже `.fbx` (Lust, Unity, часть Inbox) — копируется как есть, текстуры копируются плоско.
- Если `.blend` — headless Blender: `export_creature_fbx(embed_textures=False, path_mode="STRIP")`.
  Геометрия исходников не меняется, экспорт идёт через временные дубли.
- `meta.json` пишется всегда:
  `slug`, `name`, `source`, `source_root`, `source_ext`, `source_mb`, `in_catalog`,
  `locomotion`, `size_class`, `catalog_height_m`, `exported_at`, `alternates[]`,
  `fbx`, `height_m` (bbox мешей персонажа, метры), `export_ok`, `export_message`,
  `textures_copied`, `texture_layout`, `fbx_texture_refs`, `issues[]`, `seconds`.
- `issues[]`: `export_failed`, `no_armature`, `height_unmeasured`,
  `textures_not_linked`, `no_textures`.
- `out\review_log.jsonl` — по строке на решение:
  `{"slug": "...", "verdict": "approve|skip|reject|resize", "height_m": 1.70, "comment": "...", "at": "..."}`
- Рост, введённый в сцене, **применяется к модели сразу** и пишется в `meta.json` + `out`.

**Известное ограничение.** Дампы Unity / Lust / части Mascot не содержат в FBX
ссылок на текстуры (`fbx_texture_refs: false`, issue `textures_not_linked`).
Файлы текстур рядом лежат, но UE сам их не подключит — на это есть отдельный
проход привязки (ниже).

## Пайплайн (Blender, без UE)

Всё headless: `C:\Blender\5.2\blender.exe -b --factory-startup --python <скрипт> -- <args.json>`.
Скрипты лежат в `C:\Users\Den\AppData\Local\Temp\opencode\` (сессионные).

1. **Сборка входа** — `review_export.py`.
   - `.blend` → FBX через `export_creature_fbx(embed_textures=False, path_mode="STRIP")`
     (переиспользован модуль `U:\Viu\viu\creature_catalog\_creature_blender_shared.py`,
     геометрия исходников не меняется — экспорт идёт через временные дубли);
   - `.fbx` → копирование как есть + текстуры плоско рядом;
   - `meta.json` на каждую модель. Резюмируемо: готовые папки пропускаются.
2. **Привязка текстур** — `blender_rewire_fbx.py`, режим `wire`.
   Импортирует FBX, находит картинки в папке и подключает их к материалам
   по именам (`Belf_F_Body_01_M` → `Belf_F_Body_01_D.tga`; материал `No Name` →
   по имени меша `OrcMan_Body` → `OrcMan_Body.png`), выгружает FBX заново
   со ссылками на имена файлов. Попутно замеряет рост.
3. **Превью** — тот же скрипт, режим `thumb` (или `shots_dir` в режиме `wire`):
   ортокамера спереди, EEVEE, `out\shots\<slug>.png`.
4. **Страница просмотра** — `make_contact_sheet.py` → `out\_review.html`
   (сетка превью с ростом, источником и замечаниями, фильтры по проблемам).

**Зачем привязка в Blender, а не в UE.** UE импортирует только те текстуры,
которые прописаны в FBX. Blender при импорте умеет искать картинки по имени
и делает это сам, поэтому «собрать материалы в Blender и перевыгрузить FBX» —
самый короткий путь: после этого и UE, и любой другой движок видят текстуры.

**Масштаб.** У Lust-дампов файлы в сантиметрах (рост 0.013 м) и разного
множителя внутри набора — единой нормы нет. Поэтому масштаб в FBX не правится:
рост замеряется и записывается в `meta.json`, а модель подгоняется под
введённый Деном рост уже в сцене просмотра (равномерное масштабирование).

## Blender MCP

В Blender 5.2 есть встроенный MCP-аддон (extension `bl_ext.user_default.mcp`),
он поднимает TCP-сокет на `localhost:9876` и принимает
`{"type":"execute","code":"<python>","strict_json":true}`.

Мост в OpenCode — `U:\Viu\tools\blender_mcp_bridge.js` (Node, без зависимостей),
зарегистрирован в `C:\Users\Den\.config\opencode\opencode.jsonc` как `blender-mcp`.
Инструменты: `blender_status` (связь + краткое состояние сцены) и
`blender_execute` (выполнить Python, результат — в переменной `result`).

Запуск Blender с сервером:

```
blender.exe -b --online-mode --command blender_mcp --port 9876
```

или в GUI: System → MCP → Start.

Две грабли, которые уже вылечены:
- аддон стоял дважды (легаси `scripts\addons\mcp` + extension) → `blender_mcp`
  регистрировался дважды и запуск падал. Легаси-копия переложена в
  `scripts\mcp_legacy_backup` (не удалена);
- в песочнице MCP-аддона запрещён `bpy.ops.wm.read_factory_settings` —
  вместо него `bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)`.

## Статус

- [x] Папки созданы
- [x] Очередь собрана (`_queue.json`, `_СПИСОК.md`)
- [x] Пилот 5 моделей: `ada_wong` 1.91 м / 55 МБ, `alexa` 1.74 м / 8.5 МБ,
      `tauren1` 3.18 м / 7.7 МБ, `orc_man`, `perlica`
- [x] Привязка текстур в Blender проверена на живых моделях
      (`orc_man` — материал `No Name` → `OrcMan_Body.png`; `blood_elf` —
      10 материалов `_M` → `_D`); превью совпадают с ожиданием
- [x] Blender MCP поставлен и проверен (`blender_status` отвечает)
- [ ] Экспорт всех в `in\` (идёт в фоне)
- [ ] Привязка текстур + превью для всех `.fbx`-источников
- [ ] Превью для всех `.blend`-источников
- [ ] Импорт в UE (`/Game/ModelReview/`)
- [ ] Сцена + вид «по одной» + кнопки (Пропустить / Подтвердить / Подогнать рост до N м)
- [ ] Журнал решений в `out\`

## Что уже вылечено по пути

- встроенные текстуры раздували FBX в 5 раз (`ada_wong` 280 МБ → 55 МБ);
- Blender складывал копии текстур в `<slug>.fbm\` и дублировал в `textures\` —
  теперь всё плоско рядом с FBX;
- рост считался по самому многополигонному мешу (`ada_wong` выходила 0.28 м) —
  теперь bbox всех мешей персонажа, без пола и пропсов;
- `_pick_armature` выбирал арматуру по числу deform-костей, из-за чего у
  Rigify-персонажей (`dennis`) выигрывал `metarig`, к которому меши не
  привязаны, и экспорт падал. Теперь приоритет — число привязанных мешей;
- у моделей, где риг не привязан к мешам (`bigcuck`), FBX выгружается как
  статический меш с пометкой `no_skinned_mesh`, а не падает.
