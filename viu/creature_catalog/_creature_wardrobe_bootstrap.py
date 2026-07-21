"""Bootstrap: Viu Creature Wardrobe."""
import importlib.util
import sys
from pathlib import Path


def main():
    argv = sys.argv
    if "--" not in argv:
        print("VIU_WARDROBE_FAIL no session")
        return
    session_path = Path(argv[argv.index("--") + 1])
    addon_path = session_path.parent / "viu_creature_wardrobe.py"
    if not addon_path.is_file():
        print("VIU_WARDROBE_FAIL addon missing")
        return
    spec = importlib.util.spec_from_file_location("viu_creature_wardrobe", str(addon_path))
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    sys.modules["viu_creature_wardrobe"] = mod
    spec.loader.exec_module(mod)
    mod.register()
    mod.load_session(str(session_path))
    print("VIU_WARDROBE_OK", session_path)


if __name__ == "__main__":
    main()
