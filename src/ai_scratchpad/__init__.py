# /// script
# requires-python = ">=3.10"
# dependencies = ["aiohttp>=3.9"]
# [tool.uv.sources]
# ///
"""
iTerm2 AI Scratchpad — aiohttp server with embedded HTML UI.
Posts notes from AI agents, displays in iTerm2 Toolbelt sidebar.
"""

# Unset PYTHONPATH to avoid conflicts with system Python packages
import os
os.environ.pop("PYTHONPATH", None)

import logging
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_PATH = Path.home() / "iterm2_scratchpad.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    Observer = None  # type: ignore
    FileSystemEventHandler = object  # type: ignore
    WATCHDOG_AVAILABLE = False

try:
    import iterm2 as _iterm2
    ITERM2_AVAILABLE = True
except ImportError:
    _iterm2 = None  # type: ignore
    ITERM2_AVAILABLE = False
