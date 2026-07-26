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


def test_outfit_sets_upsert():
    from viu.creature_catalog.outfit_sets import empty_outfit_doc, upsert_outfit_set

    data = empty_outfit_doc("shanya", "Shanya")
    snap = {
        "show_meshes": ["Body", "Pants"],
        "hide_meshes": ["Bikini"],
        "genital_mesh_visible": False,
        "clothing_visible": True,
    }
    upsert_outfit_set(data, set_id="casual_01", label="Casual", snapshot=snap, confirmed=True)
    assert len(data["sets"]) == 1
    assert data["sets"][0]["hide_genital_mesh"] is True


def test_texture_manifest_paths(tmp_path, monkeypatch):
    from viu.creature_catalog.paths import (
        creature_outfit_sets_path,
        creature_texture_manifest_path,
    )

    cfg = _cfg(tmp_path, monkeypatch)
    m = creature_texture_manifest_path(cfg, "wolf", stage="prepared")
    assert m.parent.name == "wolf"
    assert m.name == "texture_manifest.json"
    o = creature_outfit_sets_path(cfg, "wolf")
    assert o.name == "outfit_sets.json"


def test_anatomy_markup_and_anim_bucket(tmp_path, monkeypatch):
    from viu.creature_catalog.models import CreatureEntry, STATUS_SIZED

    e = CreatureEntry(
        id="x",
        path=str(tmp_path / "goblin.fbx"),
        name="goblin",
        size_class="small",
        locomotion="biped",
        status=STATUS_SIZED,
    )
    e.set_anatomy(genital_profile="penis")
    assert e.nsfw_capable
    assert e.anim_bucket() == "small__biped__penis"
    e.set_anatomy(genital_profile="none", contact_modes=["oral", "tentacle"])
    assert e.anim_bucket() == "small__biped__oral+tentacle"
    assert "рот" in e.anatomy_summary()


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


def test_resolve_shanya_path_env(tmp_path, monkeypatch):
    from viu.creature_catalog.lineup import resolve_shanya_path

    cfg = _cfg(tmp_path, monkeypatch)
    shanya = tmp_path / "Library" / "Lab" / "Models" / "CascadeurReady" / "Shanya.fbx"
    shanya.parent.mkdir(parents=True, exist_ok=True)
    shanya.write_bytes(b"fbx")
    override = tmp_path / "custom" / "Shanya_ref.fbx"
    override.parent.mkdir()
    override.write_bytes(b"fbx")
    monkeypatch.setenv("VIU_SHANYA_FBX", str(override))
    assert resolve_shanya_path(cfg) == override
    monkeypatch.delenv("VIU_SHANYA_FBX", raising=False)
    assert resolve_shanya_path(cfg) == shanya


def test_resolve_shanya_studio_prefers_fbx(tmp_path, monkeypatch):
    from viu.creature_catalog.studio import resolve_shanya_studio_path

    cfg = _cfg(tmp_path, monkeypatch)
    d = tmp_path / "Library" / "Lab" / "Models" / "CascadeurReady"
    d.mkdir(parents=True, exist_ok=True)
    blend = d / "Shanya_rig.blend"
    fbx = d / "Shanya.fbx"
    blend.write_bytes(b"blend")
    fbx.write_bytes(b"fbx")
    monkeypatch.setenv("VIU_SHANYA_FBX", str(blend))
    assert resolve_shanya_studio_path(cfg) == fbx


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
    data = __import__("json").loads(job.read_text(encoding="utf-8"))
    assert data.get("processed_root")
    assert data["creatures"][0].get("slug")
    script = job.parent / "viu_creature_lineup.py"
    assert script.is_file()
    body = script.read_text(encoding="utf-8")
    assert "wrap_root" in body
    assert "import_scene.fbx" in body
    assert "VIU_LINEUP_PHOTO" in body
    assert "render_creature_shots" in body
    assert "_hide_rig_helpers" in body


