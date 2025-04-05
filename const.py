# Mapping of transaction states to NEGDi payment statuses.
# See https://paymentservices-reference.payfort.com/docs/api/build/index.html#transactions-response-codes.
PAYMENT_STATUS_MAPPING = {
    'pending': ('19',),
    'done': ('14',),
}

# The codes of the payment methods to activate when NEGDi is activated.
DEFAULT_PAYMENT_METHOD_CODES = {
    # Primary payment methods.
    'card',
    # Brand payment methods.
    'visa',
    'mastercard',
    'unionpay',
}

# payment_negdi/const.py

# Base URLs for NEGDi API
NEGDI_API_URL_TEST = 'http://103.229.177.10:8032/api/pay'  # Use the one from the spec for now
NEGDI_API_URL_PROD = 'https://payment.negdi.mn/api/pay' # Replace with actual Production URL when known

# Specific API endpoints
NEGDI_CREATE_ORDER_ENDPOINT = 'ec1000'

# Default ordertype for simple redirect
NEGDI_DEFAULT_ORDER_TYPE = '3dsOrder' # Or 'Non3dsOrder' if CVV only is preferred initially