"""Тесты каталога существ."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.creature_catalog.auto_size import apply_size_to_same_stem, auto_apply_size_guesses
from viu.creature_catalog.lineup import build_lineup_job
from viu.creature_catalog.models import (
    GIRL_SOCKETS,
    suggest_locomotion_from_name,
    suggest_size_from_name,
)
from viu.creature_catalog.paths import creature_catalog_path, creatures_inbox_dir
from viu.creature_catalog.scanner import scan_creatures_inbox
from viu.creature_catalog.sockets import ensure_girl_sockets_doc, list_girl_socket_ids
from viu.creature_catalog.store import CreatureCatalogStore
from viu.tools import build_default_registry


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    lib = tmp_path / "Library"
    lib.mkdir()
    return Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        library_root=str(lib),
    ).ensure_dirs()


def test_creature_describe_parse_and_store(tmp_path, monkeypatch):
    from viu.creature_catalog.describe import _parse_vl, describe_creature
    from viu.creature_catalog.models import CreatureEntry, STATUS_SIZED

    en, ru, tags = _parse_vl(
        "EN: green goblin biped, warty skin\n"
        "RU: Зеленоватый гоблин, двуногий.\n"
        "TAGS: biped, goblin, green"
    )
    assert "goblin" in en.lower()
    assert "гоблин" in ru.lower()
    assert "biped" in tags

    cfg = _cfg(tmp_path, monkeypatch)
    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    png = tmp_path / "gob.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    e = CreatureEntry(
        id="abc123",
        path=str(tmp_path / "Goblin.fbx"),
        name="Goblin",
        size_class="small",
        locomotion="biped",
        status=STATUS_SIZED,
        photo_front=str(png),
    )
    store.upsert(e)
    store.save()

    def fake_ask(image_path, *, prompt, config, model=""):
        return True, (
            "EN: small green goblin warrior\n"
            "RU: Маленький зелёный гоблин-воин.\n"
            "TAGS: goblin, biped"
        )

    monkeypatch.setattr(
        "viu.creature_catalog.describe.ask_vision", fake_ask
    )
    monkeypatch.setattr(
        "viu.creature_catalog.describe.pick_vision_model", lambda *_a, **_k: "llava"
    )
    ok, msg = describe_creature(cfg, "Goblin")
    assert ok
    assert "EN:" in msg
    store2 = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    g = store2.get("abc123")
    assert g is not None
    assert "goblin" in g.appearance_en.lower()
    assert g.appearance_ru
    assert g.status == "ready"


def test_girl_sockets_include_hands_and_cleavage():
    ids = list_girl_socket_ids()
    assert "socket_oral" in ids
    assert "socket_hand_l" in ids
    assert "socket_hand_r" in ids
    assert "socket_cleavage" in ids
    assert len(GIRL_SOCKETS) == 6


def test_suggest_size_goblin():
    assert "small" in suggest_size_from_name("Goblin_warrior")
    assert suggest_locomotion_from_name("green_slime") == "amorph"
    assert suggest_locomotion_from_name("mimic_chest") == "mimic"


def test_scan_and_set_size(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    inbox = creatures_inbox_dir(cfg)
    fbx = inbox / "Goblin_A.fbx"
    fbx.write_bytes(b"fbx")
    (inbox / "textures").mkdir()
    (inbox / "textures" / "a.png").write_bytes(b"x")

    added, total, msg = scan_creatures_inbox(cfg)
    assert added == 1
    assert total == 1
    assert "Goblin" in msg

    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    e = store.all()[0]
    assert e.textures_external
    assert e.status == "new"
    assert "small" in e.tags or "small" in e.notes

    updated = store.set_size(
        e.id, "small", size_alt=["humanoid"], locomotion="biped"
    )
    assert updated is not None
    assert updated.anim_bucket() == "small__biped"
    assert updated.size_alt == ["humanoid"]
    store.save()

    sock = ensure_girl_sockets_doc(cfg)
    assert sock.is_file()


def test_auto_apply_and_same_stem(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    inbox = creatures_inbox_dir(cfg)
    (inbox / "DireWolf.fbx").write_bytes(b"fbx")
    (inbox / "DireWolf.blend").write_bytes(b"blend")
    (inbox / "MysteryThing.fbx").write_bytes(b"x")
    scan_creatures_inbox(cfg)
    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    assert len(store.pending()) == 3

    n, lines = auto_apply_size_guesses(store)
    assert n >= 1
    assert any("DireWolf" in ln for ln in lines)
    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    wolves = [e for e in store.all() if "DireWolf" in e.name]
    # auto marks both if both pending with clear name — or first then sibling
    sized_wolves = [e for e in wolves if e.size_class]
    assert sized_wolves
    assert all(e.size_class == "quad_med" for e in sized_wolves)

    # mystery still pending
    mystery = next(e for e in store.all() if "Mystery" in e.name)
    assert mystery.status == "new"

    # sibling helper: mark remaining wolf file if any
    if len(sized_wolves) == 1 and len(wolves) == 2:
        extra = apply_size_to_same_stem(
            store, sized_wolves[0].id, "quad_med", locomotion="quadruped"
        )
        store.save()
        assert extra == 1


def test_lineup_job(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    inbox = creatures_inbox_dir(cfg)
    fbx = inbox / "Wolf.fbx"
    fbx.write_bytes(b"fbx")
    scan_creatures_inbox(cfg)
    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    e = store.all()[0]
    store.set_size(e.id, "quad_med", locomotion="quadruped")
    store.save()

    ok, msg, job = build_lineup_job(cfg, size_filter=["quad_med"])
    assert ok, msg
    assert job.is_file()
    script = job.parent / "viu_creature_lineup.py"
    assert script.is_file()
    assert "wrap_root" in script.read_text(encoding="utf-8")
    assert "import_scene.fbx" in script.read_text(encoding="utf-8")


def test_lineup_dedupe_and_auto_run(tmp_path, monkeypatch):
    from viu.creature_catalog.lineup import build_lineup_jobs, run_creature_lineup

    cfg = _cfg(tmp_path, monkeypatch)
    inbox = creatures_inbox_dir(cfg)
    (inbox / "Goblin.fbx").write_bytes(b"fbx")
    (inbox / "Goblin.blend").write_bytes(b"blend")
    (inbox / "Wolf.fbx").write_bytes(b"fbx")
    scan_creatures_inbox(cfg)
    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    for e in store.all():
        if "Goblin" in e.name:
            store.set_size(e.id, "small", locomotion="biped")
        else:
            store.set_size(e.id, "quad_med", locomotion="quadruped")
    store.save()

    ok, msg, jobs = build_lineup_jobs(cfg, split=False)
    assert ok, msg
    data = __import__("json").loads(jobs[0].read_text(encoding="utf-8"))
    # дедуп: Goblin.fbx+blend → один
    assert len(data["creatures"]) == 2
    names = {c["name"] for c in data["creatures"]}
    assert "Goblin" in names
    assert "Wolf" in names

    calls = []

    def fake_runner(cmd, capture_output=True, text=True, timeout=900.0):
        calls.append(cmd)
        job_path = Path(cmd[-1])
        job = __import__("json").loads(job_path.read_text(encoding="utf-8"))
        out = Path(job["output_blend"])
        out.write_bytes(b"BLENDER")
        stdout = "VIU_LINEUP_OK " + str(out) + "\n"
        for c in job["creatures"]:
            stdout += (
                'VIU_LINEUP_ROW {"id": "%s", "measured_m": 1.2, "scale": 0.5}\n'
                % c["id"]
            )
        from types import SimpleNamespace

        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(
        "viu.integrations.blender.exe.resolve_blender_exe",
        lambda config=None, override="": Path("/fake/blender"),
    )
    ok, msg = run_creature_lineup(
        cfg, split=False, open_result=False, runner=fake_runner
    )
    assert ok, msg
    assert calls
    store2 = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    assert any(e.measured_height_m > 0 for e in store2.all())


def test_set_size_custom_height(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    inbox = creatures_inbox_dir(cfg)
    (inbox / "Facehug.fbx").write_bytes(b"x")
    scan_creatures_inbox(cfg)
    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    e = store.all()[0]
    updated = store.set_size(e.id, "small", locomotion="biped", target_m=0.7)
    assert updated is not None
    assert updated.target_height_m == 0.7
    assert updated.size_class == "small"


def test_suggest_facehug_and_croc():
    assert "small" in suggest_size_from_name("Facehugger_v2")
    assert "large" in suggest_size_from_name("Renekton_Croc")
    assert "mini" in suggest_size_from_name("FAIRIE_bee")
    assert "humanoid" in suggest_size_from_name("Lilia_Centauress")
    assert "large" in suggest_size_from_name("Bareoth_Werewolf_1")


def test_tools_registered():
    names = build_default_registry().names()
    assert "creature_catalog_scan" in names
    assert "creature_catalog_set_size" in names
    assert "creature_catalog_auto_size" in names
    assert "creature_lineup" in names


def test_gui_action_creature_catalog():
    from viu.gui_actions import GUI_ACTIONS

    ids = {a.action_id for a in GUI_ACTIONS}
    assert "creature_catalog" in ids
    assert "creature_lineup" in ids
    action = next(a for a in GUI_ACTIONS if a.action_id == "creature_catalog")
    assert action.tool == "__creature_catalog__"
    assert action.group == "Главное"
    lineup = next(a for a in GUI_ACTIONS if a.action_id == "creature_lineup")
    assert lineup.tool == "creature_lineup"
