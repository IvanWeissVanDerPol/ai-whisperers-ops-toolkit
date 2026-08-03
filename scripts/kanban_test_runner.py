"""
kanban_test_runner — runs the test suite from any cwd.

Use this when you want to run tests from a different directory or via a
cron job that doesn't know the test file's location.

Usage:
  python3 ~/.hermes/scripts/kanban_test_runner.py
  python3 ~/.hermes/scripts/kanban_test_runner.py -v
  python3 ~/.hermes/scripts/kanban_test_runner.py --coverage
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
TEST_FILE = SCRIPTS_DIR / "test_kanban_extensions.py"


def main():
    verbose = "-v" in sys.argv
    coverage = "--coverage" in sys.argv

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(SCRIPTS_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    )

    if coverage:
        # Run coverage as a wrapper
        cmd = [
            "coverage", "run",
            "--source=kanban_common,kanban_store,kanban_models,kanban_log_rotate,kanban_doctor",
            "-m", "unittest", "discover",
            "-s", str(SCRIPTS_DIR),
            "-p", "test_kanban_extensions.py",
        ]
    else:
        cmd = [
            "python3", "-m", "unittest",
            "test_kanban_extensions",
        ]
        if verbose:
            cmd.append("-v")

    print(f"Running: {' '.join(cmd)}")
    print(f"PYTHONPATH: {env.get('PYTHONPATH')}")
    print(f"CWD: {os.getcwd()}")
    print("=" * 60)
    r = subprocess.run(cmd, env=env)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
