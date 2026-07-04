#!/usr/bin/env python3
"""
SAHPRA Watcher — Apify Actor entrypoint.

This module allows the Actor to be run as ``python -m src``.
"""

import asyncio
import sys

from .main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
