"""Discover application modules without a central app-name list."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
import pkgutil

from ._api import App


def discover() -> dict[str, App]:
    found: dict[str, App] = {}
    for item in pkgutil.iter_modules(__path__):
        if item.name.startswith("_") or item.ispkg:
            continue
        module = import_module(f"{__name__}.{item.name}")
        app = getattr(module, "APP", None)
        if not isinstance(app, App) or app.name != item.name:
            raise RuntimeError(f"Application module {item.name} must export APP with the matching name")
        if app.name == "all":
            raise RuntimeError("Application name 'all' is reserved")
        if not app.default_subdir or Path(app.default_subdir).is_absolute() or ".." in Path(app.default_subdir).parts:
            raise RuntimeError(f"Invalid default directory for {app.name}")
        found[app.name] = app
    return dict(sorted(found.items()))
