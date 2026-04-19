from __future__ import annotations

import base64
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from urllib.request import (
    HTTPBasicAuthHandler,
    HTTPDigestAuthHandler,
    HTTPPasswordMgrWithDefaultRealm,
    Request,
    build_opener,
)


SUPPORTED_REMOTE_EXTENSIONS = {
    ".ase",
    ".csv",
    ".json",
    ".gpl",
    ".pal",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
}


class WebDavError(RuntimeError):
    pass


@dataclass(slots=True)
class WebDavEntry:
    relative_path: PurePosixPath
    is_dir: bool


class WebDavClient:
    def __init__(self, base_url: str, username: str = "", password: str = "", timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.username = username
        self.password = password
        password_manager = HTTPPasswordMgrWithDefaultRealm()
        password_manager.add_password(None, self.base_url, username, password)
        self.opener = build_opener(
            HTTPBasicAuthHandler(password_manager),
            HTTPDigestAuthHandler(password_manager),
        )

    def _authorization_header(self) -> dict[str, str]:
        if not self.username:
            return {}
        token = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    def _remote_path(self, remote_path: str | PurePosixPath) -> PurePosixPath:
        path = str(remote_path).strip()
        if not path:
            return PurePosixPath("/")
        normalized = "/" + path.strip("/")
        return PurePosixPath(normalized)

    def _build_url(self, remote_path: str | PurePosixPath, prefer_collection: bool = False) -> str:
        split = urlsplit(self.base_url)
        extra_path = self._remote_path(remote_path).as_posix()
        base_path = split.path.rstrip("/")
        full_path = base_path + extra_path
        if prefer_collection and not full_path.endswith("/"):
            full_path += "/"
        quoted_path = quote(full_path, safe="/:@")
        return urlunsplit((split.scheme, split.netloc, quoted_path, split.query, split.fragment))

    def _base_path_prefix(self) -> str:
        split = urlsplit(self.base_url)
        return unquote(split.path.rstrip("/"))

    def _request(
        self,
        method: str,
        remote_path: str | PurePosixPath,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        request = Request(
            self._build_url(remote_path, prefer_collection=method in {"PROPFIND", "MKCOL"}),
            data=data,
            headers={"User-Agent": "ColorManager/1.0", **self._authorization_header(), **(headers or {})},
            method=method,
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return response.read()
        except HTTPError as exc:
            raise WebDavError(f"{method} {remote_path}: HTTP {exc.code}") from exc
        except URLError as exc:
            raise WebDavError(f"{method} {remote_path}: {exc.reason}") from exc

    def _request_optional(
        self,
        method: str,
        remote_path: str | PurePosixPath,
        allowed_statuses: set[int],
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        request = Request(
            self._build_url(remote_path, prefer_collection=method in {"PROPFIND", "MKCOL"}),
            data=data,
            headers={"User-Agent": "ColorManager/1.0", **self._authorization_header(), **(headers or {})},
            method=method,
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code in allowed_statuses:
                return exc.read()
            raise WebDavError(f"{method} {remote_path}: HTTP {exc.code}") from exc
        except URLError as exc:
            raise WebDavError(f"{method} {remote_path}: {exc.reason}") from exc

    def ensure_directory(self, remote_path: str | PurePosixPath) -> None:
        path = self._remote_path(remote_path)
        current = PurePosixPath("/")
        for part in path.parts[1:]:
            current /= part
            self._request_optional("MKCOL", current, {301, 405})

    def ensure_child_directory(self, parent_path: str | PurePosixPath, child_name: str) -> None:
        parent = self._remote_path(parent_path)
        child = parent / child_name.strip("/")
        self._request_optional("MKCOL", child, {301, 405})

    def ensure_directory_below_root(
        self,
        existing_root: str | PurePosixPath,
        remote_path: str | PurePosixPath,
    ) -> None:
        root = self._remote_path(existing_root)
        path = self._remote_path(remote_path)
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise WebDavError(f"{path} is not under {root}") from exc
        current = root
        for part in relative.parts:
            if part in {"", "/"}:
                continue
            current /= part
            self._request_optional("MKCOL", current, {301, 405})

    def list_directory(self, remote_path: str | PurePosixPath) -> list[WebDavEntry]:
        path = self._remote_path(remote_path)
        body = b"""<?xml version="1.0" encoding="utf-8" ?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:resourcetype />
  </d:prop>
</d:propfind>"""
        payload = self._request(
            "PROPFIND",
            path,
            data=body,
            headers={"Depth": "1", "Content-Type": "text/xml; charset=utf-8"},
        )
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise WebDavError("Failed to parse WebDAV directory listing") from exc
        namespace = {"d": "DAV:"}
        entries: list[WebDavEntry] = []
        current_path = self._remote_path(path).as_posix().rstrip("/")
        base_prefix = self._base_path_prefix()
        for response in root.findall("d:response", namespace):
            href = response.findtext("d:href", default="", namespaces=namespace).rstrip("/")
            if not href:
                continue
            href_path = unquote(urlsplit(href).path or href).rstrip("/")
            if not href_path:
                continue
            if base_prefix and href_path.startswith(base_prefix):
                href_path = href_path[len(base_prefix):] or "/"
            if href_path.endswith(current_path):
                continue
            if not href_path.startswith(current_path):
                continue
            relative = href_path[len(current_path):].strip("/")
            if not relative:
                continue
            resourcetype = response.find("d:propstat/d:prop/d:resourcetype", namespace)
            is_dir = resourcetype is not None and resourcetype.find("d:collection", namespace) is not None
            entries.append(WebDavEntry(relative_path=PurePosixPath(relative), is_dir=is_dir))
        return entries

    def list_child_directory_names(self, remote_path: str | PurePosixPath) -> set[str]:
        names: set[str] = set()
        for entry in self.list_directory(remote_path):
            if entry.is_dir and len(entry.relative_path.parts) == 1:
                names.add(entry.relative_path.parts[0])
        return names

    def iter_files(self, remote_path: str | PurePosixPath) -> list[PurePosixPath]:
        stack = [self._remote_path(remote_path)]
        files: list[PurePosixPath] = []
        while stack:
            current = stack.pop()
            for entry in self.list_directory(current):
                child_path = current / entry.relative_path
                if entry.is_dir:
                    stack.append(child_path)
                elif child_path.suffix.lower() in SUPPORTED_REMOTE_EXTENSIONS:
                    files.append(child_path)
        return files

    def download_file(self, remote_path: str | PurePosixPath, local_path: Path) -> None:
        payload = self._request("GET", remote_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(payload)

    def upload_file(
        self,
        local_path: Path,
        remote_path: str | PurePosixPath,
        existing_root: str | PurePosixPath | None = None,
    ) -> None:
        parent = self._remote_path(remote_path).parent
        if existing_root is None:
            self.ensure_directory(parent)
        else:
            self.ensure_directory_below_root(existing_root, parent)
        self._request(
            "PUT",
            remote_path,
            data=local_path.read_bytes(),
            headers={"Content-Type": "application/octet-stream"},
        )

    def move(
        self,
        source_path: str | PurePosixPath,
        target_path: str | PurePosixPath,
        existing_root: str | PurePosixPath | None = None,
    ) -> None:
        target_parent = self._remote_path(target_path).parent
        if existing_root is None:
            self.ensure_directory(target_parent)
        else:
            self.ensure_directory_below_root(existing_root, target_parent)
        self._request(
            "MOVE",
            source_path,
            headers={
                "Destination": self._build_url(target_path),
                "Overwrite": "T",
            },
        )

    def delete(self, remote_path: str | PurePosixPath) -> None:
        self._request_optional("DELETE", remote_path, {404})

    def sync_directory(self, remote_path: str | PurePosixPath, local_dir: Path) -> None:
        local_dir.mkdir(parents=True, exist_ok=True)
        remote_files = self.iter_files(remote_path)
        seen: set[Path] = set()
        remote_root = self._remote_path(remote_path)
        for remote_file in remote_files:
            relative = Path(*remote_file.relative_to(remote_root).parts)
            local_path = local_dir / relative
            self.download_file(remote_file, local_path)
            seen.add(local_path.resolve())
        for local_path in list(local_dir.rglob("*")):
            if not local_path.is_file():
                continue
            if local_path.resolve() not in seen:
                local_path.unlink(missing_ok=True)
        for local_path in sorted(local_dir.rglob("*"), reverse=True):
            if local_path.is_dir() and not any(local_path.iterdir()):
                local_path.rmdir()

    def upload_tree_files(self, local_root: Path, remote_root: str | PurePosixPath, files: list[Path]) -> None:
        for local_path in files:
            relative = local_path.relative_to(local_root)
            remote_path = self._remote_path(remote_root) / PurePosixPath(*relative.parts)
            self.upload_file(local_path, remote_path)

    def clear_local_cache(self, local_root: Path) -> None:
        if local_root.exists():
            shutil.rmtree(local_root)
