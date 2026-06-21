"""Tests for SLA lifecycle edge cases."""

from __future__ import annotations

from datetime import UTC, datetime

from inv_man_intake.queue.sla import initialize_sla, mark_breach_if_due


def test_mark_breach_if_due_is_idempotent_after_first_breach() -> None:
    sla = initialize_sla(created_at=datetime(2026, 6, 20, 9, 0, tzinfo=UTC))
    first_observed_at = datetime(2026, 6, 21, 0, 1, tzinfo=UTC)
    second_observed_at = datetime(2026, 6, 21, 1, 15, tzinfo=UTC)

    breached = mark_breach_if_due(sla, now=first_observed_at)
    breached_again = mark_breach_if_due(breached, now=second_observed_at)

    assert breached.breached_at == first_observed_at
    assert breached_again == breached
