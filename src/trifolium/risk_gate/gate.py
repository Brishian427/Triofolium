"""Risk Gate public orchestration entrypoint."""

from __future__ import annotations

from collections.abc import Callable

from trifolium.adapter.types import OrderExecutionResult
from trifolium.risk_gate.checks.account_health import check_account_health
from trifolium.risk_gate.checks.direction_sanity import check_direction_sanity
from trifolium.risk_gate.checks.hard_floor_drawdown import check_hard_floor_drawdown
from trifolium.risk_gate.checks.lot_size import check_lot_size
from trifolium.risk_gate.checks.numeric_consistency import check_numeric_consistency
from trifolium.risk_gate.checks.rate_limit import check_rate_limit
from trifolium.risk_gate.checks.single_symbol_concentration import check_single_symbol_concentration
from trifolium.risk_gate.checks.total_leverage import check_total_leverage
from trifolium.risk_gate.execution import send_order_to_mt5
from trifolium.risk_gate.logging import log_order_result
from trifolium.risk_gate.types import CheckResult, OrderRequest, OrderResult


CheckFn = Callable[[OrderRequest], tuple[bool, str | None]]


CHECKS: list[tuple[str, CheckFn]] = [
    ("check_lot_size", check_lot_size),
    ("check_numeric_consistency", check_numeric_consistency),
    ("check_total_leverage", check_total_leverage),
    ("check_single_symbol_concentration", check_single_symbol_concentration),
    ("check_rate_limit", check_rate_limit),
    ("check_direction_sanity", check_direction_sanity),
    ("check_account_health", check_account_health),
    ("check_hard_floor_drawdown", check_hard_floor_drawdown),
]


def _failure_reason(name: str, detail: str | None) -> str:
    if detail is None:
        return name
    return detail if detail.startswith(f"{name}:") else f"{name}: {detail}"


def submit_order(
    request: OrderRequest,
) -> OrderResult:
    """Submit an order request through the Risk Gate.

    Checks are ordered deliberately: cheap local checks first
    (`lot_size`, `numeric_consistency`), projected-account math next
    (`total_leverage`, `single_symbol_concentration`), stateful local checks
    after that (`rate_limit`, `direction_sanity`), and expensive/account-health
    hard-floor checks last. Any returned failure or raised exception rejects the
    order and prevents the MT5 sender from being called.
    """

    check_results: list[CheckResult] = []
    for name, check in CHECKS:
        try:
            passed, detail = check(request)
        except Exception as exc:
            reason = f"check_error: {name}: {type(exc).__name__}: {exc}"
            result = OrderResult(
                status="rejected",
                reason=reason,
                request=request,
                checks=check_results + [CheckResult(name=name, passed=False, reason=reason)],
            )
            log_order_result(result)
            return result
        check_result = CheckResult(name=name, passed=passed, reason=detail)
        check_results.append(check_result)
        if not passed:
            reason = _failure_reason(name, detail)
            result = OrderResult(status="rejected", reason=reason, request=request, checks=check_results)
            log_order_result(result)
            return result

    try:
        execution = send_order_to_mt5(request)
    except Exception as exc:
        reason = f"mt5_send_error: {type(exc).__name__}: {exc}"
        result = OrderResult(status="error", reason=reason, request=request, checks=check_results)
        log_order_result(result)
        return result

    result = OrderResult(
        status=execution.status,
        reason=execution.comment,
        request=request,
        checks=check_results,
        mt5_response=execution.model_dump(mode="python"),
    )
    log_order_result(result)
    return result
