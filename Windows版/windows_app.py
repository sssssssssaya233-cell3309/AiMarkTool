"""Windows portable entry point for AiMarkTool.

This module intentionally lives outside the existing macOS entry point.  It
only supplies Windows-specific runtime discovery and defaults, then reuses the
shared application UI and watermark engine.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _portable_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# Source runs import the shared application from the repository root.
source_root = _source_root()
if str(source_root) not in sys.path:
    sys.path.insert(0, str(source_root))

# The portable archive places ffmpeg.exe and ffprobe.exe beside AiMarkTool.exe.
# Prepending that location makes the existing engine discover them without
# changing the macOS implementation.
portable_root = _portable_root()
os.environ["PATH"] = str(portable_root) + os.pathsep + os.environ.get("PATH", "")

from app import WatermarkApp  # noqa: E402


class WindowsWatermarkApp(WatermarkApp):
    def __init__(self) -> None:
        super().__init__()
        self.title("水印工坊 · Windows")
        self.output_dir.set(str(Path.home() / "Videos" / "Watermarked"))


if __name__ == "__main__":
    WindowsWatermarkApp().mainloop()
