"""Bootstrap: регистрирует аддон студии и загружает session JSON."""
import importlib.util
import sys
from pathlib import Path


def main():
    argv = sys.argv
    if "--" not in argv:
        print("VIU_STUDIO_FAIL no session path")
        return
    session_path = Path(argv[argv.index("--") + 1])
    studio_dir = session_path.parent
    addon_path = studio_dir / "viu_creature_studio.py"
    if not addon_path.is_file():
        print("VIU_STUDIO_FAIL addon missing", addon_path)
        return

    spec = importlib.util.spec_from_file_location("viu_creature_studio", str(addon_path))
    if spec is None or spec.loader is None:
        print("VIU_STUDIO_FAIL spec")
        return
    mod = importlib.util.module_from_spec(spec)
    sys.modules["viu_creature_studio"] = mod
    spec.loader.exec_module(mod)
    mod.register()
    mod.load_session(str(session_path))
    print("VIU_STUDIO_OK", session_path)


if __name__ == "__main__":
    main()
