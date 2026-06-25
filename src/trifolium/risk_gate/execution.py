"""Live MT5 order execution path owned exclusively by Risk Gate."""

from __future__ import annotations

from trifolium.adapter.types import OrderExecutionResult
from trifolium.risk_gate.types import OrderRequest


def send_order_to_mt5(request: OrderRequest) -> OrderExecutionResult:
    """Send an already-approved order to MT5.

    MetaTrader5 and Task 01 adapter normalization are imported lazily so tests
    can exercise Risk Gate orchestration without requiring MT5 to be installed.
    """

    import MetaTrader5 as mt5

    from trifolium.adapter.orders import build_market_order_request, normalize_order_response

    mt5_request = build_market_order_request(request.symbol, request.side, request.lots, request.price, request.comment)
    response = mt5.order_send(mt5_request)
    result = normalize_order_response(response)
    if result.raw is None:
        result.raw = {}
    result.raw["request"] = mt5_request
    return result
