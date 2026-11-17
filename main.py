"""Launcher for Instagram Collection Downloader.

Kept as a thin entry point so ``python main.py`` / ``uv run main.py`` and
PyInstaller builds keep working. All code lives in the ``collection_downloader``
package.
"""

from collection_downloader.gui.app import run

if __name__ == "__main__":
    run()
