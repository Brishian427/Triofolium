"""Equity sampling and Syphonix-style metric computation."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from statistics import mean, pstdev

from trifolium.backtest.executor import Executor
from trifolium.backtest.types import AccountState, EquityPoint


class EquityTracker:
    """Track equity, max drawdown, 15-minute Sharpe, and risk snapshots."""

    def __init__(self, initial_equity: Decimal, executor: Executor) -> None:
        self.initial_equity = initial_equity
        self.executor = executor
        self.points: list[EquityPoint] = []
        self.peak_equity = initial_equity
        self.max_drawdown = Decimal("0")
        self.next_sample_time: datetime | None = None
        self.max_leverage_seen = Decimal("0")
        self.max_concentration_seen = Decimal("0")

    @staticmethod
    def ceil_to_quarter(timestamp: datetime) -> datetime:
        minute = ((timestamp.minute // 15) + 1) * 15
        base = timestamp.replace(second=0, microsecond=0)
        if minute >= 60:
            return base.replace(minute=0) + timedelta(hours=1)
        return base.replace(minute=minute)

    def tick(self, timestamp: datetime, account: AccountState) -> None:
        """Sample equity at every crossed 15-minute boundary."""

        if self.next_sample_time is None:
            self.next_sample_time = self.ceil_to_quarter(timestamp)
        while self.next_sample_time is not None and timestamp >= self.next_sample_time:
            self.sample(self.next_sample_time, account)
            self.next_sample_time += timedelta(minutes=15)

    def sample(self, timestamp: datetime, account: AccountState) -> None:
        self.executor.mark_to_market(account)
        margin_level = self.executor.margin_level(account)
        self.points.append(
            EquityPoint(
                timestamp=timestamp,
                equity=account.equity,
                balance=account.balance,
                margin_used=account.margin_used,
                margin_level=margin_level,
            )
        )
        if account.equity > self.peak_equity:
            self.peak_equity = account.equity
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - account.equity) / self.peak_equity
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown
        self._track_risk(account)

    def _track_risk(self, account: AccountState) -> None:
        if account.equity > 0:
            leverage = account.margin_used * self.executor.leverage / account.equity
            if leverage > self.max_leverage_seen:
                self.max_leverage_seen = leverage
        notionals = []
        for symbol, position in account.positions.items():
            tick = account.latest_ticks.get(symbol)
            mark = tick.mid if tick is not None else position.avg_price
            notionals.append(abs(position.lots) * self.executor.contract_size(symbol) * mark)
        total_abs = sum(notionals, Decimal("0"))
        if total_abs > 0:
            concentration = max(notional / total_abs for notional in notionals)
            if concentration > self.max_concentration_seen:
                self.max_concentration_seen = concentration

    def total_return(self, final_equity: Decimal) -> Decimal:
        return (final_equity - self.initial_equity) / self.initial_equity

    def sharpe(self) -> Decimal | None:
        if len(self.points) < 9:
            return None
        returns: list[float] = []
        for previous, current in zip(self.points, self.points[1:], strict=False):
            if previous.equity == 0:
                continue
            returns.append(float((current.equity - previous.equity) / previous.equity))
        if len(returns) < 8:
            return None
        std = pstdev(returns)
        if std == 0:
            return None
        return Decimal(str(mean(returns) / std))

    def projected_risk_discipline(self, account: AccountState) -> Decimal:
        """Simple projected score: 100 minus penalties for observed red-lines."""

        score = Decimal("100")
        if account.stop_out_events:
            score -= Decimal("100")
        if self.max_leverage_seen > Decimal("28"):
            score -= Decimal("25")
        if self.max_concentration_seen > Decimal("0.40"):
            score -= Decimal("10")
        return max(Decimal("0"), score)
