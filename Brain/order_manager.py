"""
Live order manager — wrapper around dhanhq.dhanhq for order execution.

Provides order placement, modification, cancellation, and position/fund queries.
Connects to OrderSocket for async order status updates.
"""
import logging
import threading
from typing import Any, Dict, List, Optional

from dhanhq import dhanhq
from dhanhq.orderupdate import OrderSocket

logger = logging.getLogger("QuantPlatform.LiveOrderManager")


class LiveOrderManager:
    """
    Wraps dhanhq.dhanhq for live order execution on Dhan.

    Methods mirror the PaperBroker interface so LiveExecutor can swap
    between paper and live by changing one reference.

    Exchange segment defaults to NSE_EQ, product type to CNC (delivery).
    """

    def __init__(
        self,
        client_id: str,
        access_token: str,
        security_map: Optional[Dict[str, tuple]] = None,
    ):
        """
        Args:
            client_id: Dhan client ID
            access_token: Dhan access token
            security_map: {symbol: (security_id, instrument_type)} from
                          DataManager.build_security_mapping()
        """
        self._dhan = dhanhq(client_id=client_id, access_token=access_token)
        self._security_map = security_map or {}
        self._order_socket: Optional[OrderSocket] = None
        # In-memory order cache {order_id: status_dict}
        self._orders: Dict[str, dict] = {}
        self._lock = threading.Lock()

    # ── order placement ─────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        action: str,  # "BUY" or "SELL"
        quantity: int,
        price: float,
        order_type: str = "MARKET",
        product_type: str = "CNC",
        after_market: bool = False,
        tag: Optional[str] = None,
    ) -> dict:
        """
        Place an order via dhanhq.place_order().

        Args:
            symbol: Trading symbol (e.g. "RELIANCE")
            action: "BUY" or "SELL"
            quantity: Number of shares
            price: Limit price (ignored for MARKET orders)
            order_type: "MARKET" or "LIMIT"
            product_type: "CNC" (delivery) or "INTRADAY"
            after_market: Place as AMO order
            tag: Optional client tag for order tracking

        Returns:
            dict with keys: status, order_id, remark, etc.
        """
        # Resolve security ID from symbol
        sec_id = self._resolve_security_id(symbol)
        if not sec_id:
            return {"status": "REJECTED", "reason": f"Unknown symbol: {symbol}"}

        transaction_type = "BUY" if action.upper() == "BUY" else "SELL"
        # ponytail: MARKET order by default. Add limit order support if needed.
        dhan_order_type = "MARKET" if order_type.upper() == "MARKET" else "LIMIT"

        result = self._dhan.place_order(
            security_id=sec_id,
            exchange_segment="NSE_EQ",
            transaction_type=transaction_type,
            quantity=quantity,
            order_type=dhan_order_type,
            product_type=product_type,
            price=price if dhan_order_type == "LIMIT" else 0,
            after_market_order=after_market,
            tag=tag,
        )

        # Cache order for status tracking
        order_id = result.get("order_id") or result.get("data", {}).get("orderId")
        if order_id:
            with self._lock:
                self._orders[order_id] = {
                    "symbol": symbol,
                    "action": action,
                    "quantity": quantity,
                    "status": result.get("status", "PENDING"),
                }
            logger.info(
                f"[LIVE] Order placed: {action} {quantity} {symbol} "
                f"(order_id={order_id}, status={result.get('status')})"
            )
        else:
            logger.warning(f"[LIVE] Order placement returned no order_id: {result}")

        return result

    def modify_order(self, order_id: str, **kwargs) -> dict:
        """Modify an existing pending order."""
        result = self._dhan.modify_order(order_id=order_id, **kwargs)
        logger.info(f"Order modified: {order_id} -> {result.get('status')}")
        return result

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a pending order."""
        result = self._dhan.cancel_order(order_id=order_id)
        logger.info(f"Order cancelled: {order_id} -> {result.get('status')}")
        return result

    # ── order status ────────────────────────────────────────────────────

    def get_order_status(self, order_id: str) -> dict:
        """Fetch order status from Dhan."""
        return self._dhan.get_order_by_id(order_id=order_id)

    def get_open_orders(self) -> List[dict]:
        """List all open orders for the day."""
        resp = self._dhan.get_order_list()
        return resp.get("data", []) if isinstance(resp.get("data"), list) else []

    # ── positions & funds ───────────────────────────────────────────────

    def get_positions(self) -> List[dict]:
        """Get current day's open positions from Dhan."""
        resp = self._dhan.get_positions()
        return resp.get("data", []) if isinstance(resp.get("data"), list) else []

    def get_fund_limits(self) -> dict:
        """Get account fund limits (balance, margin, collateral)."""
        return self._dhan.get_fund_limits()

    def get_holdings(self) -> List[dict]:
        """Get holdings from previous sessions (delivery positions)."""
        resp = self._dhan.get_holdings()
        return resp.get("data", []) if isinstance(resp.get("data"), list) else []

    # ── utility ─────────────────────────────────────────────────────────

    def _resolve_security_id(self, symbol: str) -> Optional[str]:
        """Resolve a trading symbol to a Dhan security ID via the injected map."""
        result = self._security_map.get(symbol)
        return result[0] if result else None

    def close(self) -> None:
        """Cleanup (close any open connections)."""
        if self._order_socket:
            try:
                self._order_socket.close_connection()
            except Exception:
                pass
