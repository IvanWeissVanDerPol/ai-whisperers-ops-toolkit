#!/usr/bin/env python3
"""
gh_actions_generator.py — Atlas J-1: Generate GitHub Actions workflow from project metadata.

Auto-detects project type (Node, Python, etc.) and generates a CI workflow that:
  - Installs dependencies
  - Runs linter
  - Runs tests
  - Builds the project

Detects via:
  - package.json → Node + npm/yarn/pnpm
  - pyproject.toml / requirements.txt / setup.py → Python + pip/poetry
  - Makefile → make
  - Cargo.toml → Rust
  - go.mod → Go

Output goes to .github/workflows/ci.yml (or stdout).

Usage:
  python3 gh_actions_generator.py --path /path/to/project
  python3 gh_actions_generator.py --path . --output .github/workflows/ci.yml
  python3 gh_actions_generator.py --detect        # JSON detect info, no workflow
  python3 gh_actions_generator.py --matrix        # include a test matrix (Python versions)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Standard Node workflow
NODE_TEMPLATE = """name: CI

on:
  push:
    branches: [main, master, develop]
  pull_request:
    branches: [main, master, develop]

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      - run: npm ci || npm install
      - run: npm run lint --if-present
      - run: npm test --if-present
      - run: npm run build --if-present
"""

# Python workflow (with optional matrix)
def python_template(matrix: bool) -> str:
    matrix_block = ""
    if matrix:
        matrix_block = """    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']
"""
    return f"""name: CI

on:
  push:
    branches: [main, master, develop]
  pull_request:
    branches: [main, master, develop]

jobs:
  build:
    runs-on: ubuntu-latest
{matrix_block}    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{{{ matrix.python-version if matrix else '3.11' }}}}
          cache: 'pip'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt || pip install -e .
      - name: Lint
        run: |
          pip install ruff || true
          ruff check . || true
      - name: Test
        run: |
          pip install pytest || true
          pytest || true
"""


RUST_TEMPLATE = """name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - uses: Swatinem/rust-cache@v2
      - run: cargo build --verbose
      - run: cargo test --verbose
      - run: cargo clippy -- -D warnings || true
"""


GO_TEMPLATE = """name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
          cache: true
      - run: go build ./...
      - run: go test ./...
"""


def detect_project(path: Path) -> dict:
    """Detect project type and metadata."""
    info = {
        "path": str(path),
        "type": "unknown",
        "tools": [],
        "lint_command": None,
        "test_command": None,
        "build_command": None,
    }

    # Node
    if (path / "package.json").exists():
        info["type"] = "node"
        info["tools"].append("npm")
        # Detect lockfile
        if (path / "pnpm-lock.yaml").exists():
            info["tools"].append("pnpm")
        elif (path / "yarn.lock").exists():
            info["tools"].append("yarn")
        else:
            info["tools"].append("npm")
        # Parse package.json for scripts
        try:
            pkg = json.loads((path / "package.json").read_text())
            scripts = pkg.get("scripts", {})
            if "lint" in scripts:
                info["lint_command"] = "npm run lint"
            if "test" in scripts:
                info["test_command"] = "npm test"
            if "build" in scripts:
                info["build_command"] = "npm run build"
        except Exception:
            pass

    # Python
    elif (path / "pyproject.toml").exists() or (path / "requirements.txt").exists() or (path / "setup.py").exists():
        info["type"] = "python"
        info["tools"].append("pip")
        if (path / "pyproject.toml").exists():
            try:
                content = (path / "pyproject.toml").read_text()
                if "poetry" in content or "[tool.poetry]" in content:
                    info["tools"].append("poetry")
            except Exception:
                pass
        if (path / "ruff.toml").exists() or (path / ".ruff.toml").exists():
            info["lint_command"] = "ruff check ."
        if (path / "pytest.ini").exists() or (path / "tests").exists() or (path / "test").exists():
            info["test_command"] = "pytest"

    # Rust
    elif (path / "Cargo.toml").exists():
        info["type"] = "rust"
        info["tools"].append("cargo")
        info["build_command"] = "cargo build"
        info["test_command"] = "cargo test"
        info["lint_command"] = "cargo clippy -- -D warnings || true"

    # Go
    elif (path / "go.mod").exists():
        info["type"] = "go"
        info["tools"].append("go")
        info["build_command"] = "go build ./..."
        info["test_command"] = "go test ./..."

    # Make
    elif (path / "Makefile").exists():
        info["type"] = "make"
        info["tools"].append("make")
        info["build_command"] = "make"
        info["test_command"] = "make test"
        info["lint_command"] = "make lint"

    return info


def generate_workflow(project_info: dict, matrix: bool = False) -> str:
    """Generate a GitHub Actions workflow YAML based on project type."""
    ptype = project_info["type"]
    if ptype == "node":
        return NODE_TEMPLATE
    elif ptype == "python":
        return python_template(matrix)
    elif ptype == "rust":
        return RUST_TEMPLATE
    elif ptype == "go":
        return GO_TEMPLATE
    elif ptype == "make":
        return f"""name: CI

on:
  push:
    branches: [main, master]
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make
      - run: make test || true
"""
    else:
        return """# Unable to detect project type. Add explicit CI config.
name: CI

on:
  push:
    branches: [main, master]
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo "No project type detected. Add CI manually."
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--path", default=".", help="Project path")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    parser.add_argument("--detect", action="store_true", help="Only detect, don't generate")
    parser.add_argument("--matrix", action="store_true", help="Include test matrix (Python)")
    parser.add_argument("--json", action="store_true", help="JSON output for detect")
    args = parser.parse_args()

    project_path = Path(args.path).resolve()
    if not project_path.exists():
        print(f"Error: {project_path} does not exist", file=sys.stderr)
        return 1

    info = detect_project(project_path)

    if args.detect:
        if args.json:
            print(json.dumps(info, indent=2))
        else:
            print(f"Project: {info['path']}")
            print(f"Type: {info['type']}")
            print(f"Tools: {', '.join(info['tools'])}")
            print(f"Lint:   {info['lint_command'] or '(none detected)'}")
            print(f"Test:   {info['test_command'] or '(none detected)'}")
            print(f"Build:  {info['build_command'] or '(none detected)'}")
        return 0

    workflow = generate_workflow(info, matrix=args.matrix)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(workflow)
        print(f"✓ Wrote workflow to {out_path}")
        print(f"  Detected project type: {info['type']}")
    else:
        print(workflow)

    return 0


if __name__ == "__main__":
    sys.exit(main())
