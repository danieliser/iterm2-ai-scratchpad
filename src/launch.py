#!/usr/bin/env python3
"""iTerm2 AutoLaunch entry point — imports and runs the ai_scratchpad package."""
import sys
from pathlib import Path

# Ensure the src/ directory is on the path so the package can be found
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai_scratchpad.app import main

main()
