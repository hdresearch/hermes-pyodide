"""
Patch instructions for hermes_state.py

WAL journal mode doesn't work in Pyodide's wa-sqlite.  Switch to DELETE.
"""

PATCHES = [
    {
        "description": "WAL -> DELETE journal mode for wa-sqlite compatibility",
        "file": "hermes_state.py",
        "find": '        self._conn.execute("PRAGMA journal_mode=WAL")',
        "replace": '        self._conn.execute("PRAGMA journal_mode=DELETE")  # WAL not supported in Pyodide wa-sqlite',
    },
]
