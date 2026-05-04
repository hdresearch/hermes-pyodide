# hermes-pyodide

Run [hermes-agent](../hermes-agent) in the browser via [Pyodide](https://pyodide.org) — CPython compiled to WebAssembly.

Everything runs single-threaded, like postgres-wasm's single-process mode. No relay server needed for the core agent loop — the browser makes `fetch()` calls directly to the LLM API.

## What this is

A **patch set + shim layer** (~130 lines of changes) that makes hermes-agent's core conversation loop work inside Pyodide:

| Component | What was changed |
|---|---|
| `pyodide_shims.py` | Monkey-patches `threading.Thread` → sync, `ThreadPoolExecutor` → sync, provides `pyfetch`-backed httpx transport for the OpenAI client |
| `run_agent.py` | `_interruptible_api_call()` calls API synchronously (no background thread) |
| `agent/display.py` | `KawaiiSpinner` replaced with a no-op (browser UI is JS-side) |
| `model_tools.py` | `_run_async()` uses `pyodide_shims.run_sync()` instead of `asyncio.run()` in a thread |
| `agent/auxiliary_client.py` | `asyncio.to_thread()` → direct sync call |
| `hermes_state.py` | `PRAGMA journal_mode=WAL` → `DELETE` (wa-sqlite compat) |
| `tools/session_search_tool.py` | Async bridging uses `pyodide_shims.run_sync()` |
| `tools/__init__.py` | Lazy imports (original eagerly imports all tools, pulling in missing deps) |

The shims are **no-ops in native Python** — the patched code runs identically on a normal machine.

## Setup

```bash
# 1. Apply patches to hermes-agent, creating a patched copy
python apply_patches.py --source ../hermes-agent --dest ./hermes-agent

# 2. Test natively (no browser needed)
python test_native.py --simulate-pyodide

# 3. Test with hermes-agent's deps available
source ../hermes-agent/venv/bin/activate
PYTHONPATH=.:./hermes-agent python test_native.py --simulate-pyodide
```

## How it works

### The shim strategy

Pyodide runs CPython inside WebAssembly.  Python code runs unmodified — but OS primitives don't exist:

| OS Primitive | Used For | Pyodide Shim |
|---|---|---|
| `threading.Thread` | Interruptible API call, spinner animation | Runs target function synchronously in `start()` |
| `ThreadPoolExecutor` | Async-to-sync bridging | Calls function synchronously in `submit()` |
| `asyncio.run()` | Running async tool handlers | `pyodide.ffi.run_sync()` (uses browser event loop) |
| `socket` (via httpx) | HTTP to LLM API | `pyodide.http.pyfetch()` → browser `fetch()` |
| `subprocess` | Terminal tool, browser tool | Not shimmed — these tools are simply not loaded |
| SQLite WAL mode | Session state | Switched to DELETE mode (wa-sqlite compat) |

### What works in the browser

- **Full conversation loop** — `AIAgent.run_conversation()` calls the LLM API, parses tool calls, dispatches tools, manages context
- **Session state** — SQLite-backed session persistence (wa-sqlite)
- **Memory / Todo / Skills** — pure file I/O on Pyodide's Emscripten FS
- **Session search** — FTS5 search over conversation history
- **Clarify tool** — interactive questions to the user
- **Context compression** — summarizes old turns to stay within context window
- **Prompt caching** — Anthropic cache breakpoints for Claude models

### What doesn't work (tools not loaded)

Tools gated behind `check_fn` that require subprocess, Browserbase, ffmpeg, etc.:
`terminal`, `browser_*`, `execute_code`, `delegate_task`, `text_to_speech`, `process`, `file_*` (read/write/patch/search via terminal backend)

### CORS consideration

The browser's `fetch()` enforces CORS.  LLM APIs must send `Access-Control-Allow-Origin` headers.  If they don't, you need a lightweight CORS proxy.  OpenRouter works from the browser.

## File structure

```
hermes-pyodide/
├── README.md                 ← this file
├── pyodide_shims.py          ← the shim layer (copied into hermes-agent on patch)
├── apply_patches.py          ← applies all patches to a hermes-agent tree
├── test_native.py            ← test suite (works without a browser)
├── index.html                ← browser demo harness
├── patches/                  ← individual patch definitions
│   ├── run_agent.patch.py
│   ├── display.patch.py
│   ├── model_tools.patch.py
│   ├── hermes_state.patch.py
│   ├── auxiliary_client.patch.py
│   └── session_search.patch.py
└── hermes-agent/             ← patched copy (created by apply_patches.py)
    ├── pyodide_shims.py
    ├── run_agent.py           (patched)
    ├── model_tools.py         (patched)
    ├── hermes_state.py        (patched)
    ├── agent/display.py       (patched)
    ├── agent/auxiliary_client.py (patched)
    ├── tools/__init__.py      (replaced with lazy version)
    ├── tools/session_search_tool.py (patched)
    └── ... (everything else unchanged)
```

## To deploy in a browser

1. Serve the patched `hermes-agent/` directory as static files
2. Load Pyodide + install packages:
   ```js
   const pyodide = await loadPyodide();
   await pyodide.loadPackage(['micropip', 'sqlite3', 'pyyaml']);
   await pyodide.runPythonAsync(`
       import micropip
       await micropip.install(['openai', 'httpx', 'pydantic', 'tenacity',
                                'python-dotenv', 'jinja2', 'pyodide-http'])
   `);
   ```
3. Load hermes-agent modules from your server
4. Run the agent:
   ```python
   import pyodide_shims
   from run_agent import AIAgent

   agent = AIAgent(
       api_key="sk-or-...",
       model="anthropic/claude-sonnet-4-20250514",
       enabled_toolsets=["memory", "skills", "planning"],
       quiet_mode=True,
   )
   result = agent.run_conversation("Hello!")
   ```

**Tip:** Run Pyodide in a [Web Worker](https://pyodide.org/en/stable/usage/webworker.html) so the API call doesn't freeze the browser tab.
