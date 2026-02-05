from __future__ import annotations

import logging


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level))
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("comtypes").setLevel(logging.WARNING)
