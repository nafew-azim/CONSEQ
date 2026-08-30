"""Repository paths, resolved from this file rather than the working directory.

Entry points under pipeline/ and analysis/ import this first so that they run correctly
from anywhere in the tree.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTRUMENT = os.path.join(ROOT, "instrument")
DATA = os.path.join(ROOT, "data")
RUNS = os.path.join(DATA, "runs")
RELEASE = os.path.join(DATA, "conseq.jsonl")
MANIFEST = os.path.join(DATA, "conseq_manifest.json")
FIGURES = os.path.join(ROOT, "analysis", "figures")

if INSTRUMENT not in sys.path:
    sys.path.insert(0, INSTRUMENT)


def require_release():
    """The release ships gzipped so the repository stays small."""
    if os.path.exists(RELEASE):
        return RELEASE
    gz = RELEASE + ".gz"
    if os.path.exists(gz):
        sys.exit(f"{RELEASE} not found. Decompress it first:\n"
                 f"    gunzip -k {os.path.relpath(gz, os.getcwd())}")
    sys.exit(f"{RELEASE} not found, and neither is {gz}. "
             f"Rebuild it with: python3 pipeline/assemble.py")
