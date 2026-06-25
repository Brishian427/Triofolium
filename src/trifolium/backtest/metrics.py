"""Metric helpers for validation and round simulations."""

from __future__ import annotations

from decimal import Decimal


def final_score_projection(
    return_score: Decimal,
    drawdown_score: Decimal,
    sharpe_score: Decimal,
    risk_discipline_score: Decimal,
) -> Decimal:
    """Compute weighted projected final score from component scores."""

    return (
        Decimal("0.70") * return_score
        + Decimal("0.15") * drawdown_score
        + Decimal("0.10") * sharpe_score
        + Decimal("0.05") * risk_discipline_score
    )


def score_from_metric(value: Decimal, *, higher_is_better: bool = True) -> Decimal:
    """Map a standalone metric to a simple 0-100 projection for offline comparison."""

    if higher_is_better:
        return max(Decimal("0"), min(Decimal("100"), Decimal("50") + value * Decimal("1000")))
    return max(Decimal("0"), min(Decimal("100"), Decimal("100") - value * Decimal("1000")))
