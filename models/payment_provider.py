import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError



_logger = logging.getLogger(__name__)

class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('negdi', 'NEGDi Payment Services')],
        ondelete={'negdi': 'set default'}
    )
    # NEGDi Credentials
    negdi_terminal_id = fields.Char(string='Terminal ID', required_if_provider='negdi', groups='base.group_system')
    negdi_username = fields.Char(string='Username', required_if_provider='negdi', groups='base.group_system')
    negdi_password = fields.Char(string='Password', required_if_provider='negdi', groups='base.group_system')
    negdi_public_key = fields.Text(string='NEGDI Public Key', groups='base.group_system', help="Public key provided by NEGDI for verifying response signatures.")
    # negdi_test_url = fields.Char(string='NEGDI Test URL', default='http://103.229.177.10:8032/api/pay/', groups='base.group_system',
    #     help="The base URL for the NEGDI test environment.")
    # negdi_prod_url = fields.Char(string='NEGDI Production URL', default='https://api.negdi.com/api/pay/', groups='base.group_system',
    #     help="The base URL for the NEGDI production environment.")
    # # Settings
    # negdi_webhook_url = fields.Char(string='Webhook URL', compute='_compute_negdi_webhook_url')


    # @api.depends('company_id')
    # def _compute_negdi_webhook_url(self):
    #     for provider in self:
    #         if provider.code == 'negdi':
    #             provider.negdi_webhook_url = provider.get_base_url() + '/payment/negdi/webhook'
    #         else:
    #             provider.negdi_webhook_url = False

    # @api.model
    # def _get_compatible_providers(self, *args, payment_token=None, **kwargs):
    #     """ Override to filter out negdi acquirers depending on the payment token. """
    #     providers = super()._get_compatible_providers(*args, payment_token=payment_token, **kwargs)
    #     if not payment_token or payment_token.provider_code != 'negdi':
    #         return providers

    #     return providers.filtered(lambda a: a.code == 'negdi')
    
    #=== BUSINESS METHODS ===#

    def _get_negdi_api_url(self):
        if self.state == 'enabled':
            return 'https://api.negdi.com/api/pay/'
        else:  # 'test'
            return 'http://103.229.177.10:8032/api/pay/'
        
    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'aps':
            return default_codes
        return const.DEFAULT_PAYMENT_METHOD_CODES

    # def _get_default_payment_method_id(self, provider_code=None):
    #     self.ensure_one()
    #     if self.code != 'negdi':
    #         return super()._get_default_payment_method_id(provider_code)

    #     try:
    #         payment_method_id = self.env.ref('payment.payment_method_manual').id  # Or 'payment.payment_method_card'
    #     except ValueError:
    #         _logger.warning("External ID 'payment.payment_method_manual' not found.  Falling back to creating a payment journal.")
    #         # If the external ID isn't found, create a basic payment method
    #         PaymentMethod = self.env['payment.method']
    #         payment_method = PaymentMethod.create({
    #             'name': 'NEGDI Manual Payment',
    #             'code': 'manual',  # Or 'card', if appropriate
    #         })
    #         payment_method_id = payment_method.id

    #     return payment_method_id

    # def _get_supported_currencies(self):
    #     """ Hook for sub-modules to implement.
    #     :return: A set of supported currency names.
    #     :rtype: set
    #     """
    #     res = super()._get_supported_currencies()
    #     mnt_currency = self.env['res.currency'].search([('name', '=', 'MNT')], limit=1)
    #     if mnt_currency:
    #         res |= mnt_currency
    #     return res 

    # def _get_validation_supported_fields(self):
    #     """ Hook for sub-modules to implement. """
    #     return super()._get_validation_supported_fields() + [
    #         'cc_number', 'cc_expiry', 'cc_holder_name', 'cc_cvc'
    #     ]

    # def _get_payment_methods_mapping(self):
    #     """ Hook for sub-modules to implement. """
    #     return {
    #         'card': 'card',
    #     }

    # def _get_compatible_payment_methods(self, invoice=None, currency=None, country=None):
    #     """ Hook for sub-modules to implement. """
    #     self.ensure_one()
    #     payment_methods = super()._get_compatible_payment_methods(invoice=invoice, currency=currency, country=country)
    #     if self.code != 'negdi':
    #         return payment_methods

    #     payment_methods = payment_methods.filtered(lambda pm: pm.code == 'manual')
    #     return payment_methods

    def _negdi_make_request(self, endpoint, data=None):
        """ Make a request to the NEGDI API. """
        import requests
        import json

        url = self._get_negdi_api_url() + endpoint  # Use the centralized URL method
        headers = {
            'Content-Type': 'application/json'
        }
        try:
            _logger.info("NEGDI Request URL: %s", url)
            _logger.info("NEGDI Request Data: %s", data)
            response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.exception("NEGDI API Error: %s", str(e))
            raise UserError(_("NEGDI API Error: %s") % str(e))