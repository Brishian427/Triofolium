"""Risk Gate package: mandatory order-safety entrypoint before MT5."""

from trifolium.risk_gate.config import RISK_LIMITS
from trifolium.risk_gate.gate import submit_order
from trifolium.risk_gate.types import OrderRequest, OrderResult

__all__ = ["OrderRequest", "OrderResult", "RISK_LIMITS", "submit_order"]
