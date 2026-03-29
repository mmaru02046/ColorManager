from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ColorEntry:
    name: str
    hex_code: str

    @property
    def rgb(self) -> tuple[int, int, int]:
        value = self.hex_code.lstrip("#")
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


@dataclass(slots=True)
class Palette:
    name: str
    colors: list[ColorEntry] = field(default_factory=list)
    source_path: Path | None = None
    source_format: str = "unknown"
    source_group: str = "materials"

    @property
    def preview_colors(self) -> list[ColorEntry]:
        return self.colors[:6]
