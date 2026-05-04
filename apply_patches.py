#!/usr/bin/env python3
"""
Apply all Pyodide compatibility patches to a hermes-agent source tree.

Usage:
    python apply_patches.py [--source ~/hdr/hermes-agent] [--dest ~/hdr/hermes-pyodide/hermes-agent]

If --dest is given, copies the source tree first, then patches in place.
If --dest is omitted, patches the source directory in place (dangerous!).
"""

import argparse
import importlib.util
import os
import shutil
import sys
from pathlib import Path


def load_patches_from_file(patch_path: Path) -> list:
    """Import a .patch.py file and return its PATCHES list."""
    spec = importlib.util.spec_from_file_location("patch_mod", str(patch_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "PATCHES", [])


def apply_patch(root: Path, patch: dict) -> bool:
    """Apply a single find-replace patch.  Returns True on success."""
    filepath = root / patch["file"]
    if not filepath.exists():
        print(f"  ✗ File not found: {patch['file']}")
        return False

    content = filepath.read_text()
    find = patch["find"]

    if find not in content:
        # Try normalizing line endings
        find_normalized = find.replace("\r\n", "\n")
        content_normalized = content.replace("\r\n", "\n")
        if find_normalized not in content_normalized:
            print(f"  ✗ Pattern not found in {patch['file']}: {patch['description']}")
            # Show first 80 chars of what we're looking for
            snippet = find[:80].replace('\n', '\\n')
            print(f"    Looking for: {snippet}...")
            return False
        content = content_normalized
        find = find_normalized

    new_content = content.replace(find, patch["replace"], 1)
    filepath.write_text(new_content)
    print(f"  ✓ {patch['description']}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Apply Pyodide patches to hermes-agent")
    parser.add_argument("--source", type=Path,
                        default=Path(__file__).parent.parent / "hermes-agent",
                        help="Path to hermes-agent source tree")
    parser.add_argument("--dest", type=Path, default=None,
                        help="Copy source to dest before patching")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be changed without modifying files")
    args = parser.parse_args()

    source = args.source.resolve()
    if not (source / "run_agent.py").exists():
        print(f"Error: {source} doesn't look like a hermes-agent tree (no run_agent.py)")
        sys.exit(1)

    # Copy if dest specified
    target = source
    if args.dest:
        target = args.dest.resolve()
        if target.exists():
            print(f"Destination {target} already exists.")
            resp = input("Overwrite? [y/N] ").strip().lower()
            if resp != "y":
                print("Aborted.")
                sys.exit(0)
            shutil.rmtree(target)

        print(f"Copying {source} → {target}")
        # Copy only the source files, skip .git, venv, __pycache__, node_modules
        def ignore(dir, files):
            return [f for f in files if f in (
                ".git", "venv", ".venv", "__pycache__", "node_modules",
                ".vers", "hermes_agent.egg-info", "uv.lock", "package-lock.json",
            )]
        shutil.copytree(source, target, ignore=ignore)
        print(f"Copied (excluding .git, venv, __pycache__, node_modules)")

    # Copy pyodide_shims.py into the target tree
    shims_src = Path(__file__).parent / "pyodide_shims.py"
    shims_dst = target / "pyodide_shims.py"
    if not args.dry_run:
        shutil.copy2(shims_src, shims_dst)
        print(f"Copied pyodide_shims.py → {shims_dst}")

    # Load and apply all patches
    patches_dir = Path(__file__).parent / "patches"
    patch_files = sorted(patches_dir.glob("*.patch.py"))

    total = 0
    succeeded = 0
    failed = 0

    for pf in patch_files:
        patches = load_patches_from_file(pf)
        print(f"\n{pf.name} ({len(patches)} patches):")
        for patch in patches:
            total += 1
            if args.dry_run:
                filepath = target / patch["file"]
                if filepath.exists():
                    content = filepath.read_text()
                    found = patch["find"] in content
                    status = "would apply" if found else "PATTERN NOT FOUND"
                else:
                    status = "FILE NOT FOUND"
                print(f"  {'✓' if 'would' in status else '✗'} {patch['description']} [{status}]")
                if "would" in status:
                    succeeded += 1
                else:
                    failed += 1
            else:
                if apply_patch(target, patch):
                    succeeded += 1
                else:
                    failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {succeeded}/{total} patches applied, {failed} failed")

    if failed:
        print(f"\n⚠  {failed} patch(es) failed — check the output above.")
        sys.exit(1)
    else:
        print(f"\n✅ All patches applied successfully!")
        if not args.dry_run:
            print(f"\nPatched tree: {target}")
            print(f"To test:  cd {target} && python -c 'import pyodide_shims; print(\"shims loaded\")'")


if __name__ == "__main__":
    main()
