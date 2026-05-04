"""
Pyodide compatibility shims for hermes-agent.

This module monkey-patches threading, asyncio, and httpx to work in
Pyodide's single-threaded WebAssembly environment.  Import this module
BEFORE importing any hermes-agent code.

    import pyodide_shims          # patches applied on import
    from run_agent import AIAgent # now safe
"""

import sys
import os

# ---------------------------------------------------------------------------
# Detect whether we're actually running inside Pyodide
# ---------------------------------------------------------------------------
IN_PYODIDE = "pyodide" in sys.modules or "_pyodide" in sys.modules or \
             os.environ.get("PYODIDE", "") == "1"

# ---------------------------------------------------------------------------
# 1.  threading.Thread  →  synchronous execution
#
#     In single-threaded Wasm there are no OS threads.  We replace Thread
#     with a shim that runs the target callable *synchronously* in start().
#     threading.Event / Lock / RLock already work fine (they're just flags
#     when there's only one thread).
# ---------------------------------------------------------------------------

import threading as _threading

_OriginalThread = _threading.Thread


class _SyncThread:
    """Drop-in replacement for threading.Thread that runs synchronously."""

    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs=None, *, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}
        self._started = False
        self._alive = False

    def start(self):
        self._started = True
        self._alive = True
        try:
            if self._target:
                self._target(*self._args, **self._kwargs)
        finally:
            self._alive = False

    def join(self, timeout=None):
        pass  # already finished

    def is_alive(self):
        return self._alive

    @property
    def daemon(self):
        return True

    @daemon.setter
    def daemon(self, _):
        pass


if IN_PYODIDE:
    _threading.Thread = _SyncThread


# ---------------------------------------------------------------------------
# 2.  concurrent.futures.ThreadPoolExecutor  →  synchronous execution
# ---------------------------------------------------------------------------

import concurrent.futures as _cf

_OriginalTPE = _cf.ThreadPoolExecutor


class _SyncPoolExecutor:
    """ThreadPoolExecutor replacement: runs callables synchronously."""

    def __init__(self, max_workers=None, **kw):
        pass

    def submit(self, fn, *args, **kwargs):
        fut = _cf.Future()
        try:
            result = fn(*args, **kwargs)
            fut.set_result(result)
        except Exception as exc:
            fut.set_exception(exc)
        return fut

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def shutdown(self, wait=True, **kw):
        pass


if IN_PYODIDE:
    _cf.ThreadPoolExecutor = _SyncPoolExecutor


# ---------------------------------------------------------------------------
# 3.  asyncio  →  make asyncio.run() work in Pyodide
#
#     Pyodide runs inside the browser event loop.  asyncio.run() tries to
#     create a new loop and fails if one is already running.  We provide
#     a run_sync helper that works in both Pyodide and native Python.
# ---------------------------------------------------------------------------

import asyncio as _asyncio


def run_sync(coro):
    """Run a coroutine to completion, Pyodide-safe.

    - Native Python (no running loop): uses asyncio.run()
    - Pyodide: uses pyodide.ffi.run_sync() which unblocks the browser
      event loop between await points.
    - Native Python (loop already running): nest_asyncio-style or
      ThreadPool fallback.
    """
    if IN_PYODIDE:
        try:
            from pyodide.ffi import run_sync as _pyodide_run_sync
            return _pyodide_run_sync(coro)
        except ImportError:
            pass

    try:
        loop = _asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None or not loop.is_running():
        return _asyncio.run(coro)

    # Loop is running (e.g. Jupyter, gateway) — run in a thread.
    # This path isn't hit in Pyodide (single-threaded).
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_asyncio.run, coro)
        return future.result(timeout=300)


# ---------------------------------------------------------------------------
# 4.  httpx transport backed by Pyodide's pyfetch (browser fetch API)
#
#     The openai library uses httpx.Client for HTTP.  In Pyodide, raw
#     sockets don't exist — all HTTP must go through the browser's fetch().
# ---------------------------------------------------------------------------

