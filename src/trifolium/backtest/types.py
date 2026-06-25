"""Pydantic models used by the offline backtest engine."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Side = Literal["buy", "sell"]
OrderKind = Literal["market", "limit", "stop"]


class Tick(BaseModel):
    """Best bid/ask observation from the historical pricer output."""

    timestamp: datetime
    symbol: str
    bid: Decimal
    ask: Decimal
    volume: Decimal = Decimal("0")

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid


class Bar(BaseModel):
    """OHLCV bar derived from tick data."""

    timestamp: datetime
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    bid: Decimal
    ask: Decimal
    volume: Decimal = Decimal("0")
    spread_pips: Decimal = Decimal("0")


class Order(BaseModel):
    """Strategy order submitted to the simulated executor."""

    symbol: str
    side: Side
    lots: Decimal
    order_type: OrderKind = "market"
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    tag: str | None = None


class Fill(BaseModel):
    """Simulated fill result."""

    timestamp: datetime
    symbol: str
    side: Side
    lots: Decimal
    price: Decimal
    order_type: OrderKind
    realized_pnl: Decimal = Decimal("0")
    tag: str | None = None


class Position(BaseModel):
    """Netting-mode position for one symbol."""

    symbol: str
    lots: Decimal = Decimal("0")
    avg_price: Decimal = Decimal("0")

    @property
    def side(self) -> Side | None:
        if self.lots > 0:
            return "buy"
        if self.lots < 0:
            return "sell"
        return None


class Trade(BaseModel):
    """Trade log row emitted by the engine."""

    timestamp: datetime
    symbol: str
    side: Side
    lots: Decimal
    price: Decimal
    realized_pnl: Decimal
    equity_after: Decimal
    tag: str | None = None


class AccountState(BaseModel):
    """Mutable simulated account state in netting mode."""

    model_config = ConfigDict(validate_assignment=True)

    balance: Decimal = Decimal("1000000")
    equity: Decimal = Decimal("1000000")
    margin_used: Decimal = Decimal("0")
    leverage: Decimal = Decimal("30")
    positions: dict[str, Position] = Field(default_factory=dict)
    latest_ticks: dict[str, Tick] = Field(default_factory=dict)
    market_history: list[Tick] = Field(default_factory=list)
    stop_out_events: list[str] = Field(default_factory=list)
    risk_events: list[str] = Field(default_factory=list)

    def clone_for_strategy(self) -> "AccountState":
        """Return a lightweight copy so strategies cannot mutate engine-owned state."""

        clone = self.model_copy(deep=True)
        clone.market_history = list(self.market_history)
        return clone


class EquityPoint(BaseModel):
    """Equity sample at a point in simulated time."""

    timestamp: datetime
    equity: Decimal
    balance: Decimal
    margin_used: Decimal
    margin_level: Decimal | None


class DataQualityStats(BaseModel):
    """Counts of skipped/corrupt data encountered during streaming."""

    processed_ticks: int = 0
    skipped_ticks: int = 0
    skipped_examples: list[str] = Field(default_factory=list)


class BacktestResult(BaseModel):
    """Output of a backtest run."""

    strategy_name: str
    symbols: list[str]
    start: datetime
    end: datetime
    initial_equity: Decimal
    final_equity: Decimal
    total_return: Decimal
    max_drawdown: Decimal
    sharpe: Decimal | None
    projected_risk_discipline: Decimal
    trade_count: int
    trades: list[Trade]
    equity_curve: list[EquityPoint]
    data_quality: DataQualityStats
    stop_out_events: list[str]
    risk_events: list[str]
