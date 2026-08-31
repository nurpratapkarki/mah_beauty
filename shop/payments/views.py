"""eSewa payment gateway views."""

import logging

import requests as http_requests
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import Order, PaymentMethod
from .config import EsewaConfig
from .errors import EsewaConfigurationError, EsewaUpstreamError
from .esewa import (
    build_esewa_payload,
    decode_esewa_callback,
    verify_esewa_signature,
)

logger = logging.getLogger(__name__)


def _get_order_or_404(order_id):
    try:
        return get_object_or_404(Order, pk=order_id)
    except (ValueError, TypeError):
        raise Http404("Order not found.")


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def esewa_initiate(request):
    """Build and return the signed eSewa payment payload for an order.

    The frontend should auto-submit a hidden form with the returned fields
    to the ``esewa_url`` endpoint.
    """
    order_id = request.data.get("order_id")
    if not order_id:
        return Response(
            {"error": "order_id is required."}, status=status.HTTP_400_BAD_REQUEST
        )
    order = _get_order_or_404(order_id)

    if order.payment_method != PaymentMethod.ESEWA:
        return Response(
            {"error": "Order is not an eSewa payment."},
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

    try:
        config = EsewaConfig.from_settings()
    except EsewaConfigurationError as exc:
        logger.error("eSewa not configured: %s", exc)
        return Response(
            {"error": "eSewa is not configured."}, status=status.HTTP_502_BAD_GATEWAY
        )

    try:
        payload = build_esewa_payload(order, config)
    except Exception as exc:
        logger.error("eSewa payload build failed for order %s: %s", order.id, exc)
        return Response(
            {"error": "Could not build eSewa payment payload."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    # Persist the transaction_uuid on the order for later callback matching.
    Order.objects.filter(pk=order.pk).update(
        transaction_uuid=payload["transaction_uuid"],
        payment_status="pending",
    )

    logger.info(
        "eSewa payment initiated for order %s (uuid=%s)",
        order.id,
        payload["transaction_uuid"],
    )

    return Response(payload, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def esewa_callback(request):
    """Process the eSewa redirect callback after payment completion.

    eSewa redirects to our success_url with a ``data`` query parameter
    containing base64-encoded JSON. We decode, verify the signature, and
    mark the order paid if status is COMPLETE.
    """
    encoded_data = request.query_params.get("data")
    if not encoded_data:
        return Response(
            {"error": "Missing callback data."}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        callback_data = decode_esewa_callback(encoded_data)
    except ValueError as exc:
        logger.warning("Invalid eSewa callback data: %s", exc)
        return Response(
            {"error": "Invalid callback data."}, status=status.HTTP_400_BAD_REQUEST
        )

    transaction_uuid = callback_data.get("transaction_uuid", "")
    order = Order.objects.filter(transaction_uuid=transaction_uuid).first()
    if order is None:
        logger.warning(
            "eSewa callback for unknown transaction_uuid: %s", transaction_uuid
        )
        return Response(
            {"error": "No order found for this transaction."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Idempotent: if already paid, just return current state.
    if order.is_paid and order.status == "confirmed":
        logger.info(
            "eSewa callback for already-paid order %s — idempotent skip", order.id
        )
        return Response(
            {
                "status": order.payment_status or "COMPLETE",
                "message": "Payment already confirmed.",
                "order_id": str(order.id),
            },
            status=status.HTTP_200_OK,
        )

    # Verify signature.
    try:
        config = EsewaConfig.from_settings()
    except EsewaConfigurationError as exc:
        logger.error("eSewa not configured: %s", exc)
        return Response(
            {"error": "eSewa is not configured."}, status=status.HTTP_502_BAD_GATEWAY
        )

    if not verify_esewa_signature(callback_data, config.secret_key):
        logger.warning(
            "eSewa callback signature verification failed for order %s", order.id
        )
        return Response(
            {"error": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST
        )

    payment_status = callback_data.get("status", "")
    transaction_code = callback_data.get("transaction_code", "")

    if payment_status == "COMPLETE":
        order.mark_gateway_confirmed(
            gateway_reference=transaction_code,
            status=payment_status,
        )
        logger.info(
            "eSewa payment confirmed for order %s (code=%s)",
            order.id,
            transaction_code,
        )
    else:
        Order.objects.filter(pk=order.pk).update(payment_status=payment_status)
        logger.info(
            "eSewa payment not complete for order %s (status=%s)",
            order.id,
            payment_status,
        )

    return Response(
        {
            "status": payment_status,
            "message": f"Payment {payment_status.lower()}.",
            "order_id": str(order.id),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def esewa_check_status(request):
    """Query eSewa's transaction status API to verify payment independently.

    Accepts ``order_id`` to look up the order, then calls eSewa's
    ``/api/epay/transaction/status/`` endpoint with the order's transaction
    details. On COMPLETE, marks the order paid.
    """
    order_id = request.data.get("order_id")
    if not order_id:
        return Response(
            {"error": "order_id is required."}, status=status.HTTP_400_BAD_REQUEST
        )
    order = _get_order_or_404(order_id)

    # Idempotent: already paid — just return current state.
    if order.is_paid and order.status == "confirmed":
        logger.info(
            "eSewa status check for already-paid order %s — idempotent", order.id
        )
        return Response(
            {
                "status": order.payment_status or "COMPLETE",
                "is_paid": True,
                "order_id": str(order.id),
                "gateway_reference": order.gateway_reference,
            },
            status=status.HTTP_200_OK,
        )

    if not order.transaction_uuid:
        return Response(
            {"error": "Order has no transaction UUID — payment was not initiated."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        config = EsewaConfig.from_settings()
    except EsewaConfigurationError as exc:
        logger.error("eSewa not configured: %s", exc)
        return Response(
            {"error": "eSewa is not configured."}, status=status.HTTP_502_BAD_GATEWAY
        )

    # Query eSewa status-check API.
    try:
        resp = http_requests.get(
            config.status_check_url,
            params={
                "product_code": config.merchant_code,
                "total_amount": str(order.total),
                "transaction_uuid": order.transaction_uuid,
            },
            timeout=15,
        )
        resp.raise_for_status()
        status_data = resp.json()
    except http_requests.RequestException as exc:
        logger.error("eSewa status check failed for order %s: %s", order.id, exc)
        return Response(
            {"error": "Could not query eSewa status."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except ValueError as exc:
        logger.error("eSewa returned non-JSON for order %s: %s", order.id, exc)
        return Response(
            {"error": "Invalid response from eSewa."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    payment_status = status_data.get("status", "")
    ref_id = status_data.get("ref_id", "")

    if payment_status == "COMPLETE":
        order.mark_gateway_confirmed(
            gateway_reference=ref_id,
            status=payment_status,
        )
        logger.info(
            "eSewa payment confirmed via status check for order %s (ref=%s)",
            order.id,
            ref_id,
        )
    else:
        Order.objects.filter(pk=order.pk).update(payment_status=payment_status)
        logger.info(
            "eSewa status check for order %s: %s", order.id, payment_status
        )

    order.refresh_from_db()
    return Response(
        {
            "status": payment_status,
            "is_paid": order.is_paid,
            "order_id": str(order.id),
            "gateway_reference": order.gateway_reference,
        },
        status=status.HTTP_200_OK,
    )
