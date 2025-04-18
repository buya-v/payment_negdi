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
from ..const import NEGDI_DEFAULT_ORDER_TYPE, NEGDI_QR_ORDER_TYPE
from ..controllers.main import NEGDiController


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    negdi_check_id = fields.Char(
        string="NEGDi Check ID",
        readonly=True, # Usually set by the system, not user
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

    def _negdi_make_order_request(self):
        # ... (Keep the full implementation of this method from previous versions) ...
        # It should perform the requests.post call and return the negdi_url
        # Ensure it handles errors correctly (logging and raising ValidationError)
        self.ensure_one()
        if self.provider_code != 'negdi':
             # Should not happen if called correctly, but good practice
             return None
        if self.currency_id.name == "MNT" and self.amount <= 300:
            self._set_error(_("Payment limits error: Amount must greater than 300 MNT."))
            raise ValidationError(_("Payment limits error: Amount must greater than 300 MNT."))

        provider = self.provider_id
        if not all([provider.negdi_terminal_identifier, provider.negdi_username, provider.negdi_password]):
             self._set_error(_("Configuration error: NEGDi credentials missing."))
             raise ValidationError(_("The NEGDi payment provider is missing required credentials."))

        api_urls = provider._get_negdi_urls()
        api_url = api_urls.get('negdi_create_order_url')
        if not api_url:
             self._set_error(_("Configuration error: NEGDi Create Order URL missing."))
             raise ValidationError("NEGDi: Provider not configured correctly (missing URL).")
        

        # --- Determine the description ---
        # Use the name of the first linked Sale Order if available,
        # otherwise fallback to the transaction reference.
        sale_order = self.reference # Default fallback
        if self.sale_order_ids:
            # Assumes only one SO is linked in the e-commerce flow
            # Access the name field of the first sale.order record
            sale_order = self.sale_order_ids[0].name
            _logger.info("NEGDi: Using Sale Order name '%s' for tx %s", sale_order, self.reference)
        else:
            _logger.info("NEGDi: No linked Sale Order found for tx %s, using reference '%s'", self.reference, ordernum)
        # --- End Determine description ---

        if self.payment_method_code =='card':
            # Set the order type to 'Card' for card payments
            order_type = NEGDI_DEFAULT_ORDER_TYPE
        if self.payment_method_code == 'negdi_qpay':
            order_type = NEGDI_QR_ORDER_TYPE

        payload = {
            'ordertype': order_type,
            'terminalid': provider.negdi_terminal_identifier,
            'username': provider.negdi_username,
            'password': provider.negdi_password,
            'returnurl': urls.url_join(self.get_base_url(), NEGDiController._return_url),
            'amount': self.amount,
            'currency': self.currency_id.name,
            'ordernum': self.reference,
            'description': sale_order,
        }
        _logger.info("NEGDi: Using return url as %s", urls.url_join(self.get_base_url(), NEGDiController._return_url))
        _logger.info("NEGDi: Sending ec1000 request for %s to %s:\n%s", self.reference, api_url, pprint.pformat(payload))
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            response_data = response.json()
            _logger.info("NEGDi: Received ec1000 response for %s:\n%s", self.reference, pprint.pformat(response_data))

            order_data = response_data.get('order', {})
            negdi_status = order_data.get('status')
            if negdi_status == 'System error':
                negdi_order_detail = order_data.get('detail')
                _logger.error("System error received: %s", negdi_order_detail)
                self._set_error(_(negdi_order_detail))
                raise ValidationError(_("NEGDi System Error: %s", negdi_order_detail))
            else:  
                negdi_url = order_data.get('negdiurl')
                if not negdi_url:
                    _logger.error("NEGDi: 'negdiurl' not found in response for %s.", self.reference)
                    self._set_error(_("NEGDi: Payment URL missing in API response."))
                    raise ValidationError(_("NEGDi: Could not get payment URL. Please try again."))

            # Store tranid/checkid if needed later for verification/inquiry

            self.provider_reference = order_data.get('tranid')
            # Example: Store checkid in metadata (adjust if needed)
            self.negdi_check_id = order_data.get('checkid')
     

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
            raise ValidationError(_("An unexpected error occurred. %s", e))

    def _negdi_make_inquiry_request(self):
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
        if not self.negdi_check_id:
             raise ValidationError("Cannot perform inquiry: Check ID is missing.")

        payload = {
            # Payload for ec1098 (based on Page 13)
            'tranid': self.provider_reference, # Ensure it's an integer if required by API
            'checkid': self.negdi_check_id,
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

    def _get_specific_rendering_values(self, processing_values):
        """ Override of `payment` to return NEGDi-specific processing values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic processing values of the transaction.
        :return: The dict of provider-specific processing values.
        :rtype: dict
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'negdi':
            return res

        converted_amount = payment_utils.to_minor_currency_units(self.amount, self.currency_id)
        base_url = self.provider_id.get_base_url()
        payment_option = negdi_utils.get_payment_option(self.payment_method_id.code)

        negdi_url = self._negdi_make_order_request()
        if not negdi_url:
            raise ValidationError(_("NEGDi: Could not create order."))
        # Prepare the rendering values for NEGDi
        rendering_values = {
            'api_url': negdi_url,
            'tranid': self.provider_reference,
            'checkid': self.negdi_check_id,
        }
        # if payment_option:  # Not included if the payment method is 'card'.
        #     rendering_values['payment_option'] = payment_option
        # rendering_values.update({
        #     'signature': self.provider_id._negdi_calculate_signature(
        #         rendering_values, incoming=False
        #     ),
        # })
        return rendering_values

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """ Override of `payment` to find the transaction based on NEGDi data.

        :param str provider_code: The code of the provider that handled the transaction.
        :param dict notification_data: The notification data sent by the provider.
        :return: The transaction if found.
        :rtype: recordset of `payment.transaction`
        :raise ValidationError: If inconsistent data are received.
        :raise ValidationError: If the data match no transaction.
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'negdi' or len(tx) == 1:
            return tx
        
        # Extract tranid and checkid from the GET parameters
        tranid = notification_data.get('tranid')
        checkid = notification_data.get('checkid')

        if not tranid or not checkid:
            _logger.warning("NEGDi: Received incomplete return data: %s", notification_data)
            # Redirect to a generic error or status page if data is missing
            raise ValidationError(
                "NEGDi: Received incomplete return data: %s", notification_data
                )
      
        # Find the Odoo transaction based on the provider_reference (tranid)
        tx = self.search([
            ('provider_reference', '=', tranid),
            ('provider_code', '=', 'negdi')
        ], limit=1)

        if not tx:
            _logger.warning("NEGDi: No transaction found for tranid %s", tranid)
            # Redirect to a generic error or status page if no transaction is found
            raise ValidationError(
                "NEGDi: No transaction found for tranid %s", tranid
                )

        return tx

    def _process_notification_data(self, notification_data):
        """ Override of `payment' to process the transaction based on NEGDi data.

        Note: self.ensure_one()

        :param dict notification_data: The notification data sent by the provider.
        :return: None
        :raise ValidationError: If inconsistent data are received.
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'negdi':
            return
        
        notification_data = self._negdi_make_inquiry_request()
        if not notification_data:
            raise ValidationError("NEGDi: Inquiry request failed.")
        
        order_data = notification_data.get('order')
        # Update the provider reference.
        self.provider_reference = order_data.get('tranid')

        # Update payment method based on inquiry response if available (Page 13)
        payment_method_code = order_data.get('paymentmethod') # e.g., 'Card', 'QR'
        if payment_method_code:
             payment_method = self.env['payment.method']._get_from_code(payment_method_code.lower())
             if payment_method and self.payment_method_id != payment_method:
                  self.payment_method_id = payment_method

        # Update the payment state.
        status = order_data.get('status')
        if not status:
            _logger.warning("NEGDi: Inquiry response missing status for tx %s.", self.reference)
            self._set_error("NEGDi: " + _("Received Inquiry data with missing payment status."))
            return

        if status in PAYMENT_STATUS_MAPPING['done']:
            _logger.info("NEGDi: Setting transaction %s to DONE based on status '%s'", self.reference, status)
            self._set_done()
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
