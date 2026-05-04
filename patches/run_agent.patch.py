"""
Patch instructions for run_agent.py

This file documents the exact changes needed.  The apply_patches.py
script applies them automatically against the hermes-agent source tree.
"""

PATCHES = [
    # ── 1. Add pyodide_shims import near the top ──
    {
        "description": "Import pyodide_shims at the top of run_agent.py",
        "file": "run_agent.py",
        "find": "import copy\nimport hashlib\nimport json",
        "replace": "import copy\nimport hashlib\nimport json\n\n# Pyodide single-thread compatibility\ntry:\n    import pyodide_shims\nexcept ImportError:\n    pass  # running natively, no shims needed",
    },

    # ── 2. Replace _interruptible_api_call with synchronous version ──
    {
        "description": "Remove threading from _interruptible_api_call",
        "file": "run_agent.py",
        "find": '''    def _interruptible_api_call(self, api_kwargs: dict):
        """
        Run the API call in a background thread so the main conversation loop
        can detect interrupts without waiting for the full HTTP round-trip.
        
        On interrupt, closes the HTTP client to cancel the in-flight request
        (stops token generation and avoids wasting money), then rebuilds the
        client for future calls.
        """
        result = {"response": None, "error": None}

        def _call():
            try:
                if self.api_mode == "codex_responses":
                    result["response"] = self._run_codex_stream(api_kwargs)
                else:
                    result["response"] = self.client.chat.completions.create(**api_kwargs)
            except Exception as e:
                result["error"] = e

        t = threading.Thread(target=_call, daemon=True)
        t.start()
        while t.is_alive():
            t.join(timeout=0.3)
            if self._interrupt_requested:
                # Force-close the HTTP connection to stop token generation
                try:
                    self.client.close()
                except Exception:
                    pass
                # Rebuild the client for future calls (cheap, no network)
                try:
                    self.client = OpenAI(**self._client_kwargs)
                except Exception:
                    pass
                raise InterruptedError("Agent interrupted during API call")
        if result["error"] is not None:
            raise result["error"]
        return result["response"]''',
        "replace": '''    def _interruptible_api_call(self, api_kwargs: dict):
        """
        Run the API call synchronously.

        In the original hermes-agent this runs in a background thread so
        interrupts can cancel in-flight requests.  In the Pyodide build
        there's only one thread, so we call directly.  Interrupts are
        checked before and after (not during) the API call.
        """
        if self._interrupt_requested:
            raise InterruptedError("Agent interrupted before API call")

        try:
            if self.api_mode == "codex_responses":
                return self._run_codex_stream(api_kwargs)
            else:
                return self.client.chat.completions.create(**api_kwargs)
        except Exception:
            if self._interrupt_requested:
                raise InterruptedError("Agent interrupted during API call")
            raise''',
    },
]
