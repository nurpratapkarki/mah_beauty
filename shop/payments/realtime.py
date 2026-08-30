"""Real-time FonePay payment monitoring over the merchant WebSocket.

FonePay's dynamic-QR flow exposes a ``thirdpartyQrWebSocketUrl`` on the QR
initiation response. The application (not the customer's browser) opens a
client WebSocket to that URL and receives ``transactionStatus`` messages as the
customer scans and pays. This module bridges that socket to the order model so
orders are confirmed automatically the moment ``paymentSuccess`` arrives — no
frontend polling required.

The flow is a belt-and-suspenders design: on ``paymentSuccess`` we cross-check
against the ``thirdPartyDynamicQrGetStatus`` REST endpoint before confirming
the order, exactly as the reference implementation recommends. A timeout closes
the socket so abandoned payments do not leak threads.
"""

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field

import websockets

from .errors import FonepayConfigurationError, FonepayUpstreamError

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15 * 60  # mirror the reference's 15-minute timeout


def _is_valid_ws_url(url: str) -> bool:
    """True if ``url`` is a well-formed ws:// or wss:// WebSocket URL."""
    if not url or not isinstance(url, str):
        return False
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        return parts.scheme in {"ws", "wss"} and bool(parts.netloc)
    except ValueError:
        return False


@dataclass
class TransactionStatus:
    """Structured view of a parsed FonePay WebSocket transactionStatus message."""

    raw: str = ""
    qr_verified: bool = False
    payment_success: bool | None = None
    cancelled: bool = False
    message: str = ""
    remarks1: str = ""
    amount: str = ""
    additional: dict = field(default_factory=dict)


def parse_transaction_status(message: str) -> TransactionStatus:
    """Parse a FonePay WebSocket text message into a TransactionStatus.

    The payload is a JSON object with a ``transactionStatus`` field that is
    itself a JSON-encoded string (or object) holding the real status fields.
    """
    status = TransactionStatus(raw=message)
    try:
        root = json.loads(message)
    except (ValueError, TypeError):
        logger.warning("FonePay WS message is not valid JSON: %r", message[:200])
        return status

    tx = root.get("transactionStatus")
    if isinstance(tx, str):
        try:
            tx = json.loads(tx)
        except (ValueError, TypeError):
            tx = None
    if not isinstance(tx, dict):
        logger.warning("FonePay WS message missing transactionStatus: %r", message[:200])
        return status

    status.qr_verified = bool(tx.get("qrVerified", False))
    ps = tx.get("paymentSuccess")
    if ps is not None:
        status.payment_success = bool(ps)
    status.cancelled = bool(tx.get("cancelled", False))
    status.message = tx.get("message") or ""
    status.remarks1 = tx.get("remarks1") or ""
    status.amount = str(tx.get("amount") or "")
    status.additional = tx
    return status


