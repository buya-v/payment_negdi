# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hashlib
import logging

from odoo import fields, models

from .. import const


_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('negdi', "Amazon Payment Services")], ondelete={'negdi': 'set default'}
    )
    negdi_merchant_identifier = fields.Char(
        string="NEGDi Merchant Identifier",
        help="The code of the merchant account to use with this provider.",
        required_if_provider='negdi',
    )
    negdi_access_code = fields.Char(
        string="NEGDi Access Code",
        help="The access code associated with the merchant account.",
        required_if_provider='negdi',
        groups='base.group_system',
    )
    negdi_sha_request = fields.Char(
        string="NEGDi SHA Request Phrase",
        required_if_provider='negdi',
        groups='base.group_system',
    )
    negdi_sha_response = fields.Char(
        string="NEGDi SHA Response Phrase",
        required_if_provider='negdi',
        groups='base.group_system',
    )

    #=== BUSINESS METHODS ===#

    def _negdi_get_api_url(self):
        if self.state == 'enabled':
            return 'https://checkout.payfort.com/FortAPI/paymentPage'
        else:  # 'test'
            return 'https://sbcheckout.payfort.com/FortAPI/paymentPage'

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
