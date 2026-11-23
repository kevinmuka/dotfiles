"""Contract implemented by a single-file localbackup application module."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, TYPE_CHECKING
import argparse
import re

if TYPE_CHECKING:
    from ..config import AppConfig


@dataclass(frozen=True)
class Option:
    flag: str
    help: str
    kind: str = "path"

    def add_to(self, parser: argparse.ArgumentParser) -> None:
        if not re.fullmatch(r"--[a-z][a-z0-9-]*", self.flag):
            raise ValueError(f"Application options must use a long --name flag: {self.flag}")
        if self.kind == "bool":
            parser.add_argument(self.flag, action="store_true", help=self.help)
            return
        types = {"path": Path, "file": Path, "archive": Path, "int": int, "text": str}
        if self.kind not in types:
            raise ValueError(f"Unsupported option kind: {self.kind}")
        parser.add_argument(self.flag, type=types[self.kind], help=self.help)


@dataclass(frozen=True)
class App:
    name: str
    default_subdir: str
    default_time: str
    example_config: str
    backup: Callable[[AppConfig, argparse.Namespace], list[dict[str, str]]]
    restore: Callable[[AppConfig, argparse.Namespace], dict[str, object]]
    archive_sources: Callable[[AppConfig], tuple[tuple[str, Path, str, str], ...]]
    now_options: tuple[Option, ...] = ()
    restore_options: tuple[Option, ...] = ()
    config_keys: tuple[str, ...] = ()
    parse_config: Callable[[dict[str, object]], dict[str, object]] = field(
        default=lambda table: {}
    )
    conflicting_agents: dict[str, str] = field(default_factory=dict)
