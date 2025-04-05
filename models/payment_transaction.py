# payment_negdi/models/payment_transaction.py

import logging
import pprint
import json # Import json
import base64 # For signature verification later
import requests # Import requests
from requests.exceptions import RequestException # Import specific exceptions

from werkzeug import urls

from odoo import _, api, models, fields
from odoo.exceptions import UserError,ValidationError
from odoo.addons.payment import utils as payment_utils

from .. import utils as negdi_utils
from ..const import PAYMENT_STATUS_MAPPING
from ..const import NEGDI_DEFAULT_ORDER_TYPE
from ..controllers.main import NEGDiController



_logger = logging.getLogger(__name__)
_logger.info("***** payment_negdi PaymentTransaction Model File Loaded *****") # ADD THIS LINE

# For signature verification
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature
    SIGNATURE_VERIFICATION_SUPPORTED = True
except ImportError:
    SIGNATURE_VERIFICATION_SUPPORTED = False
    _logger.info("NEGDi: 'cryptography' library not found, signature verification disabled.")

class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    negdi_check_id = fields.Char(
        string="NEGDi Check ID",
        readonly=True, # Usually set by the system, not user
        copy=False,
        groups="base.group_user", # Adjust group visibility if needed
        help="Technical field storing the Check ID returned by NEGDi during transaction creation."
    )



    @api.model
    def _compute_reference(self, provider_code, prefix=None, separator='-', **kwargs):
        """ Override of `payment` to ensure that NEGDi' requirements for references are satisfied.

        NEGDi' requirements for transaction are as follows:
        - References can only be made of alphanumeric characters and/or '-' and '_'.
          The prefix is generated with 'tx' as default. This prevents the prefix from being
          generated based on document names that may contain non-allowed characters
          (eg: INV/2020/...).

        :param str provider_code: The code of the provider handling the transaction.
        :param str prefix: The custom prefix used to compute the full reference.
        :param str separator: The custom separator used to separate the prefix from the suffix.
        :return: The unique reference for the transaction.
        :rtype: str
        """
        if provider_code == 'negdi':
            prefix = payment_utils.singularize_reference_prefix()

        return super()._compute_reference(provider_code, prefix=prefix, separator=separator, **kwargs)

    # === Helper to make API Call (Keep this method) ===
    def _negdi_make_ec1000_request(self):
        # ... (Keep the full implementation of this method from previous versions) ...
        # It should perform the requests.post call and return the negdi_url
        # Ensure it handles errors correctly (logging and raising ValidationError)
        self.ensure_one()
        if self.provider_code != 'negdi':
             # Should not happen if called correctly, but good practice
             return None

        provider = self.provider_id
        if not all([provider.negdi_terminal_identifier, provider.negdi_username, provider.negdi_password]):
             self._set_error(_("Configuration error: NEGDi credentials missing."))
             raise ValidationError(_("The NEGDi payment provider is missing required credentials."))

        api_urls = provider._get_negdi_urls()
        api_url = api_urls.get('negdi_create_order_url')
        if not api_url:
             self._set_error(_("Configuration error: NEGDi Create Order URL missing."))
             raise ValidationError("NEGDi: Provider not configured correctly (missing URL).")

        payload = {
            'ordertype': NEGDI_DEFAULT_ORDER_TYPE,
            'terminalid': provider.negdi_terminal_identifier,
            'username': provider.negdi_username,
            'password': provider.negdi_password,
            # Ensure get_base_url() is available or construct appropriately
            'returnurl': self.get_base_url() + '/payment/negdi/return',
            'amount': self.amount,
            'currency': self.currency_id.name,
            'ordernum': self.reference,
            'description': self.reference,
        }

        _logger.info("NEGDi: Sending ec1000 request for %s to %s:\n%s", self.reference, api_url, pprint.pformat(payload))
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            response_data = response.json()
            _logger.info("NEGDi: Received ec1000 response for %s:\n%s", self.reference, pprint.pformat(response_data))

            order_data = response_data.get('order', {})
            negdi_url = order_data.get('negdiurl')

            if not negdi_url:
                 _logger.error("NEGDi: 'negdiurl' not found in response for %s.", self.reference)
                 self._set_error(_("NEGDi: Payment URL missing in API response."))
                 raise ValidationError(_("NEGDi: Could not get payment URL. Please try again."))

            # Store tranid/checkid if needed later for verification/inquiry

            self.provider_reference = order_data.get('tranid')
            # Example: Store checkid in metadata (adjust if needed)
            checkid = order_data.get('checkid')
            if checkid:
                self.negdi_check_id = checkid

            return negdi_url

        except requests.exceptions.Timeout:
            _logger.warning("NEGDi: Timeout during API request for %s", self.reference)
            self._set_error(_("NEGDi: Communication timeout."))
            raise ValidationError(_("The payment provider timed out. Please try again."))
        except requests.exceptions.RequestException as e:
            _logger.error("NEGDi: API request failed for %s: %s", self.reference, e)
            self._set_error(_("NEGDi: Communication error: %s", e))
            raise ValidationError(_("Could not connect to the payment provider. Please try again."))
        except json.JSONDecodeError as e:
            _logger.error("NEGDi: Failed to decode JSON response for %s: %s", self.reference, e)
            self._set_error(_("NEGDi: Invalid response received."))
            raise ValidationError(_("Received an invalid response from the payment provider."))
        except Exception as e:
            _logger.error("NEGDi: Unexpected error during API request for %s: %s", self.reference, e, exc_info=True)
            self._set_error(_("NEGDi: Unexpected error: %s", e))
            raise ValidationError(_("An unexpected error occurred."))

    def _negdi_make_inquiry_request(self, check_id):
        """ Makes the server-to-server request to NEGDi's ec1098 endpoint. """
        self.ensure_one()
        provider = self.provider_id
        if not all([provider.negdi_terminal_identifier, provider.negdi_username, provider.negdi_password]):
             # Don't set error here, just raise validation for calling method
             raise ValidationError(_("Cannot perform inquiry: NEGDi credentials missing."))

        api_urls = provider._get_negdi_urls()
        inquiry_url = api_urls.get('negdi_inquiry_order_url')
        if not inquiry_url:
             raise ValidationError("Cannot perform inquiry: NEGDi Inquiry URL missing.")

        if not self.provider_reference:
             raise ValidationError("Cannot perform inquiry: Transaction is missing the NEGDi tranid (provider_reference).")
        if not check_id:
             raise ValidationError("Cannot perform inquiry: Check ID is missing.")

        payload = {
            # Payload for ec1098 (based on Page 13)
            'tranid': int(self.provider_reference), # Ensure it's an integer if required by API
            'checkid': check_id,
            # Add username/password if required by ec1098 API (spec doesn't show them here, but maybe needed)
            # 'username': provider.negdi_username,
            # 'password': provider.negdi_password,
        }

        _logger.info("NEGDi: Sending ec1098 Inquiry request for %s (tranid: %s):\n%s",
                     self.reference, self.provider_reference, pprint.pformat(payload))
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(inquiry_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            response_data = response.json()
            _logger.info("NEGDi: Received ec1098 Inquiry response for %s:\n%s",
                         self.reference, pprint.pformat(response_data))
            return response_data # Return the full response data
        except Timeout:
            _logger.warning("NEGDi: Timeout during Inquiry API request for %s", self.reference)
            raise ValidationError(_("NEGDi: Communication timeout during status check."))
        except RequestException as e:
            _logger.error("NEGDi: Inquiry API request failed for %s: %s", self.reference, e)
            raise ValidationError(_("NEGDi: Communication error during status check: %s", e))
        except json.JSONDecodeError as e:
            _logger.error("NEGDi: Failed to decode Inquiry JSON response for %s: %s", self.reference, e)
            raise ValidationError(_("Received an invalid response during status check."))
        except Exception as e:
            _logger.error("NEGDi: Unexpected error during Inquiry API request for %s: %s", self.reference, e, exc_info=True)
            raise ValidationError(_("An unexpected error occurred during status check."))

    # === RENDERING METHODS (Modified) === #
    def _get_specific_rendering_values(self, processing_values):
        """ Override of payment. For NEGDi API flow, we don't need specific rendering values here."""
        if self.provider_code == 'negdi':
             # API call is handled by the controller override now
             return {}
        # Let other providers return their specific values
        return super()._get_specific_rendering_values(processing_values)
    
# === FEEDBACK PROCESSING METHODS (Implementation) === #
    def _handle_feedback_data(self, provider_code, data):
        """ Override of `payment` to process feedback data returning from NEGDi.
            For NEGDi, the 'data' comes from our own Inquiry API call, triggered by the return URL.
        """
        if provider_code != 'negdi':
            return super()._handle_feedback_data(provider_code, data)

        # 'data' is the response dict from _negdi_make_inquiry_request
        try:
            # Find the transaction using the Inquiry response data
            tx_sudo = self.sudo()._get_tx_from_notification_data(provider_code, data)
            # Process the Inquiry response data to update the transaction state
            tx_sudo._process_notification_data(data)
        except ValidationError as e:
            # Log validation errors (e.g., tx not found, bad signature) but don't crash controller
            _logger.warning(
                "NEGDi: Validation error handling feedback data: %s. Data: %s", e, data
            )
        # Let the standard flow redirect the user via /payment/status

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """ Override of `payment` to find the transaction based on NEGDi Inquiry data. """
        if provider_code != 'negdi':
            return super()._get_tx_from_notification_data(provider_code, notification_data)

        # 'notification_data' is the response dict from _negdi_make_inquiry_request
        order_data = notification_data.get('order')
        if not isinstance(order_data, dict):
             raise ValidationError("NEGDi: Invalid Inquiry response format (missing 'order' object).")

        # Use tranid from the inquiry response as the primary identifier
        provider_ref = order_data.get('tranid')
        if provider_ref:
            # Convert to string as provider_reference is Char in Odoo
            tx = self.search([
                ('provider_reference', '=', str(provider_ref)), ('provider_code', '=', 'negdi')
            ])
        else:
            # Fallback to ordernum if tranid is missing in response (less ideal)
            reference = order_data.get('ordernum') # This should match Odoo's tx reference
            if not reference:
                raise ValidationError("NEGDi: Inquiry response data missing 'tranid' and 'ordernum'.")
            tx = self.search([('reference', '=', reference), ('provider_code', '=', 'negdi')])

        if not tx:
            raise ValidationError(
                "NEGDi: No transaction found matching Inquiry response data.", notification_data
            )
        if len(tx) > 1:
             _logger.warning("NEGDi: Multiple transactions found for Inquiry response: %s", provider_ref or reference)
             # Maybe return the latest one? Or raise error? Depends on business logic.
             # Returning the first one for now.
             # raise ValidationError("NEGDi: Multiple transactions found for Inquiry response.")

        return tx

    def _process_notification_data(self, notification_data):
        """ Override of `payment` to process the NEGDi Inquiry response data. """
        if self.provider_code != 'negdi':
            return super()._process_notification_data(notification_data)

        # 'notification_data' is the response dict from _negdi_make_inquiry_request
        order_data = notification_data.get('order')
        if not isinstance(order_data, dict):
             _logger.warning("NEGDi: Received invalid Inquiry data for tx %s: %s", self.reference, notification_data)
             self._set_error("NEGDi: Invalid Inquiry response received.")
             return # Don't process further

        # --- Signature Verification (Optional but Recommended) ---
        # signature_b64 = notification_data.get('ordersign')
        # public_key_pem = self.provider_id.negdi_public_key
        # if signature_b64 and public_key_pem and SIGNATURE_VERIFICATION_SUPPORTED:
        #     try:
        #         # Prepare data exactly as NEGDi signed it (likely the JSON string of the 'order' object)
        #         # IMPORTANT: Ensure encoding (e.g., UTF-8) and format match what NEGDi signs
        #         signed_data_string = json.dumps(order_data, separators=(',', ':'), sort_keys=True) # Example format, verify with NEGDi
        #         self._negdi_verify_signature(signature_b64, signed_data_string.encode('utf-8'))
        #         _logger.info("NEGDi: Signature verified successfully for tx %s", self.reference)
        #     except (ValidationError, InvalidSignature) as e:
        #         _logger.warning("NEGDi: Invalid signature for tx %s: %s", self.reference, e)
        #         self._set_error("NEGDi: " + _("Received notification with invalid signature."))
        #         return # Stop processing if signature is invalid
        # elif signature_b64 and not public_key_pem:
        #     _logger.warning("NEGDi: Received signature but Public Key is not configured for tx %s.", self.reference)
        #     # Decide whether to proceed without verification or set an error/pending state
        # --- End Signature Verification ---

        # Update provider reference again just in case (should match)
        provider_ref = order_data.get('tranid')
        if provider_ref and self.provider_reference != str(provider_ref):
            _logger.warning("NEGDi: tranid mismatch for tx %s. Stored: %s, Received: %s",
                            self.reference, self.provider_reference, provider_ref)
            # Decide if this is an error or just update
            # self.provider_reference = str(provider_ref)

        # Update payment method based on inquiry response if available (Page 13)
        payment_method_code = order_data.get('paymentmethod') # e.g., 'Card', 'QR'
        if payment_method_code:
             payment_method = self.env['payment.method']._get_from_code(payment_method_code.lower())
             if payment_method and self.payment_method_id != payment_method:
                  self.payment_method_id = payment_method

        # Update the payment state based on the Inquiry status (Page 17 mapping)
        status = order_data.get('status')
        if not status:
            _logger.warning("NEGDi: Inquiry response missing status for tx %s.", self.reference)
            self._set_error("NEGDi: " + _("Received Inquiry data with missing payment status."))
            return

        if status in PAYMENT_STATUS_MAPPING['done']:
            _logger.info("NEGDi: Setting transaction %s to DONE based on status '%s'", self.reference, status)
            self._set_done()
            # Optionally write approval code if available
            approval_code = order_data.get('approvalCode')
            if approval_code:
                 self.write({'narration': f"Approval Code: {approval_code}"}) # Example: store in narration
        elif status in PAYMENT_STATUS_MAPPING['pending']:
            _logger.info("NEGDi: Setting transaction %s to PENDING based on status '%s'", self.reference, status)
            self._set_pending()
        elif status in PAYMENT_STATUS_MAPPING['cancel']:
             _logger.info("NEGDi: Setting transaction %s to CANCEL based on status '%s'", self.reference, status)
             self._set_canceled() # Use Odoo's cancel state
        elif status in PAYMENT_STATUS_MAPPING['error']:
             _logger.warning("NEGDi: Setting transaction %s to ERROR based on status '%s'", self.reference, status)
             error_detail = order_data.get('detail', "Unknown error from provider.") # Get detail if available
             self._set_error(f"NEGDi: {status} - {error_detail}")
        else:
            # Handle unknown statuses
            _logger.warning("NEGDi: Received unknown status '%s' for tx %s.", status, self.reference)
            self._set_error("NEGDi: " + _("Received unknown transaction status: %s", status))

    # --- Signature Verification Helper (Implement if needed) ---
    # def _negdi_verify_signature(self, signature_b64, data_bytes):
    #     self.ensure_one()
    #     if not SIGNATURE_VERIFICATION_SUPPORTED:
    #         raise ValidationError(_("Signature verification requires the 'cryptography' library."))
    #
    #     public_key_pem = self.provider_id.negdi_public_key
    #     if not public_key_pem:
    #         raise ValidationError(_("Cannot verify signature: NEGDi Public Key is not configured."))
    #
    #     try:
    #         public_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))
    #         signature_bytes = base64.b64decode(signature_b64)
    #
    #         # Use padding and hash algorithm matching NEGDi (likely PSS or PKCS1v15 with SHA256)
    #         # This requires confirmation from NEGDi documentation
    #         padding_algo = padding.PKCS1v15() # Or padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH)
    #         hasher = hashes.SHA256()
    #
    #         public_key.verify(
    #             signature_bytes,
    #             data_bytes,
    #             padding_algo,
    #             hasher
    #         )
    #         # If verify() doesn't raise an exception, the signature is valid
    #         return True
    #     except InvalidSignature:
    #         raise ValidationError(_("Invalid signature."))
    #     except Exception as e:
    #         _logger.error("NEGDi: Error during signature verification for tx %s: %s", self.reference, e, exc_info=True)
    #         raise ValidationError(_("An error occurred during signature verification."))