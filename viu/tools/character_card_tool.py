"""Инструменты: карточки 【AIS_Chara】 → JSON → поиск ассетов."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

from ..ais_asset_match import (
    character_cards_extract_dir,
    ensure_ais_inbox_layout,
    inbox_ais_assets_dir,
    inbox_ais_cards_dir,
    match_appearance_to_assets,
)
from ..ais_chara import (
    dump_appearance_json,
    format_card_report,
    load_ais_chara,
    looks_like_ais_chara,
)
from ..character_card_png import (
    dump_json_payloads,
    format_probe_report,
    probe_png,
)
from .base import AgentContext, Tool, ToolResult


def _default_cards_dir(ctx: AgentContext) -> Path:
    ensure_ais_inbox_layout(ctx.config)
    return inbox_ais_cards_dir(ctx.config)


class CharacterCardProbeTool(Tool):
    name = "character_card_probe"
    description = (
        "Разобрать PNG 【AIS_Chara】 → AnabarraAppearance JSON. "
        "По умолчанию Inbox/ais_cards (или path=). Нужен msgpack. "
        "Дамп: .viu/character_cards_extract/*__anabarra.json"
    )
    parameters = {
        "path": "файл/каталог PNG (default Inbox/ais_cards)",
        "limit": "макс. файлов (default 40)",
        "dump": "1/0 сохранить JSON (default 1)",
        "full": "1/0 полный MessagePack (default 1)",
        "copy_from": "опционально: скопировать *.png из этого каталога в ais_cards",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        ensure_ais_inbox_layout(ctx.config)
        cards_dir = inbox_ais_cards_dir(ctx.config)
        copy_from = str(args.get("copy_from") or "").strip()
        copied = 0
        if copy_from:
            src = Path(copy_from)
            if not src.is_dir():
                return ToolResult(False, f"copy_from не каталог: {src}")
            for png in list(src.glob("*.png")) + list(src.glob("*.PNG")):
                dest = cards_dir / png.name
                if not dest.exists():
                    shutil.copy2(png, dest)
                    copied += 1

        raw_path = str(args.get("path") or cards_dir).strip()
        full = str(args.get("full", "1")).strip().lower() not in (
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
            limit = int(args.get("limit") or 40)
        except (TypeError, ValueError):
            limit = 40
        limit = max(1, min(limit, 200))

        target = Path(raw_path)
        if not target.exists():
            return ToolResult(
                False,
                f"Путь не найден: {target}\n"
                f"Положи PNG в {cards_dir} или укажи path= / copy_from=U:\\TempUnityCard",
            )

        files: List[Path]
        if target.is_dir():
            files = sorted(set(target.glob("*.png")) | set(target.glob("*.PNG")))[:limit]
        else:
            files = [target]

        if not files:
            return ToolResult(
                False,
                f"Нет PNG в {target}.\n"
                f"Скопируй карточки в {cards_dir} "
                f"или character_card_probe copy_from=U:\\TempUnityCard",
            )

        out_dir = character_cards_extract_dir(ctx.config)
        ais_reports: list[str] = []
        ais_ok = 0
        dumped: list[str] = []
        missing_msgpack = False
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
                if "msgpack" in (card.error or "").lower():
                    missing_msgpack = True
                if card.parse_level == "full" and not card.error:
                    ais_ok += 1
                elif card.parse_level in ("blocks", "full"):
                    ais_ok += 1
                if dump and card.parse_level == "full":
                    out = dump_appearance_json(
                        card, out_dir / f"{fpath.stem}__anabarra.json"
                    )
                    dumped.append(str(out))
                    full_path = out_dir / f"{fpath.stem}__ais.json"
                    full_path.write_text(
                        json.dumps(card.to_dict(), ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    dumped.append(str(full_path))
            else:
                generic_results.append(probe_png(fpath, deep_scan=False))

        lines = [
            f"Character cards: {len(files)} file(s)",
            f"ais_cards dir: {cards_dir}",
            f"copied_from_extra: {copied}",
            f"AIS_Chara parsed ok: {ais_ok}",
            f"extract: {out_dir}",
            "",
        ]
        lines.extend(ais_reports[:80])
        if len(ais_reports) > 80:
            lines.append(f"… и ещё {len(ais_reports) - 80}")

        if generic_results:
            if dump:
                dumped.extend(str(p) for p in dump_json_payloads(generic_results, out_dir))
            lines.append("")
            lines.append("--- non-AIS PNG probe ---")
            lines.append(format_probe_report(generic_results, max_preview=300))

        summary = {
            "files": len(files),
            "ais_ok": ais_ok,
            "copied": copied,
            "dumped": dumped[:40],
            "cards_dir": str(cards_dir),
            "assets_dir": str(inbox_ais_assets_dir(ctx.config)),
            "extract_dir": str(out_dir),
            "missing_msgpack": missing_msgpack,
        }
        lines.append("")
        lines.append("--- summary_json ---")
        lines.append(json.dumps(summary, ensure_ascii=False, indent=2))
        report = "\n".join(lines)

        if missing_msgpack:
            report += (
                "\n\nFAIL: нет msgpack. На ПК Дена: pip install msgpack\n"
                "Потом снова character_card_probe."
            )
            return ToolResult(False, report)
        if ais_ok == 0 and not generic_results:
            return ToolResult(False, report)
        if ais_ok == 0:
            report += "\n\nWARN: AIS не разобран полностью."
        return ToolResult(True, report)


class CharacterCardDeserializeTool(Tool):
    name = "character_card_deserialize"
    description = (
        "Один PNG 【AIS_Chara】 → AnabarraAppearance JSON "
        "(face_shape_values, hair_ids). path=файл.png"
    )
    parameters = {
        "path": "путь к PNG",
        "dump": "1/0 сохранить JSON (default 1)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        ensure_ais_inbox_layout(ctx.config)
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
        if "msgpack" in (card.error or "").lower():
            return ToolResult(False, report + "\n\npip install msgpack")
        if dump and card.parse_level == "full":
            out = character_cards_extract_dir(ctx.config) / f"{path.stem}__anabarra.json"
            dump_appearance_json(card, out)
            report += f"\n\ndumped: {out}"
        ok = card.parse_level == "full" and not card.error
        return ToolResult(ok, report)


class CharacterCardMatchTool(Tool):
    name = "character_card_match"
    description = (
        "Прочитать AnabarraAppearance JSON и поискать подходящие файлы "
        "в Inbox/ais_assets (по hair_ids, имени, числам в имени, kkex). "
        "json=путь к *__anabarra.json; assets=каталог (default ais_assets)."
    )
    parameters = {
        "json": "путь к *__anabarra.json (или *__ais.json)",
        "assets": "каталог россыпи (default Inbox/ais_assets)",
        "dump": "1/0 сохранить отчёт match JSON (default 1)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        ensure_ais_inbox_layout(ctx.config)
        raw_json = str(args.get("json") or args.get("path") or "").strip()
        if not raw_json:
            extract = character_cards_extract_dir(ctx.config)
            cands = sorted(extract.glob("*__anabarra.json"))
            if not cands:
                return ToolResult(
                    False,
                    "Нужен json= к appearance. Сначала character_card_probe / deserialize.\n"
                    f"Искала в {extract} — пусто.",
                )
            json_path = cands[0]
        else:
            json_path = Path(raw_json)
        if not json_path.is_file():
            return ToolResult(False, f"JSON не найден: {json_path}")

        assets = Path(
            str(args.get("assets") or inbox_ais_assets_dir(ctx.config)).strip()
        )
        dump = str(args.get("dump", "1")).strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )

        report = match_appearance_to_assets(json_path, assets)
        text = report.format()
        text += "\n\n--- match_json ---\n"
        text += json.dumps(report.to_dict(), ensure_ascii=False, indent=2)[:8000]

        if dump:
            out = (
                character_cards_extract_dir(ctx.config)
                / f"{json_path.stem}__match.json"
            )
            out.write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            text += f"\n\ndumped: {out}"

        # пустая папка ассетов — не ошибка: Ден ещё скинет
        ok = True
        if report.notes.startswith("WARN") and not report.hits:
            ok = True
        return ToolResult(ok, text)


class CharacterCardSetupTool(Tool):
    name = "character_card_setup"
    description = (
        "Создать Inbox/ais_cards и Inbox/ais_assets + README. "
        "copy_from=U:\\TempUnityCard — скопировать PNG. "
        "probe=1 — сразу character_card_probe (нужен msgpack)."
    )
    parameters = {
        "copy_from": "каталог-источник PNG (опционально)",
        "open": "1/0 открыть ais_assets (default 1)",
        "probe": "1/0 сразу разобрать карточки в JSON (default 1)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        paths = ensure_ais_inbox_layout(ctx.config)
        cards = inbox_ais_cards_dir(ctx.config)
        assets = inbox_ais_assets_dir(ctx.config)
        copied = 0
        copy_from = str(args.get("copy_from") or "").strip()
        if copy_from:
            src = Path(copy_from)
            if src.is_dir():
                for png in list(src.glob("*.png")) + list(src.glob("*.PNG")):
                    dest = cards / png.name
                    if not dest.exists():
                        shutil.copy2(png, dest)
                        copied += 1
            else:
                return ToolResult(False, f"copy_from не каталог: {src}")

        do_open = str(args.get("open", "1")).strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        opened = ""
        if do_open:
            try:
                import os
                import subprocess
                import sys

                folder = str(assets)
                if sys.platform == "win32":
                    os.startfile(folder)  # type: ignore[attr-defined]
                    opened = f"Открыла проводник: {folder}"
                else:
                    subprocess.Popen(["xdg-open", folder], start_new_session=True)
                    opened = f"xdg-open: {folder}"
            except Exception as exc:  # noqa: BLE001
                opened = f"(open fail: {exc})"

        lines = [
            "AIS layout готов.",
            f"  cards:  {cards}  (PNG карточки)  copied={copied}",
            f"  assets: {assets} (скидывай ассеты вразнобой сюда)",
            f"  json:   {character_cards_extract_dir(ctx.config)}",
        ]
        if opened:
            lines.append(opened)

        do_probe = str(args.get("probe", "1")).strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        probe_ok = True
        if do_probe and (copied > 0 or any(cards.glob("*.png")) or any(cards.glob("*.PNG"))):
            lines.append("")
            lines.append("--- probe ---")
            probe_res = CharacterCardProbeTool().run(
                {"path": str(cards), "full": "1", "dump": "1", "limit": "40"},
                ctx,
            )
            lines.append(probe_res.content)
            probe_ok = probe_res.ok
        else:
            lines.extend(
                [
                    "",
                    "Дальше:",
                    "  1) character_card_probe — JSON из карточек",
                    "  2) скинь ассеты в ais_assets/",
                    "  3) character_card_match json=…__anabarra.json",
                ]
            )

        lines.append("")
        lines.append(
            "paths_json: " + json.dumps([str(p) for p in paths], ensure_ascii=False)
        )
        return ToolResult(probe_ok if do_probe else True, "\n".join(lines))