class FonepayRealtimeMonitor:
    """Opens a FonePay WebSocket per order and confirms the order in real time.

    One instance manages a single PRN's socket via a background daemon thread
    running its own asyncio event loop. Recognised terminal states
    (payment success / cancellation / failure) close the socket; the timeout
    guards against the customer never paying.
    """

    def __init__(self, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS):
        self.timeout_seconds = timeout_seconds
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self, order_id, prn: str, websocket_url: str) -> None:
        """Start monitoring in a background thread. This is non-blocking and
        returns immediately so the HTTP request that generated the QR can
        respond to the customer. A missing or unsupported WebSocket URL
        silently short-circuits to the polling fallback (no thread is spawned).
        """
        if not _is_valid_ws_url(websocket_url):
            logger.warning(
                "Invalid/missing WebSocket URL for order %s; relying on polling.",
                order_id,
            )
            return

        async def _run():
            self._loop = asyncio.get_running_loop()
            task = asyncio.create_task(self._monitor(order_id, prn, websocket_url))
            try:
                await task
            except Exception:
                logger.exception(
                    "FonePay realtime monitor crashed for order %s (prn=%s)", order_id, prn
                )

        self._thread = threading.Thread(
            target=lambda: asyncio.run(_run()), daemon=True, name=f"fonepay-ws-{prn}"
        )
        self._thread.start()

    async def _monitor(self, order_id, prn: str, websocket_url: str) -> None:
        """Open the socket, listen for messages, and confirm/cancel the order."""
        if not websocket_url:
            logger.info("No WebSocket URL for order %s; relying on polling.", order_id)
            return
        try:
            # Short TCP/TLS connect timeout; the overall watch window (including
            # the full listen loop) is enforced separately by _listen.
            async with websockets.connect(websocket_url, open_timeout=30) as ws:
                logger.info(
                    "FonePay WS connected for order %s (prn=%s)", order_id, prn
                )
                await self._listen(ws, order_id, prn)
        except asyncio.TimeoutError:
            logger.warning(
                "FonePay WS timeout for order %s (prn=%s); rely on polling.", order_id, prn
            )
        except websockets.exceptions.WebSocketException as exc:
            logger.warning(
                "FonePay WS closed abnormally for order %s (prn=%s): %s",
                order_id, prn, exc,
            )

    async def _listen(self, ws, order_id, prn: str) -> None:
        """Read and dispatch WebSocket messages, capped by the overall timeout."""
        async def _read():
            async for raw in ws:
                status = parse_transaction_status(raw)
                if status.payment_success:
                    await self._on_success(order_id, prn, status)
                    return
                if status.cancelled:
                    await self._on_cancelled(order_id, prn, status)
                    return
                if status.payment_success is False:
                    await self._on_failed(order_id, prn, status)
                    return
                # Mid-flow updates (e.g. qr_verified only) — keep listening.

        await asyncio.wait_for(_read(), timeout=self.timeout_seconds)

    async def _on_success(self, order_id, prn: str, status: TransactionStatus) -> None:
        result = await asyncio.to_thread(self._confirm_order, order_id, prn)
        logger.info("FonePay payment success processed for order %s: %s", order_id, result)

    def _confirm_order(self, order_id, prn: str) -> str:
        """Synchronous helper (runs off the event loop) that confirms the order."""
        from .fonepay import get_client, confirm_paid_order, PENDING
        from ..models import Order

        order = Order.objects.filter(pk=order_id).first()
        if order is None:
            logger.warning("FonePay WS success for unknown order %s", order_id)
            return "unknown order"
        if order.is_paid:
            return "already paid"

        client = get_client()
        try:
            status_json = client.check_status(prn)
        except (FonepayUpstreamError, FonepayConfigurationError) as exc:
            logger.warning("WS cross-check failed for order %s: %s", order_id, exc)
            status_json = {}

        if client.is_paid_status(status_json):
            confirm_paid_order(order, status_json)
            return "confirmed"
        # WebSocket said success but the REST cross-check disagreed — do not
        # confirm on flaky evidence; leave pending for a later poll.
        order.payment_status = PENDING
        order.save(update_fields=["payment_status"])
        return "cross-check pending"

    async def _on_cancelled(self, order_id, prn: str, status: TransactionStatus) -> None:
        await asyncio.to_thread(self._record_cancelled, order_id)

    def _record_cancelled(self, order_id) -> None:
        from ..models import Order

        Order.objects.filter(pk=order_id).update(payment_status="cancelled")

    async def _on_failed(self, order_id, prn: str, status: TransactionStatus) -> None:
        await asyncio.to_thread(self._record_failed, order_id)

    def _record_failed(self, order_id) -> None:
        from ..models import Order

        Order.objects.filter(pk=order_id).update(payment_status="failed")

    def join(self, timeout: float | None = None) -> None:
        """Block until the background thread finishes (mainly for tests)."""
        if self._thread is not None:
            self._thread.join(timeout)
