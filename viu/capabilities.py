"""Что Вью умеет / не умеет — для чата, Telegram и work.

Короткий канон, чтобы LLM не выдумывала «базовые знания Cascadeur»
и «нужен специалист».
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .config import Config

# Главный текст — в reflect и notes. Держать коротким: модели иначе размывают.
CAPABILITY_BRIEF = """
## Что я реально умею по анимациям (не выдумывай иное)

Пайплайн цели:
**Comfy (видео-референс) → Cascadeur (MoCap / чистка) → Animations/ → Unity.**
Параллельно: Mixamo FBX → Inbox → каталог → Animator.

### Могу сама (инструменты / lab)
- **Comfy:** `comfy_mocap` / `comfy_triple` / `comfy_clip_pick` — промпт, 3 ракурса, kept mp4 в `Lab/Refs`.
- **Cascadeur:** `cascadeur_status`, `cascadeur_import_reference` / `cascadeur_mocap_assist`
  (pending + Commands **Viu.ImportReference**), `cascadeur_export_clip` → `Animations/shanya_<slug>.fbx`.
- **Blender:** чистый FBX для Cascadeur (`blender_export_cascadeur` / batch), риг-check персонажей.
- **Unity:** scan/sync анимаций, оверлей, «Обновить аниматор».
- **Каталог:** `animation_catalog_show` — граф `enters_from` / `exits_to`, чего не хватает.

### Не умею / ограничение
- **Не** «нарисую анимацию словами» и не заменю Cascadeur болтовнёй.
- Кнопку **Mocap** в Cascadeur API надёжно не жму — готовлю Reference + чеклист; MoCap на Timeline — клик Дена (или lab-assist).
- Не держу одновременно тяжёлый Comfy + Cascadeur + Unity на слабой VRAM — очередь lab.
- Не путаю роли: Blender ≠ MoCap-хаб между Comfy и Cascadeur в нашем контуре.

### Как отвечать на «создашь анимацию?» / «сможешь в Cascadeur?»
Конкретно, по шагам нашего пайплайна. Например:
«Да. Сначала `comfy_mocap` на действие из каталога → ты/я выбираем ракурс →
я готовлю Reference в Cascadeur → ты жмёшь Mocap на таймлайне →
`cascadeur_export_clip` → Unity. Скажи действие (или я возьму дыру из каталога).»
Не говори «базовые знания», «нужен специалист», «концепт-моделирование-текстуры».

### Вектор проекта
Читай/держи курс: `docs/COMFY_CASCADEUR_PIPELINE.md`, `docs/CASCADEUR.md`,
`docs/SHANYA_ANIMATIONS.md`, `docs/VIU_AUTOMATION_2026.md`, `vision.md`.
Цель — живая Шаня рядом с Деном, не абстрактный «пайплайн анимации».
""".strip()


_DOC_SNIPPETS = (
    "COMFY_CASCADEUR_PIPELINE.md",
    "CASCADEUR.md",
    "SHANYA_ANIMATIONS.md",
    "VIU_AUTOMATION_2026.md",
    "CREATURE_CATALOG.md",
)


def package_docs_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "docs"


def docs_vector_brief(*, max_chars: int = 2200) -> str:
    """Короткие выдержки из ключевых md — общий вектор, не весь GitHub."""
    root = package_docs_dir()
    chunks: List[str] = []
    budget = max_chars
    for name in _DOC_SNIPPETS:
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # первые содержательные строки после заголовка
        lines = [ln for ln in text.splitlines() if ln.strip()][:28]
        body = "\n".join(lines)
        if len(body) > 500:
            body = body[:500].rstrip() + "…"
        piece = f"### docs/{name}\n{body}"
        if len(piece) > budget:
            if budget < 200:
                break
            piece = piece[:budget].rstrip() + "…"
        chunks.append(piece)
        budget -= len(piece) + 2
        if budget <= 0:
            break
    if not chunks:
        return ""
    return "Вектор из docs (сжато):\n\n" + "\n\n".join(chunks)


def reflect_capability_notes(config: Config | None = None) -> str:
    """Блок для reflect system / notes."""
    parts = [CAPABILITY_BRIEF]
    brief = docs_vector_brief()
    if brief:
        parts.append(brief)
    if config is not None:
        try:
            from .vision import read_vision

            v = read_vision(config, max_chars=900)
            if v.strip():
                parts.append("--- vision (курс) ---\n" + v.strip())
        except OSError:
            pass
    return "\n\n".join(parts)
