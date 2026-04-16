from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.branding import APP_AUTHOR, APP_COPYRIGHT, APP_NAME, APP_VERSION, APP_VERSION_INFO

PROJECT_ROOT = Path(__file__).resolve().parent
ENTRY_FILE = PROJECT_ROOT / "app" / "main.py"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
SPEC_FILE = PROJECT_ROOT / f"{APP_NAME}.spec"
LEGACY_SPEC_FILE = PROJECT_ROOT / "ColorLibraryManager.spec"
ICON_FILE = PROJECT_ROOT / "icon.ico"
VERSION_INFO_FILE = PROJECT_ROOT / "version_info.txt"


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()


def resolve_pyinstaller_command() -> list[str]:
    candidates = [
        shutil.which("pyinstaller"),
        str(Path.home() / "AppData" / "Roaming" / "Python" / "Python311" / "Scripts" / "pyinstaller.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return [candidate]
    return [sys.executable, "-m", "PyInstaller"]


def build_command() -> list[str]:
    hidden_imports = [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ]
    excludes = [
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "sklearn",
        "jupyter",
        "notebook",
        "IPython",
        "PyQt5",
        "PyQt6",
    ]

    command = resolve_pyinstaller_command() + [
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(PROJECT_ROOT),
        "--paths",
        str(PROJECT_ROOT),
        "--collect-submodules",
        "app",
    ]

    asset_dir = PROJECT_ROOT / "app" / "assets"
    if asset_dir.exists():
        command.extend(["--add-data", f"{asset_dir}{os.pathsep}app/assets"])

    if ICON_FILE.exists():
        command.extend(["--icon", str(ICON_FILE)])
        command.extend(["--add-data", f"{ICON_FILE}{os.pathsep}."])
    if VERSION_INFO_FILE.exists():
        command.extend(["--version-file", str(VERSION_INFO_FILE)])

    for module_name in hidden_imports:
        command.extend(["--hidden-import", module_name])

    for module_name in excludes:
        command.extend(["--exclude-module", module_name])

    command.append(str(ENTRY_FILE))
    return command


def ensure_version_info_file() -> None:
    major, minor, patch, build = APP_VERSION_INFO
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, {build}),
    prodvers=({major}, {minor}, {patch}, {build}),
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'080404B0',
          [
            StringStruct(u'CompanyName', u'{APP_AUTHOR}'),
            StringStruct(u'FileDescription', u'{APP_NAME}'),
            StringStruct(u'FileVersion', u'{APP_VERSION}'),
            StringStruct(u'InternalName', u'{APP_NAME}'),
            StringStruct(u'LegalCopyright', u'{APP_COPYRIGHT}'),
            StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
            StringStruct(u'ProductName', u'{APP_NAME}'),
            StringStruct(u'ProductVersion', u'{APP_VERSION}')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
  ]
)"""
    VERSION_INFO_FILE.write_text(content, encoding="utf-8")


def main() -> int:
    if not ENTRY_FILE.exists():
        raise FileNotFoundError(f"Entry file not found: {ENTRY_FILE}")

    ensure_version_info_file()
    remove_path(DIST_DIR)
    remove_path(BUILD_DIR)
    remove_path(SPEC_FILE)
    remove_path(LEGACY_SPEC_FILE)

    command = build_command()
    print("Running:")
    print(" ".join(f'"{part}"' if " " in part else part for part in command))
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if completed.stdout:
        print(completed.stdout)
    if completed.stderr:
        print(completed.stderr)

    if completed.returncode != 0:
        print()
        print(f"Build failed with exit code {completed.returncode}.")
        return completed.returncode

    exe_path = DIST_DIR / APP_NAME / f"{APP_NAME}.exe"
    print()
    print("Build finished.")
    print(f"APP: {APP_NAME} {APP_VERSION}")
    print(f"AUTHOR: {APP_AUTHOR}")
    print(f"COPYRIGHT: {APP_COPYRIGHT}")
    print(f"EXE: {exe_path}")
    if ICON_FILE.exists():
        print(f"ICON: {ICON_FILE}")
    if VERSION_INFO_FILE.exists():
        print(f"VERSION FILE: {VERSION_INFO_FILE}")
    return 0


if __name__ == "__main__":
    main()
