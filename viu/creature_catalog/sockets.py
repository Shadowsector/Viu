"""Сокеты девушек (aim targets для NSFW / grab)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..config import Config
from .models import GIRL_SOCKETS
from .paths import girl_sockets_doc_path


def default_girl_sockets_payload() -> Dict[str, Any]:
    return {
        "version": 1,
        "comment": (
            "Empties / bones на каждой девушке. Penetrator aim → активный socket. "
            "Имена стабильные — не переименовывать без миграции анимаций."
        ),
        "sockets": list(GIRL_SOCKETS),
        "attach_hints": {
            "socket_oral": "у рта / челюсти, стрелка внутрь",
            "socket_vaginal": "таз, центр, стрелка внутрь",
            "socket_anal": "таз сзади, стрелка внутрь",
            "socket_hand_l": "ладонь L, для handjob / grab shaft",
            "socket_hand_r": "ладонь R",
            "socket_cleavage": "между грудей на sternum / chest bone",
        },
    }


def ensure_girl_sockets_doc(config: Config) -> Path:
    path = girl_sockets_doc_path(config)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(default_girl_sockets_payload(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return path


def list_girl_socket_ids() -> List[str]:
    return [s["id"] for s in GIRL_SOCKETS]
