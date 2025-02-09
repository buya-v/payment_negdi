import json
import logging
import base64
import hashlib

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import config

_logger = logging.getLogger(__name__)

class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('negdi', 'NEGDI Payment Provider')],
        ondelete={'negdi': 'set default'}
    )
    negdi_terminal_id = fields.Char(string='Terminal ID', required_if_provider='negdi', groups='base.group_system')
    negdi_username = fields.Char(string='Username', required_if_provider='negdi', groups='base.group_system')
    negdi_password = fields.Char(string='Password', required_if_provider='negdi', groups='base.group_system')
    negdi_public_key = fields.Text(string='NEGDI Public Key', groups='base.group_system', help="Public key provided by NEGDI for verifying response signatures.")
    negdi_webhook_url = fields.Char(string='Webhook URL', compute='_compute_negdi_webhook_url')

    negdi_test_url = fields.Char(string='NEGDI Test URL', default='http://103.229.177.10:8032/api/pay/', groups='base.group_system',
        help="The base URL for the NEGDI test environment.")
    negdi_prod_url = fields.Char(string='NEGDI Production URL', default='https://api.negdi.com/api/pay/', groups='base.group_system',
        help="The base URL for the NEGDI production environment.")


    @api.depends('company_id')
    def _compute_negdi_webhook_url(self):
        for provider in self:
            if provider.code == 'negdi':
                provider.negdi_webhook_url = provider.get_base_url() + '/payment/negdi/webhook'
            else:
                provider.negdi_webhook_url = False

    def _get_default_payment_method_id(self, provider_code=None):
        self.ensure_one()
        if self.code != 'negdi':
            return super()._get_default_payment_method_id(provider_code)
        return self.env.ref('payment.payment_method_card').id

    def _get_supported_currencies(self):
        """ Hook for sub-modules to implement.
        :return: A set of supported currency names.
        :rtype: set
        """
        res = super()._get_supported_currencies()
        return res | {'MNT'}  # NEGDI supports MNT (Mongolian Tugrik)

    def _negdi_get_api_url(self, endpoint):
        """ Return the API URL based on the environment. """
        if self.state == 'test':
            base_url = self.negdi_test_url
        else:
            base_url = self.negdi_prod_url
        return base_url + endpoint

    def _negdi_make_request(self, endpoint, data=None):
        """ Make a request to the NEGDI API. """
        import requests
        import json

        url = self._negdi_get_api_url(endpoint)
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

    def _negdi_verify_signature(self, order_data, signature):
        """Verify the signature of the NEGDI response using the public key.
        :param str order_data:  the data within the order tag.
        :param str signature:   the ordersign tag
        :return: True if valid.
        """
        if not self.negdi_public_key:
            _logger.warning("NEGDI Public Key is not configured.")
            return False

        try:
            public_key = self.negdi_public_key.encode('utf-8')
            decoded_signature = base64.b64decode(signature)
            order_data_encoded = json.dumps(order_data).encode('utf-8')

            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.primitives import serialization

            # Load the public key
            public_key_object = serialization.load_pem_public_key(public_key, backend=default_backend())

            # Verify the signature
            public_key_object.verify(
                decoded_signature,
                order_data_encoded,
                padding.PKCS1v15(),
                hashes.SHA256()
            )

            _logger.info("NEGDI signature verification successful")
            return True

        except Exception as e:
            _logger.exception("NEGDI signature verification failed: %s", e)
            if config['dev_mode']:
                raise
            return False