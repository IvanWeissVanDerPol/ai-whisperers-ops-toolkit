#!/usr/bin/env python3
"""
swarm/retry.py — Retry policy for failed subtasks.

When a subtask fails, the orchestrator decides what to do:
1. **Retry same role**: simple transient failures (timeout, network blip)
2. **Escalate to reviewer**: harder problem, ask reviewer to diagnose + fix
3. **Skip**: if retry budget exhausted, mark dependents as skipped

Default policy (RetryPolicy.default):
- Each subtask can be retried up to N times with the same role
- After N retries with same role, escalate by adding a reviewer subtask
- After escalation, if still failing, mark failed and skip dependents

This is the core resilience layer that makes the swarm self-healing.

Usage:
    policy = RetryPolicy(max_retries=1, escalate_after=2)
    decision = policy.decide(subtask, attempt_count)
    # decision.action in {"retry", "escalate", "fail"}
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from orchestrator import SubTask, TaskStatus  # noqa: E402


class RetryAction(str, Enum):
    RETRY = "retry"          # Re-run with same role
    ESCALATE = "escalate"    # Add a reviewer subtask to diagnose + fix
    FAIL = "fail"            # Give up, skip dependents


@dataclass
class RetryDecision:
    """What to do with a failed subtask."""
    action: RetryAction
    reason: str
    next_subtask: Optional[SubTask] = None  # Only set if action == "escalate"
    retry_subtask: Optional[SubTask] = None  # The retry version (same role)

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "has_escalation": self.next_subtask is not None,
        }


@dataclass
class RetryPolicy:
    """Configurable retry + escalation policy."""
    max_retries: int = 1            # Retries with same role before escalation
    escalate_after: int = 2          # Total attempts before escalation (counts retries)
    escalate_to: str = "reviewer"    # Role to add on escalation
    timeout_multiplier: float = 1.5  # Multiply timeout on each retry

    @classmethod
    def default(cls) -> "RetryPolicy":
        return cls(max_retries=1, escalate_after=2, escalate_to="reviewer")

    def decide(
        self,
        subtask: SubTask,
        attempt_count: int,
        failure_reason: str = "",
    ) -> RetryDecision:
        """Decide what to do with a failed subtask given attempt count."""
        # First attempt: always retry (with original role)
        if attempt_count < self.max_retries:
            return RetryDecision(
                action=RetryAction.RETRY,
                reason=f"attempt {attempt_count+1} of {self.max_retries}: {failure_reason[:200]}",
                retry_subtask=self._make_retry(subtask, attempt_count),
            )

        # Past retry budget: escalate to reviewer
        if attempt_count < self.escalate_after:
            return RetryDecision(
                action=RetryAction.ESCALATE,
                reason=f"escalating to {self.escalate_to} after {attempt_count} attempts: {failure_reason[:200]}",
                next_subtask=self._make_escalation(subtask, attempt_count),
            )

        # Past escalation budget: give up
        return RetryDecision(
            action=RetryAction.FAIL,
            reason=f"failed after {attempt_count} attempts: {failure_reason[:200]}",
        )

    def _make_retry(self, original: SubTask, attempt_count: int) -> SubTask:
        """Create a retry version of the subtask (same role, more time)."""
        return SubTask(
            id=f"{original.id}-retry-{attempt_count+1}",
            role=original.role,
            description=f"RETRY of '{original.id}': {original.description}",
            depends_on=original.depends_on,
            timeout=int(original.timeout * (self.timeout_multiplier ** (attempt_count + 1))),
            model=original.model,
            extra_context=f"Previous attempt failed. Reason: {getattr(original, 'failure_reason', 'unknown')}",
        )

    def _make_escalation(self, original: SubTask, attempt_count: int) -> SubTask:
        """Create an escalation subtask (different role that diagnoses + fixes)."""
        return SubTask(
            id=f"{original.id}-escalation",
            role=self.escalate_to,
            description=(
                f"ESCALATION: '{original.id}' failed {attempt_count} times. "
                f"Diagnose the root cause and {self._fix_action_for(original.role)} the failure."
            ),
            depends_on=original.depends_on,
            timeout=int(original.timeout * 2),
            model="sonnet",  # Escalation needs stronger reasoning
            extra_context=(
                f"Original task: {original.description}\n"
                f"Failed after {attempt_count} attempts. "
                f"Diagnose why and provide a fix or escalation guidance."
            ),
        )

    @staticmethod
    def _fix_action_for(failed_role: str) -> str:
        """What the reviewer should do based on the failed role."""
        return {
            "coder": "implement a fix or refactor",
            "researcher": "find an alternative source or approach",
            "tester": "adjust the test or skip it",
            "writer": "rewrite the content based on better inputs",
            "reviewer": "explain why this review failed and provide a final verdict",
        }.get(failed_role, "fix the underlying issue")


def should_skip_dependents(subtask: SubTask, plan) -> list[SubTask]:
    """Find subtasks that depend on a failed subtask (and should be skipped)."""
    failed_ids = {subtask.id}
    # Also include any retries/esc subIDs
    for s in plan.subtasks:
        if s.status == TaskStatus.FAILED:
            failed_ids.add(s.id)
    dependents = [
        s for s in plan.subtasks
        if s.status == TaskStatus.PENDING
        and any(d in failed_ids for d in s.depends_on)
    ]
    return dependents


def main():
    """CLI: test retry decisions."""
    import argparse
    p = argparse.ArgumentParser(description="Test retry policy decisions")
    p.add_argument("--role", default="coder")
    p.add_argument("--description", default="Build feature X")
    p.add_argument("--max-retries", type=int, default=1)
    p.add_argument("--escalate-after", type=int, default=2)
    args = p.parse_args()

    policy = RetryPolicy(max_retries=args.max_retries, escalate_after=args.escalate_after)
    subtask = SubTask(id="test", role=args.role, description=args.description, timeout=300)

    print(f"\nPolicy: max_retries={policy.max_retries}, escalate_after={policy.escalate_after}\n")
    for attempt in range(5):
        decision = policy.decide(subtask, attempt, f"simulated failure #{attempt+1}")
        print(f"  attempt {attempt}: {decision.action.value:10} — {decision.reason[:80]}")
        if decision.action == "escalate" and decision.next_subtask:
            print(f"    → escalation subtask: {decision.next_subtask.role} ({decision.next_subtask.id})")


if __name__ == "__main__":
    main()