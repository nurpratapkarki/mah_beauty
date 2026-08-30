"""FonePay API views.

FonePay HTTP endpoints live here instead of ``shop/views.py`` so all gatewayspecific request handling stays within ``shop/payments/``. Shared domain logic
(client construction, PRN generation, order confirmation) is centralised in the
sibling ``fonepay.py`` module.
"""

import logging

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import Order
from .errors import FonepayConfigurationError, FonepayError, FonepayUpstreamError
from .fonepay import (
    FAILED, PENDING, SUCCESS, confirm_paid_order, generate_prn, get_client,
    interpret_status, is_fonepay_payment,
)
from .realtime import FonepayRealtimeMonitor

logger = logging.getLogger(__name__)


def _get_order_or_404(order_id):
    try:
        return get_object_or_404(Order, pk=order_id)
    except (ValueError, TypeError):
        raise Http404("Order not found.")


def _client_or_error(request):
    """Build the FonePay client or a friendly error message when unconfigured.

    Returns ``(client, message)``; exactly one of them is non-None.
    """
    try:
        return get_client(), None
    except FonepayConfigurationError as exc:
        logger.error("FonePay not configured: %s", exc)
        return None, "FonePay is not configured."


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def fonepay_generate_qr(request):
    """Generate a FonePay dynamic QR for a valid, unpaid FonePay order."""
    order_id = request.data.get("order_id")
    if not order_id:
        return Response(
            {"error": "order_id is required."}, status=status.HTTP_400_BAD_REQUEST
        )
    order = _get_order_or_404(order_id)

    if not is_fonepay_payment(order):
        return Response(
            {"error": "Order is not a FonePay payment."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if order.is_paid:
        return Response(
            {"error": "Order is already paid."}, status=status.HTTP_400_BAD_REQUEST
        )
    if order.total <= 0:
        return Response(
            {"error": "Order total must be greater than zero."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    client, error_message = _client_or_error(request)
    if error_message is not None:
        return Response(
            {"error": error_message}, status=status.HTTP_502_BAD_GATEWAY
        )

    prn = order.prn or generate_prn(order.id)
    Order.objects.filter(pk=order.pk).update(prn=prn, payment_status="pending")

    try:
        qr_data = client.generate_qr(
            amount=str(order.total),
            prn=prn,
            remarks1=f"Payment for order {order.id}",
            remarks2="Mah Beauty",
        )
    except FonepayUpstreamError as exc:
        logger.warning("FonePay QR generation failed for order %s: %s", order.id, exc)
        Order.objects.filter(pk=order.pk).update(payment_status=FAILED)
        return Response(
            {"success": False, "result": FAILED, "message": "Could not generate the FonePay QR."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except FonepayError as exc:
        logger.error("FonePay error for order %s: %s", order.id, exc)
        return Response(
            {"success": False, "result": FAILED, "message": "Could not generate the FonePay QR."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    logger.info("FonePay QR generated for order %s (prn=%s)", order.id, prn)

    websocket_url = qr_data.get("websocket_url") or ""
    if websocket_url:
        # Kick off real-time payment monitoring in the background. Order is
        # confirmed automatically when FonePay reports payment success.
        FonepayRealtimeMonitor().start(order.id, prn, websocket_url)
        logger.info("FonePay realtime monitoring started for order %s", order.id)

    return Response(
        {
            "success": True,
            "result": PENDING,
            "message": "FonePay QR generated — scan and pay with the FonePay app.",
            "order_id": str(order.id),
            "prn": prn,
            "amount": str(order.total),
            "qr": qr_data["qr"],
            "qr_message": qr_data["qr_message"],
            "realtime": bool(websocket_url),
            "payment_status": "pending",
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def fonepay_check_status(request):
    """Check the FonePay payment status for a PRN and confirm the order idempotently."""
    prn = request.data.get("prn")
    if not prn:
        return Response(
            {"error": "prn is required."}, status=status.HTTP_400_BAD_REQUEST
        )

    order = Order.objects.filter(prn=prn).first()
    if order is None:
        return Response(
            {"error": "No order found for this PRN."}, status=status.HTTP_404_NOT_FOUND
        )

    if order.is_paid and order.status == "confirmed":
        return Response(
            {
                "success": True,
                "result": SUCCESS,
                "message": "Payment successful",
                "prn": prn,
                "payment_status": order.payment_status or "COMPLETED",
                "is_paid": True,
                "order_status": order.status,
                "gateway_reference": order.gateway_reference,
            },
            status=status.HTTP_200_OK,
        )

    client, error_message = _client_or_error(request)
    if error_message is not None:
        return Response(
            {"success": False, "result": FAILED, "message": error_message},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        status_json = client.check_status(prn)
    except FonepayError as exc:
        logger.error("FonePay status check failed for prn %s: %s", prn, exc)
        return Response(
            {
                "success": False,
                "result": FAILED,
                "message": "Could not confirm payment status with FonePay.",
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    result, message = interpret_status(status_json)
    status_raw = str(status_json.get("paymentStatus", "")).lower()
    Order.objects.filter(pk=order.pk).update(payment_status=status_raw)

    if result == SUCCESS:
        confirm_paid_order(order, status_json)
        logger.info("FonePay payment confirmed for prn %s (order %s)", prn, order.id)
        return Response(
            {
                "success": True,
                "result": SUCCESS,
                "message": message,
                "prn": prn,
                "payment_status": status_raw,
                "is_paid": True,
                "order_status": order.status,
                "gateway_reference": order.gateway_reference,
            },
            status=status.HTTP_200_OK,
        )

    order.refresh_from_db()
    return Response(
        {
            "success": False,
            "result": result,
            "message": message,
            "prn": prn,
            "payment_status": status_raw,
            "is_paid": order.is_paid,
            "order_status": order.status,
            "gateway_reference": order.gateway_reference,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def fonepay_tax_refund(request):
    """Post a FonePay tax refund for a successful, confirmed FonePay order."""
    order_id = request.data.get("order_id")
    invoice_number = request.data.get("invoice_number") or ""
    invoice_date = request.data.get("invoice_date") or ""
    transaction_amount = request.data.get("transaction_amount")

    if not order_id:
        return Response(
            {"error": "order_id is required."}, status=status.HTTP_400_BAD_REQUEST
        )
    order = _get_order_or_404(order_id)

    if not is_fonepay_payment(order):
        return Response(
            {"error": "Order is not a FonePay payment."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not order.is_paid or not order.gateway_reference:
        return Response(
            {"error": "Only a paid FonePay order with a trace ID can be refunded."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not invoice_number:
        return Response(
            {"error": "invoice_number is required."}, status=status.HTTP_400_BAD_REQUEST
        )
    if not invoice_date:
        return Response(
            {"error": "invoice_date is required (YYYY-MM-DD)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    # Amount defaults to the order total unless explicitly overridden.
    amount = transaction_amount or str(order.total)

    client, error_message = _client_or_error(request)
    if error_message is not None:
        return Response(
            {"success": False, "message": error_message},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        result = client.tax_refund(
            fonepay_trace_id=order.gateway_reference,
            transaction_amount=amount,
            merchant_prn=order.prn,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
        )
    except FonepayError as exc:
        logger.error("FonePay tax refund failed for order %s: %s", order.id, exc)
        return Response(
            {"success": False, "message": "Could not post the FonePay tax refund."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    refund_success = bool(result.get("success"))
    logger.info(
        "FonePay tax refund %s for order %s (trace %s)",
        "succeeded" if refund_success else "reported failure",
        order.id,
        order.gateway_reference,
    )
    return Response(
        {
            "success": refund_success,
            "message": result.get("message") or (
                "Tax refund posted." if refund_success else "Tax refund was rejected."
            ),
            "fonepay_trace_id": result.get("fonepayTraceId")
            or result.get("fonepay_trace_id")
            or order.gateway_reference,
        },
        status=status.HTTP_200_OK,
    )
