# Mapping of NEGDi transaction statuses (from Inquiry response) to Odoo states.
# Based on Page 17 of NEGDI Spec. Adjust keys/values as needed based on actual API responses.
PAYMENT_STATUS_MAPPING = {
    # Odoo 'pending' states
    'pending': ('Preparing', 'Transaction expected'), # Add NEGDi states that mean pending

    # Odoo 'done' states
    'done': ('Approved', 'Authorized', 'Funded', 'Fully paid', 'Partially paid'), # Add NEGDi success states

    # Odoo 'cancel' states (User initiated)
    'cancel': ('Cancelled', 'Refused', 'Closed'), # Add NEGDi user cancel/refusal states

    # Odoo 'error' states (System/Processing errors)
    'error': ('Declined', 'Expired', 'System error'), # Add NEGDi failure/error states
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
NEGDI_INQUIRY_ORDER_ENDPOINT = 'ec1098' # Add Inquiry endpoint

# Default ordertype for simple redirect
NEGDI_DEFAULT_ORDER_TYPE = '3dsOrder' # Or 'Non3dsOrder' if CVV only is preferred initially