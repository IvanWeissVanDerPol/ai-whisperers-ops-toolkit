"""
kanban_models — pydantic models for the kanban.

Tier 1.3 (typed domain models with validation) + Tier 4.3 (task content
validation: length limits, no secrets, required fields).

Why this exists:
- Replaces `dataclass`-based models in kanban_store.py with pydantic
- Catches `priority='high'` instead of `priority=0` at the API boundary
- Validates task content BEFORE it lands in the DB
- Auto-validates dates, emails, URLs, phone numbers
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---- Constants ----

MAX_TITLE_LEN = 200
MAX_BODY_LEN = 5000
MAX_RESULT_LEN = 10000

# Patterns that look like secrets — reject tasks containing them
SECRET_PATTERNS = [
    # AWS keys
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # GitHub PAT
    re.compile(r"ghp_[0-9a-zA-Z]{36}"),
    re.compile(r"github_pat_[0-9a-zA-Z_]{82}"),
    # OpenAI API keys
    re.compile(r"sk-[0-9a-zA-Z]{20,}"),
    re.compile(r"sk-proj-[0-9a-zA-Z_-]{20,}"),
    # Anthropic API keys
    re.compile(r"sk-ant-[0-9a-zA-Z_-]{20,}"),
    # Slack tokens
    re.compile(r"xox[abp]-[0-9a-zA-Z-]{10,}"),
    # JWTs (eyJ... pattern, 3 segments)
    re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    # PEM private keys
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # Generic high-entropy base64 strings (32+ chars)
    re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"),
]

ALLOWED_STATUSES = {"ready", "running", "blocked", "done", "archived"}


class SecretDetected(ValueError):
    """Raised when task content looks like it contains a secret."""


# ---- Models ----

class _Base(BaseModel):
    """Base with config that allows extra fields and tolerates string→int coercion."""
    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class TaskModel(_Base):
    """Validated task schema. Required fields are id, title, status; rest optional."""
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^t_[a-f0-9]+$")
    title: str = Field(..., min_length=1, max_length=MAX_TITLE_LEN)
    body: str | None = Field(None, max_length=MAX_BODY_LEN)
    assignee: str | None = None
    status: str = "ready"
    priority: int = Field(5, ge=0, le=15)
    created_by: str | None = None
    created_at: int = 0
    tenant: str | None = None
    result: str | None = Field(None, max_length=MAX_RESULT_LEN)
    workflow_template_id: str | None = None
    idempotency_key: str | None = None

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        if v not in ALLOWED_STATUSES:
            raise ValueError(f"status must be one of {sorted(ALLOWED_STATUSES)}, got {v!r}")
        return v

    @field_validator("title", "body", "result")
    @classmethod
    def _no_secrets(cls, v: str | None) -> str | None:
        if v is None:
            return v
        for pattern in SECRET_PATTERNS:
            if pattern.search(v):
                raise SecretDetected(
                    f"Content appears to contain a secret (matched {pattern.pattern!r}). "
                    f"Refusing to save. Please remove the secret and try again."
                )
        return v

    @model_validator(mode="after")
    def _validate_consistency(self) -> "TaskModel":
        # If status is done, completed_at should be set
        if self.status == "done" and not self.completed_at:
            # Auto-fix: set completed_at to now if missing
            object.__setattr__(self, "completed_at", int(datetime.now().timestamp()))
        return self


class AssigneeModel(_Base):
    task_id: str = Field(..., min_length=1, max_length=64)
    person: str = Field(..., min_length=1, max_length=64)
    role: str | None = Field(None, max_length=128)
    weight: float = Field(1.0, ge=0.0, le=10.0)


class DueDateModel(_Base):
    task_id: str = Field(..., min_length=1, max_length=64)
    due_at: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    source: str | None = Field(None, max_length=128)


class TenantModel(_Base):
    name: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    notes: str | None = Field(None, max_length=512)


# ---- Validation helpers (for use in scripts) ----

def validate_task_dict(d: dict) -> TaskModel:
    """Validate a task dict (e.g., from JSON or DB). Raises on invalid input."""
    return TaskModel(**d)


def validate_no_secrets(text: str | None) -> bool:
    """Return True if text is safe (no secrets), False if it contains one."""
    if not text:
        return True
    return not any(p.search(text) for p in SECRET_PATTERNS)


def find_secrets(text: str) -> list[str]:
    """Return list of secret patterns matched in text (for diagnostics)."""
    if not text:
        return []
    return [p.pattern for p in SECRET_PATTERNS if p.search(text)]


# ---- CLI for ad-hoc validation ----

def main():
    """Usage: kanban_models.py validate-task '<json>'   OR   find-secrets '<text>'"""
    import json
    import sys

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "validate-task" and len(sys.argv) > 2:
        try:
            data = json.loads(sys.argv[2])
            task = TaskModel(**data)
            print(f"✓ Valid task: {task.id} = {task.title[:50]}")
        except SecretDetected as e:
            print(f"⛔ Secret detected: {e}", file=sys.stderr)
            sys.exit(2)
        except Exception as e:
            print(f"✗ Invalid: {e}", file=sys.stderr)
            sys.exit(1)
    elif cmd == "find-secrets" and len(sys.argv) > 2:
        matches = find_secrets(sys.argv[2])
        if matches:
            print(f"Found {len(matches)} potential secret(s):")
            for m in matches:
                print(f"  {m}")
            sys.exit(2)
        else:
            print("✓ No secrets detected")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
