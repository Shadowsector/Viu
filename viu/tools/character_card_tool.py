"""Инструмент: разбор PNG-карточек персонажей (AIS_Chara / JSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..ais_chara import (
    dump_appearance_json,
    format_card_report,
    load_ais_chara,
    looks_like_ais_chara,
)
from ..character_card_png import (
    dump_json_payloads,
    format_probe_report,
    probe_directory,
    probe_png,
)
from .base import AgentContext, Tool, ToolResult

DEFAULT_DIR = r"U:\TempUnityCard"


class CharacterCardProbeTool(Tool):
    name = "character_card_probe"
    description = (
        "Разобрать PNG-карточки: 【AIS_Chara】 (MessagePack после IEND — слайдеры лица, "
        "hair id) или JSON в чанках. По умолчанию U:\\TempUnityCard. "
        "Дамп AnabarraAppearance → .viu/character_cards_extract/."
    )
    parameters = {
        "path": "файл .png или каталог (по умолчанию U:\\TempUnityCard)",
        "deep_scan": "1/0 — сырой JSON-скан, если не AIS (default 0 для каталогов)",
        "limit": "макс. число файлов в каталоге (default 30)",
        "dump": "1/0 — сохранить appearance JSON (default 1)",
        "full": "1/0 — полный MessagePack-разбор AIS (нужен msgpack, default 1)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        raw_path = str(args.get("path") or DEFAULT_DIR).strip()
        deep = str(args.get("deep_scan", "0")).strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        dump = str(args.get("dump", "1")).strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        full = str(args.get("full", "1")).strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        try:
            limit = int(args.get("limit") or 30)
        except (TypeError, ValueError):
            limit = 30
        limit = max(1, min(limit, 200))

        target = Path(raw_path)
        if not target.exists():
            return ToolResult(
                False,
                f"Путь не найден: {target}\n"
                "Проверь, что файлы лежат в U:\\TempUnityCard (или передай path=).",
            )

        files: List[Path]
        if target.is_dir():
            files = sorted(set(target.glob("*.png")) | set(target.glob("*.PNG")))[:limit]
        else:
            files = [target]

        if not files:
            return ToolResult(False, f"Нет PNG в {target}")

        out_dir = Path(ctx.config.root) / ".viu" / "character_cards_extract"
        ais_reports: list[str] = []
        ais_ok = 0
        dumped: list[str] = []
        generic_results = []

        for fpath in files:
            try:
                raw = fpath.read_bytes()
            except OSError as exc:
                ais_reports.append(f"{fpath}: read error {exc}")
                continue
            if looks_like_ais_chara(raw):
                card = load_ais_chara(fpath, full=full)
                ais_reports.append(format_card_report(card))
                if card.parse_level in ("blocks", "full") and not (
                    card.error and card.parse_level == "header"
                ):
                    ais_ok += 1
                if dump and card.parse_level == "full":
                    out = dump_appearance_json(
                        card, out_dir / f"{fpath.stem}__anabarra.json"
                    )
                    dumped.append(str(out))
                    # полный card dict тоже
                    full_path = out_dir / f"{fpath.stem}__ais.json"
                    full_path.write_text(
                        json.dumps(card.to_dict(), ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    dumped.append(str(full_path))
            else:
                generic_results.append(probe_png(fpath, deep_scan=deep))

        lines = [
            f"Character cards: {len(files)} file(s)",
            f"AIS_Chara parsed ok: {ais_ok}",
            "",
        ]
        lines.extend(ais_reports[:60])
        if len(ais_reports) > 60:
            lines.append(f"… и ещё {len(ais_reports) - 60} AIS отчётов")

        if generic_results:
            if dump:
                dumped.extend(str(p) for p in dump_json_payloads(generic_results, out_dir))
            lines.append("")
            lines.append("--- non-AIS PNG probe ---")
            lines.append(format_probe_report(generic_results, max_preview=400))

        summary = {
            "files": len(files),
            "ais_ok": ais_ok,
            "ais_reports": len(ais_reports),
            "generic": len(generic_results),
            "dumped": dumped[:40],
            "format": "AIS_Chara MessagePack after IEND"
            if ais_ok
            else "unknown/mixed",
        }
        lines.append("")
        lines.append("--- summary_json ---")
        lines.append(json.dumps(summary, ensure_ascii=False, indent=2))

        report = "\n".join(lines)
        if ais_ok == 0 and not generic_results:
            return ToolResult(False, report)
        if ais_ok == 0:
            report += (
                "\n\nWARN: AIS_Chara не разобран. Нужен `pip install msgpack` "
                "или файлы другого формата."
            )
        return ToolResult(True, report)


class CharacterCardDeserializeTool(Tool):
    name = "character_card_deserialize"
    description = (
        "Десериализовать один PNG 【AIS_Chara】 в AnabarraAppearance "
        "(face_shape_values, hair_ids, parameter). path=файл.png"
    )
    parameters = {
        "path": "путь к PNG карточке",
        "dump": "1/0 сохранить JSON (default 1)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        path = Path(str(args.get("path") or "").strip())
        if not path.is_file():
            return ToolResult(False, f"Нужен path к PNG, получено: {path}")
        dump = str(args.get("dump", "1")).strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        card = load_ais_chara(path, full=True)
        report = format_card_report(card)
        report += "\n\n--- appearance_json ---\n"
        report += json.dumps(card.to_appearance().to_dict(), ensure_ascii=False, indent=2)
        if dump and card.parse_level == "full":
            out = (
                Path(ctx.config.root)
                / ".viu"
                / "character_cards_extract"
                / f"{path.stem}__anabarra.json"
            )
            dump_appearance_json(card, out)
            report += f"\n\ndumped: {out}"
        ok = card.parse_level == "full" and not card.error
        return ToolResult(ok, report)
