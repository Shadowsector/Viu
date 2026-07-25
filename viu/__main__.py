"""CLI-интерфейс Вью.

Команды:
  run "<задача>"   — выполнить задачу (провайдер из VIU_PROVIDER)
  demo             — офлайн-демонстрация всего цикла (mock, без API/сети)
  tools            — показать доступные инструменты
  memory           — показать долгосрочную память
  plan             — показать текущий план
  config           — показать текущую конфигурацию
"""

from __future__ import annotations

import argparse
import json
import sys

from .agent import Agent, Step
from .config import Config
from .demo import demo_script
from .llm import MockLLM
from .memory import MemoryStore
from .planning import Planner
from .tools import build_default_registry


def _print_step(step: Step) -> None:
    if step.kind == "action":
        print(f"  · [{step.tool}] {step.thought}")
        for line in step.observation.splitlines():
            print(f"      {line}")
    elif step.kind == "final":
        print(f"  ✓ {step.thought}")
    elif step.kind == "error":
        print(f"  ! {step.observation}")


def cmd_run(args: argparse.Namespace) -> int:
    agent = Agent(config=Config())
    print(f"Провайдер: {agent.llm.name}\nЗадача: {args.task}\n")
    result = agent.run(args.task, on_step=_print_step)
    print("\n=== Итог ===")
    print(result.final)
    return 0 if result.completed else 1


def cmd_demo(args: argparse.Namespace) -> int:
    config = Config(provider="mock")
    agent = Agent(config=config, llm=MockLLM(responses=demo_script()))
    task = "Заложи основу разработки 3D-игры «Анабарра»."
    print(f"Провайдер: {agent.llm.name} (офлайн-демо)\nЗадача: {task}\n")
    result = agent.run(task, on_step=_print_step)
    print("\n=== Итог ===")
    print(result.final)
    print(f"\nШагов выполнено: {len(result.steps)}")
    return 0 if result.completed else 1


def cmd_chat(args: argparse.Namespace) -> int:
    """Интерактивное общение с Вью (для двойного клика по .bat)."""
    agent = Agent(config=Config())
    print("=" * 56)
    print("  Вью — помощник и соавтор Анабарры")
    print(f"  Модель: {agent.llm.name}")
    print("  Пиши задачу и жми Enter. Выход: exit / выход / Ctrl+C")
    print("=" * 56)
    while True:
        try:
            task = input("\nты> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nПока!")
            return 0
        if not task:
            continue
        if task.lower() in ("exit", "quit", "выход", "пока"):
            print("Пока!")
            return 0
        try:
            result = agent.run(task, on_step=_print_step)
            print(f"\nВью> {result.final}")
        except Exception as exc:  # noqa: BLE001 — чат не должен падать из-за одной ошибки
            print(f"\n[ошибка] {exc}")
            print("Подсказка: запущена ли Ollama? Верна ли модель в start_viu.bat?")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    """Запуск графического окна Вью."""
    try:
        from .gui import main as gui_main
    except ImportError as exc:
        print(f"Не удалось загрузить графический интерфейс (tkinter): {exc}")
        print("Запустите консольный режим: python -m viu chat")
        return 1
    return gui_main()


def cmd_tool(args: argparse.Namespace) -> int:
    """Прямой вызов одного инструмента без участия модели (надёжно для тестов)."""
    agent = Agent(config=Config())
    tool = agent.registry.get(args.name)
    if tool is None:
        print(f"Инструмент {args.name!r} не найден. Доступные:")
        print(", ".join(agent.registry.names()))
        return 1
    try:
        params = json.loads(args.args) if args.args else {}
    except json.JSONDecodeError as exc:
        print(f"Неверный JSON в --args: {exc}")
        return 1
    result = tool.run(params, agent.ctx)
    print(result.render(), flush=True)
    return 0 if result.ok else 1


