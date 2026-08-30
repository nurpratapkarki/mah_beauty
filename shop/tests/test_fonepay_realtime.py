import pytest

from shop.payments.fonepay import STATUS_PATH
from shop.payments.realtime import FonepayRealtimeMonitor, _is_valid_ws_url, parse_transaction_status

pytestmark = pytest.mark.django_db


# --- WebSocket URL validation -------------------------------------------------

def test_is_valid_ws_url():
    assert _is_valid_ws_url("wss://ws.fonepay.com/x") is True
    assert _is_valid_ws_url("ws://127.0.0.1:8080/x") is True
    assert _is_valid_ws_url("") is False
    assert _is_valid_ws_url(None) is False
    assert _is_valid_ws_url("https://example.com/x") is False
    assert _is_valid_ws_url("not a url") is False


def test_start_short_circuits_on_invalid_url(order):
    monitor = FonepayRealtimeMonitor()
    monitor.start(str(order.id), "PRN-X", "https://not-ws.example")
    assert monitor._thread is None


def test_start_short_circuits_on_empty_url(order):
    monitor = FonepayRealtimeMonitor()
    monitor.start(str(order.id), "PRN-X", "")
    assert monitor._thread is None


# --- parse_transaction_status -------------------------------------------------

def test_parse_success():
    status = parse_transaction_status(
        '{"transactionStatus": "{\\"qrVerified\\": true, \\"paymentSuccess\\": true, '
        '\\"message\\": \\"Paid\\", \\"amount\\": \\"1500.00\\"}"}'
    )
    assert status.payment_success is True
    assert status.qr_verified is True
    assert status.message == "Paid"
    assert status.amount == "1500.00"


def test_parse_object_transaction_status():
    status = parse_transaction_status(
        '{"transactionStatus": {"qrVerified": true, "paymentSuccess": false}}'
    )
    assert status.payment_success is False
    assert status.qr_verified is True


def test_parse_cancelled():
    status = parse_transaction_status(
        '{"transactionStatus": "{\\"cancelled\\": true, \\"message\\": \\"User\\"}"}'
    )
    assert status.cancelled is True
    assert status.message == "User"


def test_parse_qr_verified_only():
    status = parse_transaction_status(
        '{"transactionStatus": "{\\"qrVerified\\": true}"}'
    )
    assert status.qr_verified is True
    assert status.payment_success is None
    assert status.cancelled is False


def test_parse_malformed():
    assert parse_transaction_status("not-json").payment_success is None
    assert parse_transaction_status('{"nope": 1}').payment_success is None


# --- monitor cross-check / confirm --------------------------------------------

def test_confirm_order_success(fonepay_settings, order, requests_mock):
    requests_mock.post(
        f"{fonepay_settings.FONEPAY_BASE_URL}{STATUS_PATH}",
        json={"prn": "PRN-1", "paymentStatus": "COMPLETED", "fonepayTraceId": "trace-99"},
    )
    monitor = FonepayRealtimeMonitor()
    result = monitor._confirm_order(str(order.id), "PRN-1")
    assert result == "confirmed"
    order.refresh_from_db()
    assert order.is_paid is True
    assert order.status == "confirmed"
    assert order.gateway_reference == "trace-99"


def test_confirm_order_crosscheck_disagrees(fonepay_settings, order, requests_mock):
    requests_mock.post(
        f"{fonepay_settings.FONEPAY_BASE_URL}{STATUS_PATH}",
        json={"prn": "PRN-1", "paymentStatus": "PENDING"},
    )
    monitor = FonepayRealtimeMonitor()
    result = monitor._confirm_order(str(order.id), "PRN-1")
    assert result == "cross-check pending"
    order.refresh_from_db()
    assert order.is_paid is False
    assert order.payment_status == "pending"


def test_confirm_order_crosscheck_upstream_failure(fonepay_settings, order, requests_mock):
    requests_mock.post(
        f"{fonepay_settings.FONEPAY_BASE_URL}{STATUS_PATH}", status_code=500
    )
    monitor = FonepayRealtimeMonitor()
    result = monitor._confirm_order(str(order.id), "PRN-1")
    assert result == "cross-check pending"
    order.refresh_from_db()
    assert order.is_paid is False


def test_confirm_order_unknown(fonepay_settings):
    monitor = FonepayRealtimeMonitor()
    result = monitor._confirm_order("00000000-0000-0000-0000-000000000000", "PRN-1")
    assert result == "unknown order"


def test_confirm_order_already_paid(fonepay_settings, order):
    order.mark_fonepay_confirmed(gateway_reference="existing")
    monitor = FonepayRealtimeMonitor()
    assert monitor._confirm_order(str(order.id), "PRN-1") == "already paid"


# --- end-to-end: real in-process WebSocket server ------------------------------

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_monitor_confirms_order_via_websocket(fonepay_settings, order, requests_mock):
    import asyncio
    import json
    import socket

    import websockets

    def read_is_paid():
        order.refresh_from_db()
        return (order.is_paid, order.status)

    requests_mock.post(
        f"{fonepay_settings.FONEPAY_BASE_URL}{STATUS_PATH}",
        json={"prn": "PRN-1", "paymentStatus": "COMPLETED", "fonepayTraceId": "trace-e2e"},
    )

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    success = {
        "transactionStatus": json.dumps(
            {"qrVerified": True, "paymentSuccess": True, "amount": "1500.00"}
        )
    }

    async def handler(ws):
        await ws.send(json.dumps(success))

    async with websockets.serve(handler, "127.0.0.1", port):
        monitor = FonepayRealtimeMonitor(timeout_seconds=10)
        monitor.start(str(order.id), "PRN-1", f"ws://127.0.0.1:{port}")
        is_paid = False
        status = None
        for _ in range(50):
            is_paid, status = await asyncio.to_thread(read_is_paid)
            if is_paid:
                break
            await asyncio.sleep(0.05)
        monitor.join(5)

    assert is_paid is True
    assert status == "confirmed"

