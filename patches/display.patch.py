"""
Patch instructions for agent/display.py

Replace the threaded KawaiiSpinner with a synchronous no-op version
that still exposes the same class-level constants (face arrays, verbs)
so run_agent.py's random.choice() calls don't break.
"""

PATCHES = [
    {
        "description": "Replace threaded KawaiiSpinner with no-op",
        "file": "agent/display.py",
        "find": "import threading\nimport time",
        "replace": "import time",
    },
    {
        "description": "Replace KawaiiSpinner class body",
        "file": "agent/display.py",
        "find": '''    def __init__(self, message: str = "", spinner_type: str = 'dots'):
        self.message = message
        self.spinner_frames = self.SPINNERS.get(spinner_type, self.SPINNERS['dots'])
        self.running = False
        self.thread = None
        self.frame_idx = 0
        self.start_time = None
        self.last_line_len = 0
        # Capture stdout NOW, before any redirect_stdout(devnull) from
        # child agents can replace sys.stdout with a black hole.
        self._out = sys.stdout

    def _write(self, text: str, end: str = '\\n', flush: bool = False):
        """Write to the stdout captured at spinner creation time."""
        try:
            self._out.write(text + end)
            if flush:
                self._out.flush()
        except (ValueError, OSError):
            pass

    def _animate(self):
        while self.running:
            if os.getenv("HERMES_SPINNER_PAUSE"):
                time.sleep(0.1)
                continue
            frame = self.spinner_frames[self.frame_idx % len(self.spinner_frames)]
            elapsed = time.time() - self.start_time
            line = f"  {frame} {self.message} ({elapsed:.1f}s)"
            pad = max(self.last_line_len - len(line), 0)
            self._write(f"\\r{line}{' ' * pad}", end='', flush=True)
            self.last_line_len = len(line)
            self.frame_idx += 1
            time.sleep(0.12)

    def start(self):
        if self.running:
            return
        self.running = True
        self.start_time = time.time()
        self.thread = threading.Thread(target=self._animate, daemon=True)
        self.thread.start()

    def update_text(self, new_message: str):
        self.message = new_message

    def print_above(self, text: str):
        """Print a line above the spinner without disrupting animation.

        Clears the current spinner line, prints the text, and lets the
        next animation tick redraw the spinner on the line below.
        Thread-safe: uses the captured stdout reference (self._out).
        Works inside redirect_stdout(devnull) because _write bypasses
        sys.stdout and writes to the stdout captured at spinner creation.
        """
        if not self.running:
            self._write(f"  {text}", flush=True)
            return
        # Clear spinner line with spaces (not \\033[K) to avoid garbled escape
        # codes when prompt_toolkit's patch_stdout is active — same approach
        # as stop(). Then print text; spinner redraws on next tick.
        blanks = ' ' * max(self.last_line_len + 5, 40)
        self._write(f"\\r{blanks}\\r  {text}", flush=True)

    def stop(self, final_message: str = None):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)
        # Clear the spinner line with spaces instead of \\033[K to avoid
        # garbled escape codes when prompt_toolkit's patch_stdout is active.
        blanks = ' ' * max(self.last_line_len + 5, 40)
        self._write(f"\\r{blanks}\\r", end='', flush=True)
        if final_message:
            self._write(f"  {final_message}", flush=True)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False''',
        "replace": '''    def __init__(self, message: str = "", spinner_type: str = 'dots'):
        self.message = message
        self.start_time = None

    def start(self):
        self.start_time = time.time()

    def update_text(self, new_message: str):
        self.message = new_message

    def print_above(self, text: str):
        print(f"  {text}", flush=True)

    def stop(self, final_message: str = None):
        if final_message:
            print(f"  {final_message}", flush=True)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False''',
    },
]
