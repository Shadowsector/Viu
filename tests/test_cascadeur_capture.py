"""Тесты vision-вердикта Cascadeur."""

from viu.integrations.cascadeur.capture import _parse_verdict, capture_and_verify_cascadeur


def test_parse_verdict_llava_start_screen():
    text = (
        "[llava:latest]\n"
        "1) Это welcome/start screen или 3D viewport? - Это Start Screen\n"
        "2) Видна модель? - Отсутствует видная модель\n"
        "3) Есть диалог (Import, Rig mode)? - Да, Import, Rig mode\n"
        "4) Верд"
    )
    assert _parse_verdict(text) in ("WELCOME", "DIALOG")


def test_parse_verdict_model_ok():
    text = "3D viewport, персонаж виден в сцене. Вердикт: MODEL_OK"
    assert _parse_verdict(text) == "MODEL_OK"


def test_capture_fails_on_welcome_when_require_model(tmp_path, monkeypatch):
    from viu.config import Config

    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    png = tmp_path / "shot.png"
    png.write_bytes(b"fake")

    monkeypatch.setattr(
        "viu.integrations.cascadeur.capture.capture_cascadeur_png",
        lambda *a, **k: (True, "скрин ok", 123),
    )
    monkeypatch.setattr(
        "viu.integrations.cascadeur.capture.analyze_cascadeur_shot",
        lambda *a, **k: (True, "Start Screen, Import dialog", "WELCOME"),
    )

    ok, msg, meta = capture_and_verify_cascadeur(cfg, png, require_model=True)
    assert not ok
    assert meta["verdict"] == "WELCOME"
    assert "Vision:" in msg
