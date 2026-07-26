"""Инструмент: разбор PNG с зашитым JSON кастомизации персонажа."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

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
        "Разобрать PNG «карточки» персонажей: вытащить JSON/текст из tEXt/zTXt/iTXt, "
        "хвоста после IEND и сырого скана. По умолчанию U:\\TempUnityCard. "
        "Пишет извлечённый JSON в .viu/character_cards_extract/ и краткий отчёт."
    )
    parameters = {
        "path": "файл .png или каталог (по умолчанию U:\\TempUnityCard)",
        "deep_scan": "1/0 — искать JSON в сырых байтах, если чанки пусты (default 1)",
        "limit": "макс. число файлов в каталоге (default 30)",
        "dump": "1/0 — сохранить JSON в .viu/character_cards_extract (default 1)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        raw_path = str(args.get("path") or DEFAULT_DIR).strip()
        deep = str(args.get("deep_scan", "1")).strip().lower() not in (
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

        if target.is_dir():
            results = probe_directory(target, deep_scan=deep, limit=limit)
        else:
            results = [probe_png(target, deep_scan=deep)]

        written: list[Path] = []
        if dump:
            out_dir = Path(ctx.config.root) / ".viu" / "character_cards_extract"
            written = dump_json_payloads(results, out_dir)

        report = format_probe_report(results, max_preview=800)
        if written:
            report += "\n\n--- dumped JSON ---\n"
            report += "\n".join(str(p) for p in written[:40])
            if len(written) > 40:
                report += f"\n… и ещё {len(written) - 40}"

        # компактный machine summary в конце — удобно Cursor'у
        summary = {
            "files": len(results),
            "ok": sum(1 for r in results if r.ok),
            "with_json": sum(
                1
                for r in results
                if any(p.kind in ("json", "base64_json") for p in r.payloads)
            ),
            "after_iend": sum(1 for r in results if r.after_iend_bytes > 0),
            "text_chunks": sum(1 for r in results if r.text_chunks),
            "dumped": [str(p) for p in written[:20]],
            "all_keys_sample": [],
        }
        keys: list[str] = []
        seen: set[str] = set()
        for r in results:
            for k in r.summary_keys:
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        summary["all_keys_sample"] = keys[:100]
        report += "\n\n--- summary_json ---\n"
        report += json.dumps(summary, ensure_ascii=False, indent=2)

        any_json = summary["with_json"] > 0
        if not results:
            return ToolResult(False, report + "\n\nНет PNG в каталоге.")
        if target.is_dir() and all(not r.ok and r.error for r in results):
            return ToolResult(False, report)
        # успех даже без JSON — формат мог быть неожиданным; Cursor разберёт отчёт
        note = ""
        if not any_json:
            note = (
                "\n\nWARN: JSON не извлечён. Смотри text_chunks / after_iend / "
                "bytes preview — возможно другой контейнер."
            )
        return ToolResult(True, report + note)
