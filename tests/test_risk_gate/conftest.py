from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from trifolium.risk_gate.config import RISK_LIMITS, RiskLimits
from trifolium.risk_gate.state import reset_state
from trifolium.risk_gate.types import AccountSnapshot, OrderRequest, PositionSnapshot


@pytest.fixture(autouse=True)
def clean_gate_state() -> None:
    reset_state()


@pytest.fixture
def production_limits() -> RiskLimits:
    return RISK_LIMITS.model_copy(update={"mode": "production"})


@pytest.fixture
def account() -> AccountSnapshot:
    return AccountSnapshot(equity=Decimal("1000000"), margin_level_pct=Decimal("1000"))


@pytest.fixture
def make_request(account: AccountSnapshot):
    def _make_request(**overrides: object) -> OrderRequest:
        data = {
            "symbol": "AUDUSD",
            "side": "buy",
            "lots": Decimal("0.01"),
            "price": Decimal("0.7000"),
            "contract_size": Decimal("100000"),
            "strategy_notional": Decimal("700"),
            "timestamp": datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc),
            "account": account,
            "existing_positions": [],
        }
        data.update(overrides)
        return OrderRequest(**data)

    return _make_request


@pytest.fixture
def position_factory():
    def _position(symbol: str, signed_lots: str, price: str, contract_size: str = "100000") -> PositionSnapshot:
        return PositionSnapshot(
            symbol=symbol,
            signed_lots=Decimal(signed_lots),
            price=Decimal(price),
            contract_size=Decimal(contract_size),
        )

    return _position