def test_lineup_parse_photos_and_apply(tmp_path, monkeypatch):
    from viu.creature_catalog.lineup import _apply_photos, _parse_photos
    from viu.creature_catalog.models import CreatureEntry, STATUS_SIZED

    stdout = (
        'VIU_LINEUP_PHOTO {"id": "abc", "slug": "goblin", '
        '"front": "/tmp/goblin/front.png", "side": "/tmp/goblin/side.png"}\n'
        "VIU_LINEUP_PHOTOS_DONE 1\n"
        "VIU_LINEUP_PHOTO_FAIL goblin2 boom\n"
    )
    rows = _parse_photos(stdout)
    assert len(rows) == 1
    assert rows[0]["slug"] == "goblin"

    cfg = _cfg(tmp_path, monkeypatch)
    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    store.upsert(
        CreatureEntry(
            id="abc",
            path=str(tmp_path / "Goblin.fbx"),
            name="Goblin",
            slug="goblin",
            size_class="small",
            status=STATUS_SIZED,
        )
    )
    store.save()
    n = _apply_photos(cfg, rows)
    assert n == 1
    g = CreatureCatalogStore(creature_catalog_path(cfg)).load().get("abc")
    assert g is not None
    assert g.photo_front.endswith("front.png")
    assert g.photo_side.endswith("side.png")


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
            slug = c.get("slug") or "creature"
            front = str(tmp_path / "Library" / "Lab" / "Creatures" / "Processed" / slug / "front.png")
            side = str(tmp_path / "Library" / "Lab" / "Creatures" / "Processed" / slug / "side.png")
            stdout += (
                'VIU_LINEUP_ROW {"id": "%s", "measured_m": 1.2, "scale": 0.5}\n'
                % c["id"]
            )
            stdout += (
                'VIU_LINEUP_PHOTO {"id": "%s", "slug": "%s", "front": "%s", "side": "%s"}\n'
                % (c["id"], slug, front, side)
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
    assert any(e.photo_front for e in store2.all())


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


def test_creature_studio_session_and_sync(tmp_path, monkeypatch):
    from viu.creature_catalog.models import CreatureEntry, STATUS_SIZED
    from viu.creature_catalog.paths import creature_prepared_blend_path
    from viu.creature_catalog.studio import (
        build_studio_queue,
        sync_studio_feedback,
        write_studio_session,
    )

    cfg = _cfg(tmp_path, monkeypatch)
    prep = creature_prepared_blend_path(cfg, "wolf_alpha")
    prep.parent.mkdir(parents=True, exist_ok=True)
    prep.write_bytes(b"prep")
    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    store.upsert(
        CreatureEntry(
            id="w1",
            path=str(tmp_path / "wolf.blend"),
            name="wolf_alpha",
            slug="wolf_alpha",
            size_class="quad_med",
            locomotion="quadruped",
            status=STATUS_SIZED,
            prep_ok=True,
            prepared_path=str(prep),
        )
    )
    store.save()

    ok, msg, queue = build_studio_queue(cfg, slug_filter=["wolf_alpha"])
    assert ok and len(queue) == 1
    session = write_studio_session(cfg, queue)
    assert session.is_file()
    data = __import__("json").loads(session.read_text(encoding="utf-8"))
    assert data["queue"][0]["slug"] == "wolf_alpha"
    assert data["queue"][0]["path"] == str(prep)
    assert (session.parent / "viu_creature_studio.py").is_file()
    assert (session.parent / "viu_creature_blender_shared.py").is_file()

    fb = session.parent / "studio_feedback.json"
    fb.write_text(
        __import__("json").dumps(
            {
                "entries": [
                    {
                        "id": "w1",
                        "slug": "wolf_alpha",
                        "photo_front": str(tmp_path / "front.png"),
                        "photo_three_quarter": str(tmp_path / "three_quarter.png"),
                        "photo_side": str(tmp_path / "side.png"),
                        "photo_ok": True,
                        "target_height_m": 0.96,
                        "size_class": "quad_med",
                        "locomotion": "quadruped",
                        "ready_fbx_path": str(tmp_path / "wolf_alpha_ready.fbx"),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    n, sync_msg = sync_studio_feedback(cfg)
    assert n == 1
    w = CreatureCatalogStore(creature_catalog_path(cfg)).load().get("w1")
    assert w is not None
    assert w.photo_ok
    assert w.photo_three_quarter.endswith("three_quarter.png")
    assert w.target_height_m == 0.96
    assert w.ready_fbx_path.endswith("wolf_alpha_ready.fbx")


def test_creature_prep_session_and_sync(tmp_path, monkeypatch):
    from viu.creature_catalog.models import CreatureEntry
    from viu.creature_catalog.paths import creature_prepared_blend_path
    from viu.creature_catalog.prep import (
        build_prep_queue,
        sync_prep_feedback,
        write_prep_session,
    )

    cfg = _cfg(tmp_path, monkeypatch)
    inbox = tmp_path / "wolf.blend"
    inbox.write_bytes(b"inbox")
    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    store.upsert(
        CreatureEntry(
            id="w1",
            path=str(inbox),
            name="wolf_alpha",
            slug="wolf_alpha",
        )
    )
    store.save()

    ok, msg, queue = build_prep_queue(cfg, slug_filter=["wolf_alpha"])
    assert ok and len(queue) == 1
    session = write_prep_session(cfg, queue)
    assert (session.parent / "viu_creature_prep.py").is_file()

    prep_out = creature_prepared_blend_path(cfg, "wolf_alpha", ensure_dir=True)
    prep_out.parent.mkdir(parents=True, exist_ok=True)
    prep_out.write_bytes(b"prepared")
    fb = session.parent / "prep_feedback.json"
    fb.write_text(
        __import__("json").dumps(
            {
                "entries": [
                    {
                        "id": "w1",
                        "prepared_path": str(prep_out),
                        "prep_ok": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    n, _ = sync_prep_feedback(cfg)
    assert n == 1
    w = CreatureCatalogStore(creature_catalog_path(cfg)).load().get("w1")
    assert w is not None
    assert w.prep_ok
    assert w.prepared_path == str(prep_out)


def test_studio_queue_requires_prepared(tmp_path, monkeypatch):
    from viu.creature_catalog.models import CreatureEntry
    from viu.creature_catalog.studio import build_studio_queue

    cfg = _cfg(tmp_path, monkeypatch)
    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    store.upsert(
        CreatureEntry(
            id="w1",
            path=str(tmp_path / "wolf.blend"),
            name="wolf_alpha",
            slug="wolf_alpha",
        )
    )
    store.save()
    (tmp_path / "wolf.blend").write_bytes(b"x")
    ok, msg, queue = build_studio_queue(cfg)
    assert not ok
    assert "подготов" in msg.lower()


def test_unified_living_inbox(tmp_path, monkeypatch):
    from viu.creature_catalog.paths import creatures_inbox_dir
    from viu.lab.paths import models_inbox_dir

    cfg = _cfg(tmp_path, monkeypatch)
    assert models_inbox_dir(cfg) == creatures_inbox_dir(cfg)


def test_creature_studio_tool_imports():
    from viu.tools.creature_catalog_tool import (
        CreaturePrepOpenTool,
        CreaturePrepSyncTool,
        CreatureWardrobeOpenTool,
        CreatureWardrobeSyncTool,
        CreatureStudioOpenTool,
        CreatureStudioSyncTool,
    )

    assert CreaturePrepOpenTool().name == "creature_prep_open"
    assert CreaturePrepSyncTool().name == "creature_prep_sync"
    assert CreatureWardrobeOpenTool().name == "creature_wardrobe_open"
    assert CreatureWardrobeSyncTool().name == "creature_wardrobe_sync"
    assert CreatureStudioOpenTool().name == "creature_studio_open"
    assert CreatureStudioSyncTool().name == "creature_studio_sync"


def test_tools_registered():
    names = build_default_registry().names()
    assert "creature_catalog_scan" in names
    assert "creature_catalog_set_size" in names
    assert "creature_catalog_auto_size" in names
    assert "creature_lineup" in names
    assert "creature_prep_open" in names
    assert "creature_prep_sync" in names
    assert "creature_wardrobe_open" in names
    assert "creature_wardrobe_sync" in names
    assert "creature_studio_open" in names
    assert "creature_studio_sync" in names


def test_lineup_slug_and_need_photos_filter(tmp_path, monkeypatch):
    from viu.creature_catalog.lineup import build_lineup_jobs
    from viu.creature_catalog.models import CreatureEntry, STATUS_SIZED

    cfg = _cfg(tmp_path, monkeypatch)
    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    store.upsert(
        CreatureEntry(
            id="w1",
            path=str(tmp_path / "wolf.blend"),
            name="wolf_alpha",
            slug="wolf_alpha",
            size_class="quad_med",
            locomotion="quadruped",
            status=STATUS_SIZED,
            photo_front=str(tmp_path / "wolf_front.png"),
            photo_side=str(tmp_path / "wolf_side.png"),
            photo_ok=True,
        )
    )
    store.upsert(
        CreatureEntry(
            id="g1",
            path=str(tmp_path / "goblin.fbx"),
            name="Goblin",
            slug="goblin",
            size_class="small",
            locomotion="biped",
            status=STATUS_SIZED,
        )
    )
    store.save()
    (tmp_path / "wolf_front.png").write_bytes(b"x")
    (tmp_path / "wolf_side.png").write_bytes(b"x")

    ok, _msg, jobs = build_lineup_jobs(cfg, slug_filter=["wolf_alpha"], need_photos_only=False)
    assert ok and jobs
    data = __import__("json").loads(jobs[0].read_text(encoding="utf-8"))
    assert len(data["creatures"]) == 1
    assert data["creatures"][0]["slug"] == "wolf_alpha"

    ok2, msg2, jobs2 = build_lineup_jobs(cfg, need_photos_only=True)
    assert ok2 and jobs2
    data2 = __import__("json").loads(jobs2[0].read_text(encoding="utf-8"))
    assert len(data2["creatures"]) == 1
    assert data2["creatures"][0]["slug"] == "goblin"

    store2 = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    g = store2.get("g1")
    assert g is not None
    (tmp_path / "g_front.png").write_bytes(b"x")
    g.photo_front = str(tmp_path / "g_front.png")
    store2.upsert(g)
    store2.save()
    ok3, msg3, _ = build_lineup_jobs(cfg, need_photos_only=True)
    assert not ok3
    assert "без скринов" in msg3


def test_photo_ok_model(tmp_path, monkeypatch):
    from viu.creature_catalog.models import CreatureEntry, STATUS_SIZED

    e = CreatureEntry(
        id="x",
        path=str(tmp_path / "a.fbx"),
        name="Wolf",
        size_class="quad_med",
        status=STATUS_SIZED,
    )
    assert e.needs_photo_lineup()
    assert not e.needs_photo_review()
    (tmp_path / "front.png").write_bytes(b"x")
    e.photo_front = str(tmp_path / "front.png")
    assert not e.needs_photo_lineup()
    assert e.needs_photo_review()
    e.photo_ok = True
    assert not e.needs_photo_review()


def test_gui_action_creature_catalog():
    from viu.gui_actions import GUI_ACTIONS

    ids = {a.action_id for a in GUI_ACTIONS}
    assert "creature_catalog" in ids
    assert "creature_lineup" in ids
    action = next(a for a in GUI_ACTIONS if a.action_id == "creature_catalog")
    assert action.tool == "__creature_catalog__"
    assert action.group == "Blender — существа"
    assert any(a.action_id == "creature_prep" and a.tool == "creature_prep_open" for a in GUI_ACTIONS)
    assert any(a.action_id == "creature_blender_sync" and a.is_chain for a in GUI_ACTIONS)
    assert any(a.action_id == "creature_wardrobe" and a.tool == "creature_wardrobe_open" for a in GUI_ACTIONS)
    assert any(a.action_id == "creature_studio" and a.tool == "creature_studio_open" for a in GUI_ACTIONS)
    sync_chain = next(a for a in GUI_ACTIONS if a.action_id == "creature_blender_sync")
    sync_tools = [t[0] for t in sync_chain.tool_chain]
    assert "creature_prep_sync" in sync_tools
    assert "creature_wardrobe_sync" in sync_tools
    assert "creature_studio_sync" in sync_tools
    lineup = next(a for a in GUI_ACTIONS if a.action_id == "creature_lineup")
    assert lineup.group == "Blender — существа"


def test_outfit_types_ids():
    from viu.creature_catalog.outfit_types import (
        outfit_set_id,
        outfit_type_label,
        parse_outfit_set_id,
    )

    assert outfit_set_id("casual", "02") == "casual_02"
    assert outfit_set_id("swimsuit", "2") == "swimsuit_02"
    assert outfit_type_label("half_nude") == "Half-nude"
    assert parse_outfit_set_id("lingerie_03") == ("lingerie", "03")


def test_creature_identity_from_subfolder(tmp_path):
    from viu.creature_catalog.models import creature_identity_from_inbox_path

    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    blend = inbox / "Erisa" / "Erisa.blend"
    blend.parent.mkdir(parents=True)
    blend.write_bytes(b"x")
    name, slug = creature_identity_from_inbox_path(blend, inbox)
    assert name == "Erisa"
    assert slug == "erisa"

    rig = inbox / "Girls" / "Erisa" / "rig.blend"
    rig.parent.mkdir(parents=True, exist_ok=True)
    rig.write_bytes(b"x")
    name2, slug2 = creature_identity_from_inbox_path(rig, inbox)
    assert name2 == "Girls/Erisa/rig"
    assert slug2 == "girls_erisa_rig"


def test_append_pipeline_note_dedupes():
    from viu.creature_catalog.note_utils import append_pipeline_note

    n = append_pipeline_note("", "prep", "нет текстур")
    n2 = append_pipeline_note(n, "prep", "нет текстур")
    assert n == n2
    assert n.count("нет текстур") == 1


def test_merge_duplicate_slugs(tmp_path, monkeypatch):
    from viu.creature_catalog.models import CreatureEntry
    from viu.creature_catalog.store import CreatureCatalogStore

    cfg = _cfg(tmp_path, monkeypatch)
    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    store.upsert(
        CreatureEntry(id="a", path=str(tmp_path / "a.fbx"), name="Dennis", slug="dennis")
    )
    store.upsert(
        CreatureEntry(
            id="b",
            path=str(tmp_path / "b.blend"),
            name="Dennis",
            slug="dennis",
            prep_ok=True,
            notes="[wardrobe] test",
        )
    )
    removed, _ = store.merge_duplicate_slugs()
    assert removed == 1
    assert len(store.all()) == 1
    assert store.all()[0].prep_ok


def test_dedupe_by_slug_merges_same_creature(tmp_path):
    from viu.creature_catalog.lineup import dedupe_by_slug
    from viu.creature_catalog.models import CreatureEntry

    a = CreatureEntry(
        id="a",
        path=str(tmp_path / "tiki.fbx"),
        name="Tiki",
        slug="tiki",
        prep_ok=False,
    )
    b = CreatureEntry(
        id="b",
        path=str(tmp_path / "Tiki" / "Tiki.blend"),
        name="Tiki",
        slug="tiki",
        prep_ok=True,
        prepared_path=str(tmp_path / "prepared" / "tiki_prepared.blend"),
    )
    out = dedupe_by_slug([a, b])
    assert len(out) == 1
    assert out[0].id == "b"


def test_dedupe_by_inbox_folder_keeps_subfolders(tmp_path):
    from viu.creature_catalog.lineup import dedupe_by_inbox_folder
    from viu.creature_catalog.models import CreatureEntry

    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    a = CreatureEntry(id="a", path=str(inbox / "GirlA" / "model.blend"), name="GirlA", slug="girla")
    b = CreatureEntry(id="b", path=str(inbox / "GirlB" / "model.blend"), name="GirlB", slug="girlb")
    out = dedupe_by_inbox_folder([a, b], inbox)
    assert len(out) == 2


def test_prep_queue_scans_subfolders_and_no_empty_prepared_dir(tmp_path, monkeypatch):
    from viu.creature_catalog.paths import creature_prepared_blend_path, creatures_prepared_dir
    from viu.creature_catalog.prep import build_prep_queue, needs_prep_entry

    cfg = _cfg(tmp_path, monkeypatch)
    inbox = cfg.library_root
    from viu.creature_catalog.paths import creatures_inbox_dir

    root = creatures_inbox_dir(cfg)
    (root / "Tiki").mkdir(parents=True)
    (root / "Tiki" / "Tiki.blend").write_bytes(b"blend")
    (root / "Renekton").mkdir(parents=True)
    (root / "Renekton" / "Renekton.fbx").write_bytes(b"fbx")

    ok, msg, queue = build_prep_queue(cfg)
    assert ok
    assert len(queue) == 2
    assert "Скан Inbox" in msg

    needs_prep_entry(queue[0], cfg)
    prepared_root = creatures_prepared_dir(cfg)
    assert not any(prepared_root.iterdir()), "needs_prep не должен создавать пустые папки Prepared"

    path = creature_prepared_blend_path(cfg, queue[0].slug)
    assert not path.parent.is_dir()
    path = creature_prepared_blend_path(cfg, queue[0].slug, ensure_dir=True)
    assert path.parent.is_dir()


def _extract_shared_fns(*names: str):
    import ast
    from pathlib import Path

    src = Path("viu/creature_catalog/_creature_blender_shared.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    wanted = {n: None for n in names}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            wanted[node.name] = node
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in wanted:
                    wanted[t.id] = node
    body = [wanted[n] for n in names if wanted[n] is not None]
    assert len(body) == len(names), {k: v is not None for k, v in wanted.items()}
    ns: dict = {"re": __import__("re"), "List": list, "Optional": type(None)}
    # typing List used in annotations — provide simple substitutes
    import typing

    ns["List"] = typing.List
    ns["Optional"] = typing.Optional
    exec(compile(ast.Module(body=body, type_ignores=[]), "<shared_extract>", "exec"), ns)
    return ns


def test_height_fit_multiplier_fbx_scale_and_cm():
    """Studio height fit: scale-10 visual (~17m) and cm exports (~170)."""
    ns = _extract_shared_fns("height_fit_multiplier")
    height_fit_multiplier = ns["height_fit_multiplier"]

    assert abs(height_fit_multiplier(17.0, 1.7) - 0.1) < 1e-9
    assert abs(height_fit_multiplier(170.0, 1.7) - 0.01) < 1e-9
    assert abs(height_fit_multiplier(1.7, 1.7) - 1.0) < 1e-9
    assert height_fit_multiplier(0.0, 1.7) == 1.0


def test_rig_helper_tokens_do_not_false_positive_body_names():
    ns = _extract_shared_fns(
        "_RIG_HIDE_TOKENS",
        "_name_tokens",
        "is_wgt_name",
        "is_control_shape_name",
        "is_gzm_name",
        "is_rig_helper_mesh_name",
        "mesh_vertex_count",
        "skip_mesh",
    )
    is_helper = ns["is_rig_helper_mesh_name"]
    skip_mesh = ns["skip_mesh"]
    assert is_helper("WGT-Hand") is True
    assert is_helper("cs_foot") is True
    assert is_helper("IK_Foot") is True
    assert is_helper("Body_Shadow") is True
    # Раньше substring «ik»/«target» прятал такие меши → Ahmed/Blue Devil «пустые».
    assert is_helper("Spike") is False
    assert is_helper("LikeBody") is False
    assert is_helper("retarget_mesh") is False
    assert is_helper("BlueDevil_Body") is False
    assert is_helper("Ahmed_Skin") is False
    # Крупный меш с токеном Shadow не skip — иначе Ahmed пустой в студии.
    class _Mesh:
        type = "MESH"

        class data:
            vertices = [0] * 800

    assert skip_mesh("Body_Shadow", _Mesh()) is False
    assert skip_mesh("WGT-Hand", _Mesh()) is True
