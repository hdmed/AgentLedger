from __future__ import annotations

import argparse
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Construit l'executable OpenCost avec PyInstaller")
    parser.add_argument("--onedir", action="store_true", help="produit un dossier executable plus facile a deboguer")
    parser.add_argument("--clean", action="store_true", help="nettoie le cache PyInstaller avant le build")
    parser.add_argument("--confirm", action="store_true", help="autorise PyInstaller a ecraser la sortie existante")
    args = parser.parse_args()

    root = os.path.dirname(os.path.abspath(__file__))
    separator = os.pathsep
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        "OpenCost",
        "--noupx",
        "--hidden-import",
        "sqlite3",
    ]
    command.append("--onedir" if args.onedir else "--onefile")
    if args.clean:
        command.append("--clean")
    if not args.confirm:
        command.append("--noconfirm")
    for source, destination in (("templates", "templates"), ("assets", "assets"), ("config", "config")):
        command.extend(["--add-data", "{}{}{}".format(os.path.join(root, source), separator, destination)])
    command.extend(["--distpath", os.path.join(root, "dist"), "--workpath", os.path.join(root, "build"), os.path.join(root, "launcher.py")])

    print("Build OpenCost -> {}".format("one-dir" if args.onedir else "one-file"))
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
