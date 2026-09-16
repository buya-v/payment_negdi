# -*- coding: utf-8 -*-
"""Constants for the NEGDI e-commerce gateway (merchant API v1.8, 2024-08-13)."""

# The gateway serves plain HTTP on this port; see the provider form's warning.
DEFAULT_API_URL = 'http://103.229.177.10:8032'

ENDPOINT_CREATE_ORDER = '/api/pay/ec1000'      # Create order (simple): returns negdiurl
ENDPOINT_INQUIRY_ORDER = '/api/pay/ec1098'     # Order inquiry: the authoritative status
ENDPOINT_CANCEL_ORDER = '/api/pay/ec1099'      # Same-day reversal only
ENDPOINT_ORDER_TYPES = '/api/pay/ec1096'       # Order types enabled for this merchant

# Odoo payment method code -> NEGDI ``ordertype``.
ORDER_TYPE_BY_PAYMENT_METHOD = {
    'card': '3dsOrder',   # card purchase, verified with 3-D Secure
    'qpay': 'QPAY',       # QR payment (NEGDI may also offer cards on this page)
}
DEFAULT_PAYMENT_METHOD_CODES = {'card', 'qpay'}

SUPPORTED_CURRENCIES = ('MNT',)

# Status values (spec section 10). "Partially paid" is listed as a success level
# by NEGDI, but for a purchase it means the order is NOT fully paid, so it must
# not release what was bought.
STATUS_DONE = ('Approved', 'Authorized', 'Funded', 'Fully paid')
STATUS_PENDING = ('Preparing', 'Transaction expected', 'Partially paid')
STATUS_CANCEL = ('Expired', 'Cancelled', 'Rejected', 'Refused', 'Closed')
STATUS_ERROR = ('Declined', 'System error')

# How long an unresolved order keeps being polled.
POLL_WINDOW_HOURS = 24

# Published in the merchant spec, section 12 ("Response value confirmation").
DEFAULT_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA4OmScz6Xo5bxSDAjfkRd
C5yYIkceauCMQBlpa8u3IMORrvX8YvgpDMv5nvFcVT4f6IlarYFkX7DDXbwMlSTg
Xga/aDmfSx3MubpGV8ln3HCiXKeqMI0A73ww5BLMA++aD3xKm6iJVHOvD4PK0C1g
7KnYJingOpwLH7GGDG63XFvMsFR5A00jCDdruO17AXZdfdHVZVhRxB0GaqehtHlU
WlzqXfZ9KR2eZcloqPIIaSx2EFFcJfp8Wh4gZt2IJmhrfZPEZ5VTafHGmgI7yZcL
qYcj1CDyBY5audAVojnYfGpyH24cPjTFeFM1Ab8LaW7F9HUc1BSPMQHm6kpVxc8E
RwIDAQAB
-----END PUBLIC KEY-----"""
