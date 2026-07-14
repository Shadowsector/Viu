# Сарай — обзор

Пошаговая инструкция для Дена: **[`BARN_EDIT_STEPS.md`](./BARN_EDIT_STEPS.md)**  
(камера Instance → якоря → dollhouse → props → свет → чеклист).

Ниже — зачем это нужно и критерий «готово».

---

## Что уже есть

| Часть | Компонент |
|-------|-----------|
| Фасад → дверь → кукольный дом | `ShanyaOverlayCorridor` + `DollhouseWall` |
| Три режима камеры | Facade / Corridor / Instance (`OVERLAY_MODES.md`) |
| Якоря | CharacterStart, BarnEntrance, HomeRoot, TaskbarFeetLine |

---

## Критерий «сарай ок»

1. Снаружи фасад читается, Шаня у таскбара.  
2. W → к двери, вход; внутри видны пол, стена, стул/свет.  
3. S → выход без сломанной камеры.  
4. Хочется «посидеть» — не пустой серый ящик.

Props и анимации быта — `PROP_AFFORDANCES.md` + Mixamo из `SHANYA_ANIMATIONS.md`.
