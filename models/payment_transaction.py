# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint
import json # Import json
import requests # Import requests
from requests.exceptions import RequestException # Import specific exceptions

from werkzeug import urls

from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.addons.payment import utils as payment_utils

from .. import utils as negdi_utils
from ..const import PAYMENT_STATUS_MAPPING
from ..const import NEGDI_DEFAULT_ORDER_TYPE
from ..controllers.main import NEGDiController


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

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

        
        # Get the correct API endpoint URL
        api_urls = self.provider_id._get_negdi_urls()
        create_order_url = api_urls.get('negdi_create_order_url')
        if not create_order_url:
            raise ValidationError("NEGDi: Provider is not configured correctly (missing URLs).")
        
        # Prepare the payload according to NEGDi ec1000 spec (Page 6)
        payload = {
            # --- Mandatory Fields ---
            'ordertype': NEGDI_DEFAULT_ORDER_TYPE, # Use the default from const.py
            'terminalid': self.provider_id.negdi_terminal_identifier,
            'username': self.provider_id.negdi_username,
            'password': self.provider_id.negdi_password,
            'returnurl': urls.url_join(base_url, NEGDiController._return_url),
            'amount': self.amount, # Odoo amount field is Decimal/Float
            'currency': 'MNT',

            # --- Optional Fields ---
            'ordernum': self.reference, # Use Odoo's transaction reference
            'description': self.reference, # Use Odoo's transaction reference
        }

        # Check required credential fields
        required_fields = ['terminalid', 'username', 'password']
        missing_fields = [f for f in required_fields if not payload.get(f)]
        if missing_fields:
            _logger.warning(
                "NEGDi: Missing required credentials for transaction %s: %s",
                 self.reference, missing_fields
            )
            raise ValidationError(
                _("The payment provider is missing the following credentials: %s", ", ".join(missing_fields))
            )

        # === Make the Server-to-Server API Call ===
        headers = {'Content-Type': 'application/json'}
        redirect_url = None
        try:
            _logger.info("NEGDi: Sending request to %s for transaction %s with payload:\n%s",
                         create_order_url, self.reference, pprint.pformat(payload))

            # Use requests.post, sending data as json
            response = requests.post(create_order_url, headers=headers, json=payload, timeout=20)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            # Parse the JSON response
            response_data = response.json()
            _logger.info("NEGDi: Received response for transaction %s:\n%s",
                         self.reference, pprint.pformat(response_data))

            # Extract the redirect URL - adjust keys based on the *exact* JSON structure
            if response_data.get('order') and response_data['order'].get('negdiurl'):
                redirect_url = response_data['order']['negdiurl']
                # Optional: Store tranid/checkid if needed for later inquiry/verification
                self.provider_reference = response_data['order'].get('tranid')
                # You might need a custom field for checkid if it's needed later:
                # self.negdi_checkid = response_data['order'].get('checkid')
            else:
                _logger.error("NEGDi: 'negdiurl' not found in response for transaction %s. Response: %s",
                              self.reference, response_data)
                raise ValidationError(_("NEGDi: Received an invalid response from the payment provider."))

            # Optional: Verify ordersign here if needed in the future

        except RequestException as e:
            _logger.error("NEGDi: Communication error for transaction %s: %s", self.reference, e)
            raise ValidationError(_("Could not establish communication with the payment provider. Please try again."))
        except json.JSONDecodeError as e:
             _logger.error("NEGDi: Failed to decode JSON response for transaction %s: %s", self.reference, e)
             raise ValidationError(_("Received an unreadable response from the payment provider."))
        except Exception as e:
            # Catch any other unexpected errors during the process
            _logger.error("NEGDi: Unexpected error during API call for transaction %s: %s", self.reference, e)
            raise ValidationError(_("An unexpected error occurred with the payment provider."))

        if not redirect_url:
             raise ValidationError(_("NEGDi: Failed to retrieve the payment redirection URL."))

        # Return the extracted URL for the template
        # Use a clear key name like 'redirect_url'
        return {'redirect_url': redirect_url}

        # requests.get(redirect_url)
        # return {'api_url': redirect_url}

        
        # rendering_values = {
        #     'command': 'PURCHASE',
        #     'access_code': self.provider_id.negdi_access_code,
        #     'merchant_identifier': self.provider_id.negdi_merchant_identifier,
        #     'merchant_reference': self.reference,
        #     'amount': str(converted_amount),
        #     'currency': self.currency_id.name,
        #     'language': self.partner_lang[:2],
        #     'customer_email': self.partner_id.email_normalized,
        #     'return_url': urls.url_join(base_url, NEGDiController._return_url),
        # }
        # if payment_option:  # Not included if the payment method is 'card'.
        #     rendering_values['payment_option'] = payment_option
        # rendering_values.update({
        #     'signature': self.provider_id._negdi_calculate_signature(
        #         rendering_values, incoming=False
        #     ),
        #     'api_url': self.provider_id._negdi_get_api_url(),
        # })
        # return rendering_values



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

        reference = notification_data.get('merchant_reference')
        if not reference:
            raise ValidationError(
                "NEGDi: " + _("Received data with missing reference %(ref)s.", ref=reference)
            )

        tx = self.search([('reference', '=', reference), ('provider_code', '=', 'negdi')])
        if not tx:
            raise ValidationError(
                "NEGDi: " + _("No transaction found matching reference %s.", reference)
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

        # Update the provider reference.
        self.provider_reference = notification_data.get('fort_id')

        # Update the payment method.
        payment_option = notification_data.get('payment_option', '')
        payment_method = self.env['payment.method']._get_from_code(payment_option.lower())
        self.payment_method_id = payment_method or self.payment_method_id

        # Update the payment state.
        status = notification_data.get('status')
        if not status:
            raise ValidationError("NEGDi: " + _("Received data with missing payment state."))
        if status in PAYMENT_STATUS_MAPPING['pending']:
            self._set_pending()
        elif status in PAYMENT_STATUS_MAPPING['done']:
            self._set_done()
        else:  # Classify unsupported payment state as `error` tx state.
            status_description = notification_data.get('response_message')
            _logger.info(
                "Received data with invalid payment status (%(status)s) and reason '%(reason)s' "
                "for transaction with reference %(ref)s",
                {'status': status, 'reason': status_description, 'ref': self.reference},
            )
            self._set_error("NEGDi: " + _(
                "Received invalid transaction status %(status)s and reason '%(reason)s'.",
                status=status, reason=status_description
            ))
