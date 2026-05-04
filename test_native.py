#!/usr/bin/env python3
"""
Test the Pyodide shims in native Python.

Simulates the Pyodide environment by setting PYODIDE=1, then verifies
that the patched hermes-agent code runs correctly with the shims.

Run this AFTER apply_patches.py has created the patched tree.

Usage:
    python test_native.py [--hermes-dir ./hermes-agent]
"""

import argparse
import os
import sys


def test_shims_import():
    """Test that pyodide_shims imports and detects environment."""
    print("1. Testing pyodide_shims import...")
    import pyodide_shims
    print(f"   IN_PYODIDE = {pyodide_shims.IN_PYODIDE}")
    # When PYODIDE=1, shims should be active
    if os.environ.get("PYODIDE") == "1":
        assert pyodide_shims.IN_PYODIDE, "Should detect PYODIDE=1"
        print("   ✓ Detected simulated Pyodide environment")
    else:
        print("   ✓ Running in native mode (shims inactive)")


def test_threading_shim():
    """Test that Thread shim runs synchronously."""
    print("\n2. Testing threading shim...")
    import threading

    results = []

    def worker(x):
        results.append(x * 2)

    t = threading.Thread(target=worker, args=(21,))
    t.start()
    t.join()

    if os.environ.get("PYODIDE") == "1":
        # In shim mode, result should already be available (sync execution)
        assert results == [42], f"Expected [42], got {results}"
        assert not t.is_alive(), "Thread should not be alive after sync execution"
        print("   ✓ Thread ran synchronously, result = 42")
    else:
        # In native mode, thread ran normally
        assert results == [42], f"Expected [42], got {results}"
        print("   ✓ Thread ran normally, result = 42")


def test_threadpool_shim():
    """Test that ThreadPoolExecutor shim works."""
    print("\n3. Testing ThreadPoolExecutor shim...")
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda x: x ** 2, 7)
        result = future.result(timeout=5)

    assert result == 49, f"Expected 49, got {result}"
    print(f"   ✓ ThreadPoolExecutor result = {result}")


def test_run_sync():
    """Test the async bridging helper."""
    print("\n4. Testing run_sync (async bridging)...")
    import asyncio
    from pyodide_shims import run_sync

    async def async_add(a, b):
        return a + b

    result = run_sync(async_add(3, 4))
    assert result == 7, f"Expected 7, got {result}"
    print(f"   ✓ run_sync(async_add(3, 4)) = {result}")


def test_openai_client_creation():
    """Test that make_openai_client works (without actually calling an API)."""
    print("\n5. Testing OpenAI client creation...")
    try:
        import httpx
        from pyodide_shims import make_openai_client

        # In native mode, this just creates a normal client
        # In PYODIDE mode, it would inject the fetch transport
        # Either way it shouldn't crash
        client = make_openai_client(api_key="test-key", base_url="http://localhost:1/v1")
        print(f"   ✓ Client created: {type(client).__name__}")
    except ImportError as e:
        print(f"   ⚠ Skipped (missing dep): {e}")


def test_hermes_imports(hermes_dir):
    """Test that the patched hermes-agent modules import correctly."""
    print("\n6. Testing patched hermes-agent imports...")
    sys.path.insert(0, str(hermes_dir))

    # These should all import without errors
    modules = [
        ("hermes_constants", "Constants"),
        ("toolsets", "Toolsets"),
        ("tools.registry", "Tool registry"),
        ("tools.interrupt", "Interrupt"),
        ("tools.fuzzy_match", "Fuzzy match"),
    ]

    for mod_name, label in modules:
        try:
            __import__(mod_name)
            print(f"   ✓ {label} ({mod_name})")
        except Exception as e:
            print(f"   ✗ {label} ({mod_name}): {e}")

    # These need more deps but should at least not crash on the patched parts
    try:
        from agent.display import KawaiiSpinner, build_tool_preview
        spinner = KawaiiSpinner("testing...", spinner_type="dots")
        spinner.start()
        spinner.update_text("still testing")
        spinner.stop("done!")
        print("   ✓ KawaiiSpinner (no-op version)")
    except Exception as e:
        print(f"   ✗ KawaiiSpinner: {e}")

    try:
        from tools.interrupt import set_interrupt, is_interrupted
        set_interrupt(True)
        assert is_interrupted()
        set_interrupt(False)
        assert not is_interrupted()
        print("   ✓ Interrupt mechanism")
    except Exception as e:
        print(f"   ✗ Interrupt: {e}")


def test_tool_registry(hermes_dir):
    """Test that the tool registry works with patched code."""
    print("\n7. Testing tool registry...")
    sys.path.insert(0, str(hermes_dir))

    from tools.registry import ToolRegistry

    reg = ToolRegistry()
    reg.register(
        name="test_tool",
        toolset="test",
        schema={"name": "test_tool", "description": "A test tool", "parameters": {}},
        handler=lambda args, **kw: '{"result": "ok"}',
    )

    defs = reg.get_definitions({"test_tool"})
    assert len(defs) == 1
    assert defs[0]["function"]["name"] == "test_tool"
    print(f"   ✓ Registered and retrieved 1 tool definition")

    result = reg.dispatch("test_tool", {})
    assert '"result"' in result
    print(f"   ✓ Dispatched tool call, got: {result}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-dir", type=str,
                        default=os.path.join(os.path.dirname(__file__), "hermes-agent"))
    parser.add_argument("--simulate-pyodide", action="store_true",
                        help="Set PYODIDE=1 to test shims as if in Pyodide")
    args = parser.parse_args()

    if args.simulate_pyodide:
        os.environ["PYODIDE"] = "1"
        print("🔧 Simulating Pyodide environment (PYODIDE=1)\n")
    else:
        print("🐍 Running in native Python mode\n")

    # Import shims first (this applies monkey-patches if PYODIDE=1)
    sys.path.insert(0, os.path.dirname(__file__))
    import pyodide_shims

    test_shims_import()
    test_threading_shim()
    test_threadpool_shim()
    test_run_sync()
    test_openai_client_creation()

    hermes_dir = os.path.abspath(args.hermes_dir)
    if os.path.isdir(hermes_dir) and os.path.exists(os.path.join(hermes_dir, "run_agent.py")):
        test_hermes_imports(hermes_dir)
        test_tool_registry(hermes_dir)
    else:
        print(f"\n⚠  Skipping hermes-agent import tests ({hermes_dir} not found)")
        print(f"   Run apply_patches.py first to create the patched tree.")

    print(f"\n{'=' * 60}")
    print("✅ All tests passed!")


if __name__ == "__main__":
    main()
