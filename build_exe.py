from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
ENTRY_FILE = PROJECT_ROOT / "app" / "main.py"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
SPEC_FILE = PROJECT_ROOT / "ColorLibraryManager.spec"
ICON_FILE = PROJECT_ROOT / "icon.ico"


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
        "--windowed",
        "--name",
        "ColorLibraryManager",
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

    if ICON_FILE.exists():
        command.extend(["--icon", str(ICON_FILE)])

    for module_name in hidden_imports:
        command.extend(["--hidden-import", module_name])

    for module_name in excludes:
        command.extend(["--exclude-module", module_name])

    command.append(str(ENTRY_FILE))
    return command


def main() -> int:
    if not ENTRY_FILE.exists():
        raise FileNotFoundError(f"Entry file not found: {ENTRY_FILE}")

    remove_path(DIST_DIR)
    remove_path(BUILD_DIR)
    remove_path(SPEC_FILE)

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

    exe_path = DIST_DIR / "ColorLibraryManager" / "ColorLibraryManager.exe"
    print()
    print("Build finished.")
    print(f"EXE: {exe_path}")
    if ICON_FILE.exists():
        print(f"ICON: {ICON_FILE}")
    return 0


if __name__ == "__main__":
    main()
