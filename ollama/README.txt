================================================================================
  OLLAMA / JAILBREAK — КАК ПРАВИТЬ (пошагово)
================================================================================

Папка:  U:\Viu\ollama\

ДВА ТИПА ФАЙЛОВ
--------------
  Modelfile.viu-cydonia.example   — ШАБЛОН из обновления Viu. НЕ для Ollama.
  Modelfile.viu-cydonia           — ТВОЙ рабочий файл. Его читает ollama create.

То же для: viu-magnum, viu-command-r, viu-qwen32.

Почему в проводнике/IDE видны только *.example?
  Рабочие Modelfile в .gitignore — Cursor их может не показывать.
  Открой Блокнотом напрямую:  U:\Viu\ollama\Modelfile.viu-cydonia

Если рабочего файла НЕТ — создай копию шаблона:

  cd /d U:\Viu
  copy /y ollama\Modelfile.viu-cydonia.example ollama\Modelfile.viu-cydonia

Потом правь ТОЛЬКО файл БЕЗ .example


ШАГ 1 — ОТКРЫТЬ И ПОПРАВИТЬ ТЕКСТ
---------------------------------
  notepad ollama\Modelfile.viu-cydonia

Меняй текст внутри блока:

  SYSTEM """
  ... твой jailbreak / голос / без тормозов ...
  """

Строка FROM ... не трогай, если не знаешь зачем.


ШАГ 2 — ПЕРЕСОБРАТЬ МОДЕЛЬ В OLLAMA
------------------------------------
Ollama кэширует старый system. После правки файла ОБЯЗАТЕЛЬНО:

  cd /d U:\Viu

  rem ollama stop БЕЗ имени модели — ошибка (нужен аргумент). Можно так:
  ollama ps
  rem если видишь viu-cydonia в списке:
  ollama stop viu-cydonia

  rem если rm пишет not found — это ОК, модели ещё не было:
  ollama rm viu-cydonia

  ollama create viu-cydonia -f ollama\Modelfile.viu-cydonia

Или всё сразу:

  scripts\create_viu_ollama_models.bat

Проверка, что подхватился НОВЫЙ текст:

  ollama show viu-cydonia --modelfile

Сравни SYSTEM с тем, что в Modelfile.viu-cydonia на диске.


ЕСЛИ create ПАДАЕТ: command must be one of "from"…
-------------------------------------------------
Значит Ollama не видит цельный блок SYSTEM """ … """ (часто UTF-16
после «Сохранить как Юникод» в Блокноте, или битый рабочий файл).

  1) Перезалей рабочий файл из шаблона (UTF-8):

     cd /d U:\Viu
     copy /y ollama\Modelfile.viu-cydonia.example ollama\Modelfile.viu-cydonia

  2) Если снова ошибка — принудительно UTF-8 через PowerShell:

     powershell -NoProfile -Command ^
       "Get-Content -LiteralPath 'ollama\Modelfile.viu-cydonia.example' -Encoding UTF8 | Set-Content -LiteralPath 'ollama\Modelfile.viu-cydonia' -Encoding utf8"

  3) Снова:

     ollama create viu-cydonia -f ollama\Modelfile.viu-cydonia

Внутри SYSTEM не должно быть тройных кавычек """.
Файл правь в VS Code / Notepad++ как UTF-8 (не «UTF-16 LE»).


ШАГ 3 — ВКЛЮЧИТЬ МОДЕЛЬ В ВЬЮ
------------------------------
В .env:
  VIU_MODEL_REFLECT=viu-cydonia

Или в окне Viu — выпадающий список «Чат:» сверху.

Перезапусти Viu. Новый чат (старая история тянет старый тон).


ОБНОВЛЕНИЕ VIU
--------------
После обновления Viu (zip/git):
  — шаблоны *.example обновятся сами;
  — твои Modelfile.viu-* (без .example) СОХРАНЯЮТСЯ (если Viu свежий);
  — если локальные пропали — снова copy из .example и правь заново;
  — потом снова ollama create (шаг 2).

Подробнее: docs\LLM_ROLES.md
