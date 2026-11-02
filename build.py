"""
Build dist/AI-MC.exe with the .env values baked in.

  python build.py

The exe needs no .env next to it. A .env placed beside the exe still wins,
so keys can be rotated without rebuilding. Anyone holding the exe can dig the
key out of it, so share it only with the operators.
"""

import os
import shutil
import sys

from dotenv import dotenv_values

ROOT = os.path.dirname(os.path.abspath(__file__))
EMBED = os.path.join(ROOT, "_embedded_env.py")
FALLBACK = os.path.join(ROOT, "..", "MBRGEA-nominies", "python", "MBRGEA-Nominies", ".env")


def main() -> None:
    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        sys.exit("PyInstaller missing - run:  pip install pyinstaller")

    values = {**dotenv_values(FALLBACK), **dotenv_values(os.path.join(ROOT, ".env"))}
    values = {k: v for k, v in values.items() if v}
    if not values:
        print("[warn] no .env found - the exe will run without voice generation")
    with open(EMBED, "w", encoding="utf-8") as fh:
        fh.write(f"VALUES = {values!r}\n")

    try:
        pyinstaller.run([
            os.path.join(ROOT, "app.py"),
            "--name", "AI-MC",
            "--onefile",
            "--noconfirm",
            "--clean",
            "--paths", ROOT,
            "--add-data", f"{os.path.join(ROOT, 'web')}{os.pathsep}web",
            "--hidden-import", "_embedded_env",
            "--collect-submodules", "websockets",   # openai's realtime client imports it lazily
            "--distpath", os.path.join(ROOT, "dist"),
            "--workpath", os.path.join(ROOT, "build"),
            "--specpath", os.path.join(ROOT, "build"),
        ])
    finally:
        os.remove(EMBED)   # keep the key out of the source folder
        shutil.rmtree(os.path.join(ROOT, "build"), ignore_errors=True)
    print(f"\nbuilt {os.path.join(ROOT, 'dist', 'AI-MC.exe')}")


if __name__ == "__main__":
    main()
