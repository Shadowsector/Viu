"""ReActor diagnostics."""

from pathlib import Path
from unittest.mock import MagicMock

from viu.config import Config
from viu.integrations.comfy.reactor_diag import reactor_errors_in_launch_log


def test_reactor_errors_in_launch_log(tmp_path):
    cfg = Config(root=tmp_path / "Viu", data_dir=tmp_path / ".viu")
    cfg.data_dir.mkdir(parents=True)
    log = cfg.data_dir / "logs" / "comfy_launch.log"
    log.parent.mkdir(parents=True)
    log.write_text(
        "Starting\n"
        "Traceback importing ComfyUI-ReActor\n"
        "ModuleNotFoundError: No module named 'insightface'\n",
        encoding="utf-8",
    )
    root = tmp_path / "ComfyUI"
    root.mkdir()
    (root / "main.py").write_text("#\n", encoding="utf-8")
    (root / "folder_paths.py").write_text("", encoding="utf-8")
    cfg.comfy_root = str(root)
    text = reactor_errors_in_launch_log(cfg)
    assert "insightface" in text.lower()


def test_list_reactor_node_classes():
    from unittest.mock import patch

    from viu.integrations.comfy.client import ComfyClient
    from viu.integrations.comfy.reactor_diag import list_reactor_node_classes

    client = ComfyClient("http://127.0.0.1:8188")
    with patch.object(
        client,
        "_get",
        return_value={"ReActorFaceSwap": {}, "KSampler": {}, "ReActorOptions": {}},
    ):
        found = list_reactor_node_classes(client)
    assert "ReActorFaceSwap" in found
