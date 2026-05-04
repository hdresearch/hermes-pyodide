"""
Patch instructions for agent/auxiliary_client.py

Replace asyncio.to_thread with direct sync call for Pyodide.
"""

PATCHES = [
    {
        "description": "Replace asyncio.to_thread with sync fallback in _AsyncCodexCompletionsAdapter",
        "file": "agent/auxiliary_client.py",
        "find": '''    async def create(self, **kwargs) -> Any:
        import asyncio
        return await asyncio.to_thread(self._sync.create, **kwargs)''',
        "replace": '''    async def create(self, **kwargs) -> Any:
        try:
            from pyodide_shims import IN_PYODIDE
            if IN_PYODIDE:
                # Single-threaded: just call synchronously
                return self._sync.create(**kwargs)
        except ImportError:
            pass
        import asyncio
        return await asyncio.to_thread(self._sync.create, **kwargs)''',
    },
]
