from __future__ import annotations

import argparse
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Build the AgentLedger executable with PyInstaller")
    parser.add_argument("--onedir", action="store_true", help="produce a debug-friendly folder executable")
    parser.add_argument("--clean", action="store_true", help="clean the PyInstaller cache before building")
    parser.add_argument("--confirm", action="store_true", help="allow PyInstaller to overwrite existing output")
    args = parser.parse_args()

    root = os.path.dirname(os.path.abspath(__file__))
    separator = os.pathsep
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        "AgentLedger",
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

    print("Build AgentLedger -> {}".format("one-dir" if args.onedir else "one-file"))
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
