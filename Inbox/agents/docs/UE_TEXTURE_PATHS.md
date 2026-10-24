# Текстуры и FBX: почему они «теряются» при переносе

Проверено на домашней машине 2026-10-24, UE 5.8 (`UnrealEditor-Cmd` + Python), AnimLab.

## Что записано в наших FBX

Все FBX в `U:\Anabarra\ModelReview\in\<slug>\` хранят **абсолютные пути экспортной машины**:

```text
U:\Anabarra\ModelReview\in\ru\Ru_body_normal.png
```

`path_mode` при экспорте был не `STRIP`, а copy/absolute. На домашней машине это работает, потому что путь существует. При переносе на другую машину путь не существует — и первое, что приходит в голову, «текстуры потерялись».

## Что делает UE 5.8 (Interchange)

Если абсолютный путь из FBX не существует, импортёр **берёт файл с тем же именем из папки самого FBX**. Это не настройка и не плагин — так работает `Interchange` по умолчанию.

## Эксперимент

Взяли `humangirl.fbx` + 4 текстуры и сделали три копии:

| копия | что в FBX | папка |
|---|---|---|
| `C_raw` | без правок: `U:\Anabarra\...` (на этой машине путь есть) | `C:\viu_staging\pathtest\C_raw` |
| `A_missing` | тот же путь, но несуществующий: `Z:\qqq…q\` (длина байт в байт) | `C:\viu_staging\pathtest\A_missing` |
| `B_dot` | относительный: `.\\.\\.\…\` (тоже длина байт в байт) | `C:\viu_staging\pathtest\B_dot` |

Все три импортированы в `/Game/PathTest/<копия>`.

Результат одинаковый:

```text
Texture2D 4, MaterialInstanceConstant 4, SkeletalMesh 1, Skeleton 1
ActorPC_Body1              DiffuseColorMap -> /Game/PathTest/<копия>/ActorPC_Body
ActorPC_Face               DiffuseColorMap -> /Game/PathTest/<копия>/ActorPC_Body
ActorPC_EyeBall            DiffuseColorMap -> /Game/PathTest/<копия>/Succubus_EyeBall
HumanGirl_Aliance_Healer_D_Hair_02  DiffuseColorMap -> Hair, NormalMap -> Hair_normal
```

Ни одного пустого текстурного параметра. То есть **чинить пути в FBX не нужно**: достаточно положить текстуры рядом с FBX, плоско.

## Отсюда правила для посылок

1. Текстуры — плоско в папке с FBX, имена — ровно как в FBX (регистр не важен).
2. `textures/` подпапку UE не просматривает: если текстуры лежат там, материалы станут серыми.
3. Пересобирать FBX ради путей не нужно — но если когда-нибудь будем экспортировать заново, правильнее `path_mode='STRIP'`.
4. Импорт проверять headless, а не глазами по логу редактора:

```powershell
& "U:\Unreal\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" `
  "C:\Users\Den\Documents\Unreal Projects\AnimLab\AnimLab.uproject" `
  -run=pythonscript -script="<скрипт>.py" -nullrhi -unattended -nopause -nosplash
```

`-nullrhi` важен: без него старт занимает ~10 минут на компиляцию шейдеров, с ним — секунды.

## Что показал импорт пилота (те же 4 модели, что в `payload/h-2026-10-23-001`)

| slug | результат | Texture2D | MaterialInstance | Mesh | пустых текстур-параметров |
|---|---|---|---|---|---|
| `humangirl` | ok | 4 | 4 | SkeletalMesh 1 | 0 |
| `ru` | ok | 29 | 22 | SkeletalMesh 1 | 0 |
| `alexa` | ok | 7 | 9 | SkeletalMesh 1 | 0 |
| `shanya` | ok | 10 | 24 | SkeletalMesh 1 | 0 |

`ru`: импорт проходит, но Interchange пишет ошибку на пустую часть меша `o_acs_head_barg_001` («не найдены полигоны»). Это не мешает остальным 22 материалам и скелету — модель импортируется. Просто в логе будет 3 error-строки; на них можно не реагировать.

`shanya`: 10 текстур на 24 материала — это нормально, у неё в исходнике нет body-текстуры, часть материалов использует общий скин.
