"""Provenance ассетов: источник, лицензия, можно ли в билд Анабарры."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Лицензии, при которых модификация + личная/игра-сборка обычно ок.
# ND / NC — отдельно (см. license_ok_for_anabarra_build).
LICENSE_ALLOWS_GAME_MODIFY: Tuple[str, ...] = (
    "cc0",
    "cc-by",
    "cc-by-4.0",
    "cc-by-sa",
    "cc-by-sa-4.0",
    "beerware",
    "public-domain",
    "mine",
)

_NC_MARKERS = ("nc", "noncommercial", "non-commercial", "non commercial")


@dataclass
class ProvenanceEntry:
    """Карточка происхождения одного пака / тела / клипа."""

    id: str
    title: str
    source: str  # smutbase | patreon | mine | cascadeur | other
    author: str = ""
    license: str = ""
    url: str = ""
    local_path: str = ""
    mascot_category: str = ""  # Women, Animations, …
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    credits: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ProvenanceEntry":
        tags = raw.get("tags") or []
        credits = raw.get("credits") or []
        return cls(
            id=str(raw["id"]),
            title=str(raw.get("title") or raw["id"]),
            source=str(raw.get("source") or "other"),
            author=str(raw.get("author") or ""),
            license=str(raw.get("license") or ""),
            url=str(raw.get("url") or ""),
            local_path=str(raw.get("local_path") or ""),
            mascot_category=str(raw.get("mascot_category") or ""),
            notes=str(raw.get("notes") or ""),
            tags=[str(t) for t in tags],
            credits=[str(c) for c in credits],
        )


def normalize_license(text: str) -> str:
    t = (text or "").strip().lower()
    t = t.replace("creative commons", "cc")
    t = re.sub(r"\s+", " ", t)
    t = t.replace("attribution", "by").replace("sharealike", "sa")
    t = t.replace("noderivatives", "nd").replace("no derivatives", "nd")
    t = t.replace("noncommercial", "nc").replace("non-commercial", "nc")
    # Частые формы → короткий код
    if "cc0" in t or "public domain" in t or t == "cc0":
        return "cc0"
    if "beerware" in t:
        return "beerware"
    if t in ("mine", "own", "self"):
        return "mine"
    m = re.search(r"cc[\s-]*by(?:[\s-]+(nc))?(?:[\s-]+(sa|nd))?(?:[\s-]*4\.0)?", t)
    if m:
        parts = ["cc-by"]
        if m.group(1):
            parts.append("nc")
        if m.group(2):
            parts.append(m.group(2))
        code = "-".join(parts)
        if "4.0" in t:
            return code + "-4.0"
        return code
    if "by-nd" in t or "by nd" in t:
        return "cc-by-nd-4.0" if "4.0" in t else "cc-by-nd"
    return t.replace(" ", "-")[:64]


def license_allows_derivatives(license_text: str) -> bool:
    code = normalize_license(license_text)
    if code == "mine":
        return True
    low = code.lower().replace("_", "-")
    if re.search(r"(^|-)nd($|-)", low) or "noderiv" in low:
        return False
    raw = (license_text or "").lower()
    if "no derivatives" in raw or "no-derivatives" in raw:
        return False
    return True


def license_has_nc(license_text: str) -> bool:
    code = normalize_license(license_text)
    low = code.lower()
    if re.search(r"(^|-)nc($|-)", low):
        return True
    return any(m in (license_text or "").lower() for m in _NC_MARKERS if len(m) > 2)


def license_ok_for_anabarra_build(
    license_text: str,
    *,
    personal_only: bool = True,
    will_modify: bool = True,
) -> Tuple[bool, str]:
    """Можно ли класть ассет в пайплайн Анабарры.

    personal_only=True — игра «для себя» (канон Вью).
    will_modify=True — Shrinkwrap / Rigify / FaceGen / ретаргет.
    """
    code = normalize_license(license_text)
    if not code:
        return False, "лицензия не указана — заполни provenance"
    if code == "mine":
        return True, "своя работа"
    if code == "patreon" or code.startswith("patreon"):
        return False, "Patreon без явного разрешения автора — не в билд"
    if license_has_nc(license_text) and not personal_only:
        return False, "NC: нельзя при коммерческом распространении"
    if will_modify and not license_allows_derivatives(license_text):
        if personal_only:
            return (
                True,
                "ND: для личной сборки ок; публично распространять модификацию нельзя",
            )
        return False, "ND: нельзя распространять производные"
    if code in LICENSE_ALLOWS_GAME_MODIFY or code.startswith("cc-by"):
        return True, f"лицензия {code}"
    if code.startswith("cc"):
        return True, f"лицензия {code} (проверь условия)"
    return False, f"неизвестная лицензия: {code}"


# Архив: старый пилот Erisa (больше не основной).
PILOT_SHANYA_ERISA = ProvenanceEntry(
    id="shanya_erisa_redeyes",
    title="Shanya / Erisa body (RedEyes) — архив",
    source="smutbase",
    author="RedEyes (@x_RedEyes)",
    license="CC BY-ND 4.0",
    url="https://smutba.se/project/f66e34d7-fcbb-4a26-861c-7cd4fd0ab2cc/",
    local_path=r"U:\Desktop Mascot\Women",
    mascot_category="Women",
    notes="Снят с пилота. Основное тело теперь Tracer Beerware.",
    tags=["archive", "erisa", "body"],
    credits=[
        "Shapes: @therealcrute",
        "Base female mesh: ported from DaZStudio",
    ],
)

# Текущий пилот: Tracer cutdown, Beerware (скрин Дена, 2026-07-26).
PILOT_SHANYA_TRACER = ProvenanceEntry(
    id="shanya_tracer_beerware",
    title="Shanya working body — Tracer cutdown (Beerware)",
    source="smutbase",
    author="(см. страницу Smutbase / кредит Twitter·Bsky автора)",
    license="Beerware",
    url="",
    local_path=r"U:\Desktop Mascot\Women",
    mascot_category="Women",
    notes=(
        "Основное тело Шани для Анабарры. Free cutdown; скины в отдельных .blend + UI-скрипт. "
        "Beerware: можно ремиксы при сохранении notice; автор просит кредит. "
        "Фан-арт Overwatch — только личная Анабарра (не публичный релиз как продукт Blizzard). "
        "HS2-карта опциональна как лекало; Shrinkwrap не обязателен."
    ),
    tags=["pilot", "shanya", "tracer", "body", "beerware"],
    credits=[
        "Beerware — retain notice; optional beer for the author",
        "Credit author socials as requested on the project page",
    ],
)


def seed_pilot_entries() -> List[ProvenanceEntry]:
    return [PILOT_SHANYA_TRACER, PILOT_SHANYA_ERISA]