_fetch_transport = None  # lazy-init


def _get_fetch_transport():
    """Create (once) an httpx.BaseTransport that uses Pyodide's pyfetch."""
    global _fetch_transport
    if _fetch_transport is not None:
        return _fetch_transport

    import httpx

    if not IN_PYODIDE:
        # Not in Pyodide — return None so callers use the default transport
        return None

    from pyodide.http import pyfetch
    from pyodide.ffi import run_sync as _pyodide_run_sync

    class _FetchTransport(httpx.BaseTransport):
        """httpx sync transport backed by browser fetch()."""

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            # Build headers dict (httpx Headers → plain dict)
            headers = {}
            for k, v in request.headers.raw:
                name = k.decode("latin-1")
                # Skip host and content-length — fetch sets these
                if name.lower() in ("host", "content-length", "transfer-encoding"):
                    continue
                headers[name] = v.decode("latin-1")

            body = bytes(request.content) if request.content else None

            # pyfetch is async — bridge to sync via Pyodide helper
            resp = _pyodide_run_sync(pyfetch(
                str(request.url),
                method=request.method,
                headers=headers,
                body=body,
            ))

            # Read the full body
            resp_bytes = _pyodide_run_sync(resp.bytes())

            # Build response headers
            resp_headers = {}
            js_headers = resp.js_response.headers
            # js_headers is a JS Headers object — iterate via entries()
            try:
                entries = js_headers.entries()
                while True:
                    entry = entries.next()
                    if entry.done:
                        break
                    resp_headers[entry.value[0]] = entry.value[1]
            except Exception:
                pass

            return httpx.Response(
                status_code=resp.status,
                headers=resp_headers,
                content=resp_bytes,
            )

    _fetch_transport = _FetchTransport()
    return _fetch_transport


def make_openai_client(**kwargs):
    """Create an openai.OpenAI client that works in Pyodide.

    Passes a custom httpx.Client with the fetch transport when running
    in Pyodide.  In native Python, passes through to the normal constructor.
    """
    from openai import OpenAI
    import httpx

    transport = _get_fetch_transport()
    if transport is not None:
        custom_httpx = httpx.Client(transport=transport)
        kwargs.setdefault("http_client", custom_httpx)

    return OpenAI(**kwargs)


# ---------------------------------------------------------------------------
# 5.  Patch requests (used by agent/model_metadata.py)
#
#     pyodide-http monkey-patches urllib3 to use XMLHttpRequest.
# ---------------------------------------------------------------------------

if IN_PYODIDE:
    try:
        import pyodide_http
        pyodide_http.patch_all()
    except ImportError:
        pass  # pyodide-http not installed — requests.get() will fail at call time


# ---------------------------------------------------------------------------
# 6.  subprocess  →  always raises
#
#     No tool in the core Pyodide toolset uses subprocess.  But some modules
#     import it at module level.  We don't need to shim it — Python's
#     subprocess module can be *imported* fine; it only fails at Popen().
#     This is handled naturally by the tool check_fn gating.
# ---------------------------------------------------------------------------

# (no action needed)


# ---------------------------------------------------------------------------
# 7.  signal  →  no-op handlers
#
#     Some modules register signal handlers.  In WASI / Pyodide, signal()
#     is mostly a no-op.  Python's signal module can be imported; it just
#     silently ignores signal.signal() calls in Emscripten/WASI.
# ---------------------------------------------------------------------------

# (no action needed)


# ---------------------------------------------------------------------------
# Ensure shims are importable from hermes code as:
#     from pyodide_shims import run_sync, make_openai_client, IN_PYODIDE
# ---------------------------------------------------------------------------

__all__ = [
    "IN_PYODIDE",
    "run_sync",
    "make_openai_client",
    "_get_fetch_transport",
]
