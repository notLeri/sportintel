"""Агрегатор MetaData модулей для Alembic autogenerate."""

import importlib
import importlib.util
import pkgutil

from sqlalchemy import MetaData

ALL_METADATA: list[MetaData] = []


def register(metadata: MetaData) -> MetaData:
    """Вызывается в `modules/<m>/infrastructure/tables.py`: `metadata = register(MetaData(...))`."""
    if metadata not in ALL_METADATA:
        ALL_METADATA.append(metadata)
    return metadata


def load_all() -> list[MetaData]:
    """Импортирует tables.py всех модулей, чтобы их MetaData зарегистрировались."""
    if importlib.util.find_spec("sportintel.modules") is None:
        return ALL_METADATA
    modules = importlib.import_module("sportintel.modules")
    for info in pkgutil.iter_modules(modules.__path__):
        name = f"sportintel.modules.{info.name}.infrastructure.tables"
        if importlib.util.find_spec(name) is not None:
            importlib.import_module(name)
    return ALL_METADATA
