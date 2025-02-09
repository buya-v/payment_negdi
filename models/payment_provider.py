from odoo import models, fields, api
import requests
import json

class PaymentProviderNegdi(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(selection_add=[('negdi', 'Negdi')], ondelete={'negdi': 'set default'})
    
    # Production credentials
    negdi_terminal_id = fields.Char(string='Prod Terminal ID')
    negdi_username = fields.Char(string='Prod Username')
    negdi_password = fields.Char(string='Prod Password')
    
    # Test credentials
    negdi_test_terminal_id = fields.Char(string='Test Terminal ID')
    negdi_test_username = fields.Char(string='Test Username')
    negdi_test_password = fields.Char(string='Test Password')

    def _get_negdi_credentials(self):
        Param = self.env['ir.config_parameter'].sudo()
        if self.state == 'test_mode':
            return {
                'terminal_id': self.negdi_test_terminal_id,
                'username': self.negdi_test_username,
                'password': self.negdi_test_password,
                'return_url': Param.get_param('negdi.test_return_url', 'https://test.negdi.mn/return'),
                'api_url': Param.get_param('negdi.test_api_url', 'http://103.229.177.10:8032'),
            }
        return {
            'terminal_id': self.negdi_terminal_id,
            'username': self.negdi_username,
            'password': self.negdi_password,
            'return_url': Param.get_param('negdi.prod_return_url', 'https://secure.negdi.mn/return'),
            'api_url': Param.get_param('negdi.prod_api_url', 'https://secure.negdi.mn/api/pay'),
        }

    def negdi_create_order(self, transaction):
        credentials = self._get_negdi_credentials()
        url = f"{credentials['api_url']}/ec1000"
        headers = {'Content-Type': 'application/json'}
        data = {
            "ordertype": "3dsOrder",
            "terminalid": credentials['terminal_id'],
            "username": credentials['username'],
            "password": credentials['password'],
            "returnurl": credentials['return_url'],
            "amount": transaction.amount,
            "currency": transaction.currency_id.name,
            "ordernum": transaction.reference,
            "description": "Order payment"
        }
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code == 200:
            response_data = response.json().get("order", {})
            transaction.acquirer_reference = response_data.get("tranid")
            transaction.negdi_checkid = response_data.get("checkid")
            return response_data.get("negdiurl")
        return None