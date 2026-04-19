from __future__ import annotations

import json
from pathlib import Path


class AppConfig:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.data = {
            "materials_dir": "",
            "library_dir": "",
            "local_materials_dir": "",
            "local_library_dir": "",
            "storage_mode": "local",
            "webdav_root_dir": "",
            "webdav_url": "",
            "webdav_username": "",
            "webdav_password": "",
            "ui_language": "zh",
            "favorite_palettes": [],
            "palette_groups": {},
            "tree_expanded": [],
            "welcome_seen": False,
        }
        self.load()

    def load(self) -> None:
        if not self.config_path.exists():
            return
        try:
            self.data.update(json.loads(self.config_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return

    def save(self) -> None:
        self.config_path.write_text(
            json.dumps(self.data, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    @property
    def materials_dir(self) -> str:
        return str(self.data.get("materials_dir", ""))

    @materials_dir.setter
    def materials_dir(self, value: str) -> None:
        self.data["materials_dir"] = value

    @property
    def local_materials_dir(self) -> str:
        return str(self.data.get("local_materials_dir", ""))

    @local_materials_dir.setter
    def local_materials_dir(self, value: str) -> None:
        self.data["local_materials_dir"] = value

    @property
    def library_dir(self) -> str:
        return str(self.data.get("library_dir", ""))

    @library_dir.setter
    def library_dir(self, value: str) -> None:
        self.data["library_dir"] = value

    @property
    def local_library_dir(self) -> str:
        return str(self.data.get("local_library_dir", ""))

    @local_library_dir.setter
    def local_library_dir(self, value: str) -> None:
        self.data["local_library_dir"] = value

    @property
    def storage_mode(self) -> str:
        value = str(self.data.get("storage_mode", "local")).lower()
        return value if value in {"local", "webdav"} else "local"

    @storage_mode.setter
    def storage_mode(self, value: str) -> None:
        self.data["storage_mode"] = value if value in {"local", "webdav"} else "local"

    @property
    def webdav_root_dir(self) -> str:
        return str(self.data.get("webdav_root_dir", ""))

    @webdav_root_dir.setter
    def webdav_root_dir(self, value: str) -> None:
        self.data["webdav_root_dir"] = value

    @property
    def webdav_url(self) -> str:
        return str(self.data.get("webdav_url", ""))

    @webdav_url.setter
    def webdav_url(self, value: str) -> None:
        self.data["webdav_url"] = value

    @property
    def webdav_username(self) -> str:
        return str(self.data.get("webdav_username", ""))

    @webdav_username.setter
    def webdav_username(self, value: str) -> None:
        self.data["webdav_username"] = value

    @property
    def webdav_password(self) -> str:
        return str(self.data.get("webdav_password", ""))

    @webdav_password.setter
    def webdav_password(self, value: str) -> None:
        self.data["webdav_password"] = value

    @property
    def ui_language(self) -> str:
        value = str(self.data.get("ui_language", "zh")).lower()
        return value if value in {"zh", "en"} else "zh"

    @ui_language.setter
    def ui_language(self, value: str) -> None:
        self.data["ui_language"] = value if value in {"zh", "en"} else "zh"

    @property
    def favorite_palettes(self) -> list[str]:
        return [str(value) for value in self.data.get("favorite_palettes", [])]

    def is_favorite(self, path: str) -> bool:
        return path in self.favorite_palettes

    def set_favorite(self, path: str, is_favorite: bool) -> None:
        favorites = set(self.favorite_palettes)
        if is_favorite:
            favorites.add(path)
        else:
            favorites.discard(path)
        self.data["favorite_palettes"] = sorted(favorites)

    @property
    def palette_groups(self) -> dict[str, list[str]]:
        raw = self.data.get("palette_groups", {})
        if not isinstance(raw, dict):
            return {}
        groups: dict[str, list[str]] = {}
        for name, values in raw.items():
            if isinstance(name, str) and isinstance(values, list):
                groups[name] = [str(value) for value in values]
        return groups

    def group_names(self) -> list[str]:
        return sorted(self.palette_groups)

    def groups_for_path(self, path: str) -> list[str]:
        return [name for name, paths in self.palette_groups.items() if path in paths]

    def add_to_group(self, group_name: str, path: str) -> None:
        name = group_name.strip()
        if not name:
            return
        groups = self.palette_groups
        values = set(groups.get(name, []))
        values.add(path)
        groups[name] = sorted(values)
        self.data["palette_groups"] = groups

    def remove_from_group(self, group_name: str, path: str) -> None:
        groups = self.palette_groups
        values = set(groups.get(group_name, []))
        values.discard(path)
        if values:
            groups[group_name] = sorted(values)
        else:
            groups.pop(group_name, None)
        self.data["palette_groups"] = groups

    @property
    def tree_expanded(self) -> list[str]:
        return [str(value) for value in self.data.get("tree_expanded", [])]

    def is_tree_expanded(self, key: str) -> bool:
        return key in self.tree_expanded

    def set_tree_expanded(self, key: str, expanded: bool) -> None:
        values = set(self.tree_expanded)
        if expanded:
            values.add(key)
        else:
            values.discard(key)
        self.data["tree_expanded"] = sorted(values)


    @property
    def welcome_seen(self) -> bool:
        return bool(self.data.get("welcome_seen", False))

    @welcome_seen.setter
    def welcome_seen(self, value: bool) -> None:
        self.data["welcome_seen"] = bool(value)
