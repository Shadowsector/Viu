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


def cmd_config(args: argparse.Namespace) -> int:
    print(Config().summary())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="viu", description="Вью — автономный агент-соавтор")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="выполнить задачу")
    p_run.add_argument("task", help="описание задачи")
    p_run.set_defaults(func=cmd_run)

    sub.add_parser("demo", help="офлайн-демонстрация цикла").set_defaults(func=cmd_demo)
    sub.add_parser("tools", help="список инструментов").set_defaults(func=cmd_tools)
    sub.add_parser("memory", help="показать память").set_defaults(func=cmd_memory)
    sub.add_parser("plan", help="показать план").set_defaults(func=cmd_plan)
    sub.add_parser("config", help="показать конфигурацию").set_defaults(func=cmd_config)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
