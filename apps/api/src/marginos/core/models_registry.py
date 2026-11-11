"""Imports every domain's models so Base.metadata is complete for Alembic and tests."""

from __future__ import annotations

import importlib

MODEL_MODULES: tuple[str, ...] = (
    "marginos.domains.catalog.models",
    "marginos.domains.operations.models",
)


def import_all_models() -> None:
    for module in MODEL_MODULES:
        importlib.import_module(module)
