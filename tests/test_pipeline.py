"""Тесты pipeline context и видимости кнопок."""

from pathlib import Path

from viu.config import Config
from viu.pipeline import action_visible, get_pipeline_context


def _cfg(tmp_path: Path, *, inbox: Path | None = None) -> Config:
    inbox = inbox or (tmp_path / "Inbox")
    inbox.mkdir(parents=True, exist_ok=True)
    import os

    data = tmp_path / ".viu"
    os.environ["VIU_DATA_DIR"] = str(data)
    return Config(
        root=tmp_path,
        data_dir=data,
        inbox_dir=str(inbox),
    ).ensure_dirs()


def test_pipeline_stage_inbox(tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    (inbox / "barn.blend").write_bytes(b"x")
    ctx = get_pipeline_context(_cfg(tmp_path, inbox=inbox))
    assert ctx.stage == "inbox"
    assert ctx.inbox_needs_prepare
    assert "1/4" in ctx.step_label


def test_prepare_button_hidden_without_inbox(tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    ctx = get_pipeline_context(_cfg(tmp_path, inbox=inbox))
    assert not action_visible("prepare_unity_asset", ctx)


def test_overlay_tune_hidden_until_built(tmp_path):
    ctx = get_pipeline_context(_cfg(tmp_path))
    assert not action_visible("overlay_depth_far", ctx)
    assert not action_visible("overlay_depth_close", ctx)


def test_overlay_hidden_during_markup(tmp_path, monkeypatch):
    from viu.prop_catalog.models import PropEntry, prop_id_for_mesh
    from viu.prop_catalog.paths import catalog_path
    from viu.prop_catalog.store import PropCatalogStore

    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    lib = tmp_path / "Library"
    prepared = lib / "Processed" / "Barn" / "Barn_prepared.blend"
    prepared.parent.mkdir(parents=True)
    prepared.write_bytes(b"p")
    blend = lib / "Barn.blend"
    blend.write_bytes(b"b")

    import os

    os.environ["VIU_LIBRARY_ROOT"] = str(lib)
    try:
        cfg = Config(
            root=tmp_path,
            data_dir=tmp_path / ".viu",
            inbox_dir=str(inbox),
            library_root=str(lib),
        ).ensure_dirs()
        store = PropCatalogStore(catalog_path(cfg))
        store.upsert(
            PropEntry(
                id=prop_id_for_mesh(blend, "chair"),
                source_path=str(prepared),
                display_name="chair",
                mesh_name="chair",
                collection="Props",
                reviewed=False,
            )
        )
        store.save()
        ctx = get_pipeline_context(cfg)
        assert ctx.stage == "markup"
        assert not action_visible("unity_overlay", ctx)
        assert not action_visible("overlay_depth_far", ctx)
    finally:
        os.environ.pop("VIU_LIBRARY_ROOT", None)
