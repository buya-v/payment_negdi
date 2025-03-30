# payment_negdi/const.py

API_ENDPOINT_CREATE_ORDER = 'ec1000'
API_ENDPOINT_PROCESS_ORDER = 'ec1003'
API_ENDPOINT_CANCEL_ORDER = 'ec1099'
API_ENDPOINT_INQUIRY_ORDER = 'ec1098'
API_ENDPOINT_CANCEL_TOKEN = 'ec1097'
API_ENDPOINT_INQUIRY_ORDER_TYPE = 'ec1096'

#Order types
ORDER_TYPE_3DS = '3dsOrder'

# Mapping of transaction states to NEGDi payment statuses.
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
    'amex',
    'discover',
}