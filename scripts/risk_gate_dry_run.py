"""Run 20 synthetic Risk Gate order requests with a mocked MT5 sender."""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trifolium.adapter.types import OrderExecutionResult
from trifolium.risk_gate import gate
from trifolium.risk_gate.state import reset_state
from trifolium.risk_gate.types import AccountSnapshot, OrderRequest, PositionSnapshot


@dataclass(frozen=True)
class DryRunCase:
    name: str
    request: OrderRequest
    expected_status: str
    expected_reason_prefix: str | None = None
    reset_before: bool = True


def account(equity: str = "1000000", margin_level: str = "1000") -> AccountSnapshot:
    return AccountSnapshot(equity=Decimal(equity), margin_level_pct=Decimal(margin_level), leverage=Decimal("30"))


def request(
    *,
    symbol: str = "AUDUSD",
    side: str = "buy",
    lots: str = "0.01",
    price: str = "0.7000",
    contract_size: str = "100000",
    strategy_notional: str | None = None,
    timestamp: datetime | None = None,
    existing_positions: list[PositionSnapshot] | None = None,
    account_snapshot: AccountSnapshot | None = None,
) -> OrderRequest:
    lots_d = Decimal(lots)
    price_d = Decimal(price)
    contract_d = Decimal(contract_size)
    notional = Decimal(strategy_notional) if strategy_notional is not None else abs(lots_d * price_d * contract_d)
    return OrderRequest(
        symbol=symbol,
        side=side,  # type: ignore[arg-type]
        lots=lots_d,
        price=price_d,
        contract_size=contract_d,
        strategy_notional=notional,
        timestamp=timestamp or datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc),
        account=account_snapshot or account(),
        existing_positions=existing_positions or [],
        comment="risk_gate_dry_run",
    )


def high_leverage_positions() -> list[PositionSnapshot]:
    return [
        PositionSnapshot(symbol="XAUUSD", signed_lots=Decimal("1.0"), price=Decimal("2300"), contract_size=Decimal("100")),
    ]


def build_cases() -> list[DryRunCase]:
    base = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    cases: list[DryRunCase] = []
    for index in range(5):
        cases.append(DryRunCase(f"legitimate_{index + 1}", request(timestamp=base + timedelta(minutes=index)), "filled"))
    for index in range(3):
        cases.append(
            DryRunCase(
                f"oversize_{index + 1}",
                request(lots="0.5", strategy_notional="35000", timestamp=base + timedelta(minutes=10 + index)),
                "rejected",
                "check_lot_size",
            )
        )
    for index in range(3):
        cases.append(
            DryRunCase(
                f"bypass_leverage_{index + 1}",
                request(
                    symbol="XAUUSD",
                    lots="0.01",
                    price="2300",
                    contract_size="100",
                    existing_positions=high_leverage_positions(),
                    account_snapshot=account(equity="10000"),
                    timestamp=base + timedelta(minutes=20 + index),
                ),
                "rejected",
                "check_total_leverage",
            )
        )
    for index in range(3):
        cases.append(
            DryRunCase(
                f"float_drift_{index + 1}",
                request(price="1", strategy_notional="10000", timestamp=base + timedelta(minutes=30 + index)),
                "rejected",
                "check_numeric_consistency",
            )
        )
    rapid_start = base + timedelta(minutes=40)
    cases.extend(
        [
            DryRunCase("rapid_fire_1", request(timestamp=rapid_start), "filled", reset_before=True),
            DryRunCase("rapid_fire_2", request(timestamp=rapid_start + timedelta(seconds=1)), "filled", reset_before=False),
            DryRunCase("rapid_fire_3", request(timestamp=rapid_start + timedelta(seconds=2)), "filled", reset_before=False),
            DryRunCase(
                "rapid_fire_4",
                request(timestamp=rapid_start + timedelta(seconds=3)),
                "rejected",
                "check_rate_limit",
                reset_before=False,
            ),
        ]
    )
    for index in range(2):
        cases.append(
            DryRunCase(
                f"depleted_account_{index + 1}",
                request(account_snapshot=account(equity="1000000", margin_level="100"), timestamp=base + timedelta(minutes=50 + index)),
                "rejected",
                "check_account_health",
            )
        )
    assert len(cases) == 20
    return cases


def fake_sender(order_request: OrderRequest) -> OrderExecutionResult:
    return OrderExecutionResult(
        status="filled",
        retcode=10009,
        order=9001,
        deal=9002,
        volume=order_request.lots,
        price=order_request.price,
        comment=None,
        raw={"mocked": True},
    )


def main() -> int:
    gate.send_order_to_mt5 = fake_sender
    results = []
    failures = []
    for case in build_cases():
        if case.reset_before:
            reset_state()
        result = gate.submit_order(case.request)
        results.append(result)
        reason_ok = case.expected_reason_prefix is None or (result.reason or "").startswith(case.expected_reason_prefix)
        if result.status != case.expected_status or not reason_ok:
            failures.append((case, result))

    status_counts = Counter(result.status for result in results)
    rejection_breakdown = Counter((result.reason or "filled").split(":", 1)[0] for result in results if result.status == "rejected")
    print("RISK_GATE_DRY_RUN_SUMMARY")
    print(f"total_cases={len(results)}")
    print(f"passed_expectations={len(results) - len(failures)}")
    print(f"failed_expectations={len(failures)}")
    print(f"status_counts={dict(status_counts)}")
    print(f"rejection_breakdown={dict(rejection_breakdown)}")
    if failures:
        for case, result in failures:
            print(f"FAIL case={case.name} expected={case.expected_status}/{case.expected_reason_prefix} actual={result.status}/{result.reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
