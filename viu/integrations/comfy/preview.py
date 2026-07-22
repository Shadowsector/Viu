"""Preview MoCap: короткий клип + кадр в Telegram перед полной генерацией."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Tuple

from ...config import Config
from .framing import frame_spec_for_action
from ..telegram import settings as tg_settings
from ..telegram.client import TelegramClient, TelegramError


def extract_preview_still(video: Path, dest: Path | None = None) -> Tuple[bool, str]:
    """Средний кадр preview-mp4 → PNG для Telegram."""
    video = Path(video)
    if not video.is_file():
        return False, f"нет видео: {video}"
    if dest is None:
        dest = video.with_name(video.stem + "_preview.png")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        import imageio.v3 as iio  # type: ignore

        frames = iio.imread(video)
        if getattr(frames, "ndim", 0) >= 3:
            idx = (len(frames) - 1) // 2 if frames.ndim == 4 else 0
            frame = frames[idx] if frames.ndim == 4 else frames
            iio.imwrite(dest, frame)
            if dest.is_file():
                return True, str(dest)
    except Exception:
        pass

    from .clip_review import extract_last_frame

    return extract_last_frame(video, dest)


def preview_caption(action: str, spec_summary: str, video_path: str) -> str:
    return (
        "🎞 Comfy MoCap — preview (белый фон, полный рост, ¾)\n\n"
        f"Действие: {action[:200]}\n"
        f"Кадр: {spec_summary}\n"
        f"Файл: {Path(video_path).name if video_path else '—'}\n\n"
        "Ответь:\n"
        "• ок — 3 полных дубля ¾\n"
        "• нет / другой кадр — новый промпт по графу\n"
        "• стоп — отменить пул"
    )


def send_preview_for_approval(
    config: Config,
    *,
    action: str,
    still_path: str,
    video_path: str = "",
) -> Tuple[bool, str]:
    """Отправить preview-кадр (и подпись) в Telegram."""
    spec = frame_spec_for_action(action)
    caption = preview_caption(action, spec.summary_ru(), video_path)
    if not tg_settings.enabled(config):
        return False, "Telegram выключен — одобри preview в чате Вью: ок / нет / стоп."
    token = tg_settings.token(config)
    chat_id = tg_settings.chat_id(config)
    if not token or chat_id is None:
        return False, "Telegram не привязан."
    still = Path(still_path)
    if not still.is_file():
        return False, f"Нет preview-кадра: {still_path}"
    try:
        client = TelegramClient(token)
        client.send_photo(chat_id, still, caption=caption[:1024])
        return True, "Preview ушёл в Telegram — жду ок / нет / стоп."
    except TelegramError as exc:
        return False, f"Telegram: {exc}"
