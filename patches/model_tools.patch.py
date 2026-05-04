"""
Patch instructions for model_tools.py

Replace _run_async() with a Pyodide-safe version.
"""

PATCHES = [
    {
        "description": "Replace _run_async with Pyodide-safe version",
        "file": "model_tools.py",
        "find": '''def _run_async(coro):
    """Run an async coroutine from a sync context.

    If the current thread already has a running event loop (e.g., inside
    the gateway's async stack or Atropos's event loop), we spin up a
    disposable thread so asyncio.run() can create its own loop without
    conflicting.

    This is the single source of truth for sync->async bridging in tool
    handlers. The RL paths (agent_loop.py, tool_context.py) also provide
    outer thread-pool wrapping as defense-in-depth, but each handler is
    self-protecting via this function.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=300)
    return asyncio.run(coro)''',
        "replace": '''def _run_async(coro):
    """Run an async coroutine from a sync context.

    Pyodide-compatible: uses pyodide_shims.run_sync() when available,
    which correctly bridges the browser event loop.  Falls back to
    asyncio.run() in native Python.
    """
    try:
        from pyodide_shims import run_sync
        return run_sync(coro)
    except ImportError:
        pass

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=300)
    return asyncio.run(coro)''',
    },
]
