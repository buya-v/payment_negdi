# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hashlib
import logging

from odoo import fields, models

from .. import const


_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('negdi', "NEGDi Payment Services")], ondelete={'negdi': 'set default'}
    )
    negdi_terminal_identifier = fields.Char(
        string="NEGDi Terminal ID",
        help="The code of the merchant terminal to use with this provider.",
        required_if_provider='negdi',
        groups='base.group_system',
    )
    negdi_username = fields.Char(
        string="NEGDi Merchant Username",
        required_if_provider='negdi',
        groups='base.group_system',
    )
    negdi_password = fields.Char(
        string="NEGDi Merchant Password",
        required_if_provider='negdi',
        groups='base.group_system',
    )

    negdi_public_key = fields.Text(
        string="NEGDi Public Key",
        help="The PEM-formatted public key provided by NEGDi for verifying response signatures.",
        groups='base.group_system',
        # required_if_provider='negdi', # Make required if verification is mandatory
    )


    #=== BUSINESS METHODS ===#

    def _negdi_get_api_url(self):
        """ Return the API URL according to the provider state. """
        self.ensure_one()
        if self.state == 'enabled':
            # Assume the URL in spec is TEST. Replace const.NEGDI_ENDPOINT_PROD later.
            # You might want a dedicated field on the provider form to choose test/prod explicitly.
            return const.NEGDI_API_URL_PROD
        else: # 'disabled' or 'test'
            return const.NEGDI_API_URL_TEST
    
    def _get_negdi_urls(self):
        """ NEGDi URL getter."""
        self.ensure_one()
        base_url = self._negdi_get_api_url()
        return {
            'negdi_create_order_url': f"{base_url}/{const.NEGDI_CREATE_ORDER_ENDPOINT}",
            'negdi_inquiry_order_url': f"{base_url}/{const.NEGDI_INQUIRY_ORDER_ENDPOINT}", # Add inquiry URL
        }

    def _negdi_calculate_signature(self, data, incoming=True):
        """ Compute the signature for the provided data according to the NEGDi documentation.

        :param dict data: The data to sign.
        :param bool incoming: Whether the signature must be generated for an incoming (NEGDi to Odoo)
                              or outgoing (Odoo to NEGDi) communication.
        :return: The calculated signature.
        :rtype: str
        """
        sign_data = ''.join([f'{k}={v}' for k, v in sorted(data.items()) if k != 'signature'])
        key = self.negdi_sha_response if incoming else self.negdi_sha_request
        signing_string = ''.join([key, sign_data, key])
        return hashlib.sha256(signing_string.encode()).hexdigest()

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'negdi':
            return default_codes
        return const.DEFAULT_PAYMENT_METHOD_CODES