def cmd_tools(args: argparse.Namespace) -> int:
    registry = build_default_registry()
    print(registry.spec())
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    config = Config().ensure_dirs()
    store = MemoryStore(config.data_dir / "memory.json")
    records = store.all()
    if not records:
        print("(память пуста)")
        return 0
    for r in records:
        tags = f" [{', '.join(r.tags)}]" if r.tags else ""
        print(f"- {r.text}{tags}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    config = Config().ensure_dirs()
    planner = Planner(config.data_dir / "plan.json")
    print(planner.plan.render())
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """Обновление Viu: git pull или zip с GitHub."""
    from .updater import apply_update_smart, check_for_update, install_package, update_viu_full, usable_git_root

    config = Config()
    branch = config.update_branch
    if getattr(args, "full", False):
        ok, text, _restart = update_viu_full(branch=branch, full_sync=True)
        print(text)
        return 0 if ok else 1
    if getattr(args, "apply", False):
        force = getattr(args, "force", False)
        result = apply_update_smart(branch=branch, hard_reset=force, force=force)
        if result.updated:
            ok, pip_msg = install_package()
            print(result.message)
            print(pip_msg if ok else f"WARN: {pip_msg}")
        else:
            print(result.message)
        return 0 if result.ok else 1
    result = check_for_update(branch=branch)
    print(result.message)
    if result.behind:
        print(f"Коммитов позади: {result.behind}")
    if not usable_git_root() and result.has_updates:
        print("Применить: python -m viu update --apply")
    return 0 if result.ok else 1


def cmd_config(args: argparse.Namespace) -> int:
    print(Config().summary())
    return 0


def cmd_machine(args: argparse.Namespace) -> int:
    """Личная привязка к машине (не материнка/GPU)."""
    from .machine_bind import ensure_bind, rebind, status_text, verify_bind

    config = Config()
    action = (args.action or "status").strip().lower()
    if action in ("status", "show"):
        print(status_text(config))
        ok, _, bind = verify_bind(config)
        if bind is None:
            return 0
        return 0 if ok else 2
    if action == "ensure":
        bind, created = ensure_bind(config)
        print(("создана" if created else "уже есть") + f": {bind.install_id}")
        print(status_text(config))
        return 0
    if action == "rebind":
        bind, msg = rebind(config, reason=args.reason or "cli_rebind")
        print(msg)
        print(f"install_id={bind.install_id}")
        print(status_text(config))
        return 0
    print("usage: viu machine status|ensure|rebind [--reason …]")
    return 1


def bind_path_exists(config: Config) -> bool:
    from .machine_bind import bind_path

    return bind_path(config).is_file()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="viu", description="Вью — автономный агент-соавтор")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="выполнить задачу")
    p_run.add_argument("task", help="описание задачи")
    p_run.set_defaults(func=cmd_run)

    sub.add_parser("chat", help="интерактивное общение с Вью (консоль)").set_defaults(func=cmd_chat)
    sub.add_parser("gui", help="графическое окно Вью").set_defaults(func=cmd_gui)

    p_tool = sub.add_parser("tool", help="вызвать один инструмент напрямую")
    p_tool.add_argument("name", help="имя инструмента (см. viu tools)")
    p_tool.add_argument("--args", help="параметры инструмента в виде JSON", default="")
    p_tool.set_defaults(func=cmd_tool)

    sub.add_parser("demo", help="офлайн-демонстрация цикла").set_defaults(func=cmd_demo)
    sub.add_parser("tools", help="список инструментов").set_defaults(func=cmd_tools)
    sub.add_parser("memory", help="показать память").set_defaults(func=cmd_memory)
    sub.add_parser("plan", help="показать план").set_defaults(func=cmd_plan)
    p_up = sub.add_parser("update", help="проверить/скачать обновление Viu")
    p_up.add_argument("--apply", action="store_true", help="скачать и применить (git или zip)")
    p_up.add_argument("--force", action="store_true", help="игнорировать «уже актуально», hard reset / zip")
    p_up.add_argument(
        "--full",
        action="store_true",
        help="как кнопка «Обновить Вью»: bootstrap zip + git/zip + pip + сверка SHA",
    )
    p_up.set_defaults(func=cmd_update)
    sub.add_parser("config", help="показать конфигурацию").set_defaults(func=cmd_config)
    p_mach = sub.add_parser(
        "machine",
        help="личная привязка к компу (user+host+U:, не материнка/GPU)",
    )
    p_mach.add_argument(
        "action",
        nargs="?",
        default="status",
        help="status | ensure | rebind",
    )
    p_mach.add_argument("--reason", default="", help="для rebind — комментарий")
    p_mach.set_defaults(func=cmd_machine)
    return parser


def _force_utf8_io() -> None:
    """Вывод всегда в UTF-8 — иначе на Windows (cp1251) падает на кириллице/значках."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_io()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
