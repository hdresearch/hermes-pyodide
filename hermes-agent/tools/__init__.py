#!/usr/bin/env python3
"""
Tools Package (Pyodide-compatible)

Lazy-importing version.  The original __init__.py eagerly imports every
tool module which pulls in firecrawl, fal_client, edge-tts, etc.

In the Pyodide build, tools are discovered by model_tools._discover_tools()
which already wraps each import in try/except.  This __init__.py is left
intentionally minimal — import tools directly from their modules when needed.
"""

# Only re-export the registry (used by model_tools.py)
from .registry import registry

__all__ = ["registry"]
