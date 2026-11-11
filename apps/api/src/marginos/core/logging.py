"""Structured-enough logging for a single service. Never log secret values."""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s", "%H:%M:%S")
    )
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("httpx").setLevel("WARNING")
