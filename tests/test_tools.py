import pytest

from viu.config import Config
from viu.memory import MemoryStore
from viu.planning import Planner
from viu.tools import AgentContext, build_default_registry
from viu.tools.filesystem import ListDirTool, ReadFileTool, WriteFileTool
from viu.tools.shell import ShellTool


@pytest.fixture
def ctx(tmp_path):
    config = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    registry = build_default_registry()
    memory = MemoryStore(config.data_dir / "memory.json")
    planner = Planner(config.data_dir / "plan.json")
    return AgentContext(config=config, memory=memory, planner=planner, registry=registry)


def test_write_read_list_file(ctx):
    w = WriteFileTool().run({"path": "sub/hello.txt", "content": "привет"}, ctx)
    assert w.ok

    r = ReadFileTool().run({"path": "sub/hello.txt"}, ctx)
    assert r.ok and r.content == "привет"

    ls = ListDirTool().run({"path": "sub"}, ctx)
    assert ls.ok and "hello.txt" in ls.content


def test_file_sandbox_escape_blocked(ctx):
    r = WriteFileTool().run({"path": "../escape.txt", "content": "x"}, ctx)
    assert not r.ok
    assert "песочниц" in r.content.lower()


def test_shell_tool_runs(ctx):
    r = ShellTool().run({"command": "echo hi"}, ctx)
    assert r.ok
    assert "hi" in r.content


def test_shell_disabled(tmp_path):
    config = Config(root=tmp_path, data_dir=tmp_path / ".viu", allow_shell=False).ensure_dirs()
    registry = build_default_registry()
    ctx = AgentContext(
        config=config,
        memory=MemoryStore(config.data_dir / "memory.json"),
        planner=Planner(config.data_dir / "plan.json"),
        registry=registry,
    )
    r = ShellTool().run({"command": "echo hi"}, ctx)
    assert not r.ok


def test_registry_has_core_tools():
    reg = build_default_registry()
    for name in (
        "read_file",
        "write_file",
        "run_shell",
        "web_search",
        "memory_write",
        "plan_create",
        "self_inspect",
        "add_tool",
        "improve_prompt",
    ):
        assert reg.get(name) is not None, name
