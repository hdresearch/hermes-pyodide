"""
Patch instructions for tools/session_search_tool.py

Replace ThreadPoolExecutor async bridge with Pyodide-safe version.
"""

PATCHES = [
    {
        "description": "Replace async bridging in session_search with Pyodide-safe version",
        "file": "tools/session_search_tool.py",
        "find": '''        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                results = pool.submit(lambda: asyncio.run(_summarize_all())).result(timeout=60)
        except RuntimeError:
            # No event loop running, create a new one
            results = asyncio.run(_summarize_all())
        except concurrent.futures.TimeoutError:''',
        "replace": '''        try:
            from pyodide_shims import run_sync
            results = run_sync(_summarize_all())
        except ImportError:
            try:
                asyncio.get_running_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    results = pool.submit(lambda: asyncio.run(_summarize_all())).result(timeout=60)
            except RuntimeError:
                results = asyncio.run(_summarize_all())
        except concurrent.futures.TimeoutError:''',
    },
]
