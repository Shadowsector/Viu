"""Bootstrap: Viu Creature Prep — подготовка моделей."""
import importlib.util
import sys
from pathlib import Path


def main():
    argv = sys.argv
    if "--" not in argv:
        print("VIU_PREP_FAIL no session path")
        return
    session_path = Path(argv[argv.index("--") + 1])
    prep_dir = session_path.parent
    addon_path = prep_dir / "viu_creature_prep.py"
    if not addon_path.is_file():
        print("VIU_PREP_FAIL addon missing", addon_path)
        return

    spec = importlib.util.spec_from_file_location("viu_creature_prep", str(addon_path))
    if spec is None or spec.loader is None:
        print("VIU_PREP_FAIL spec")
        return
    mod = importlib.util.module_from_spec(spec)
    sys.modules["viu_creature_prep"] = mod
    spec.loader.exec_module(mod)
    mod.register()
    mod.load_session(str(session_path))
    print("VIU_PREP_OK", session_path)


if __name__ == "__main__":
    main()
