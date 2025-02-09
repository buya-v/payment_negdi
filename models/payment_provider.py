from odoo import models, fields, api
import requests
import json

class PaymentProviderNegdi(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(selection_add=[('negdi', 'Negdi')], ondelete={'negdi': 'set default'})
    
    # Production credential fields
    negdi_terminal_id = fields.Char(string='Prod Terminal ID')
    negdi_username = fields.Char(string='Prod Username')
    negdi_password = fields.Char(string='Prod Password')
    negdi_return_url = fields.Char(string='Prod Return URL') 
    negdi_api_url = fields.Char(string='Prod API URL')
    
    # Test credential fields
    negdi_test_terminal_id = fields.Char(string='Test Terminal ID')
    negdi_test_username = fields.Char(string='Test Username')
    negdi_test_password = fields.Char(string='Test Password')
    negdi_test_return_url = fields.Char(string='Test Return URL')
    negdi_test_api_url = fields.Char(string='Test API URL')

    def _get_negdi_credentials(self):
        if self.state == 'test_mode':
            return {
                'terminal_id': self.negdi_test_terminal_id,
                'username': self.negdi_test_username,
                'password': self.negdi_test_password,
                'return_url': self.negdi_test_return_url,
                'api_url': self.negdi_test_api_url,
            }
        return {
            'terminal_id': self.negdi_terminal_id,
            'username': self.negdi_username,
            'password': self.negdi_password,
            'return_url': self.negdi_return_url,
            'api_url': self.negdi_api_url,
        }

    def negdi_create_order(self, transaction):
        credentials = self._get_negdi_credentials()
        url = f"{credentials['api_url']}/api/pay/ec1000"
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
            return response_data.get("negdiurl")
        return None