import json
import requests
from odoo import http
from odoo.http import request

class NegdiController(http.Controller):
    @http.route('/payment/negdi/redirect', type='http', auth='public', methods=['POST'], csrf=False)
    def negdi_redirect(self, **post):
        transaction = request.env['payment.transaction'].sudo().browse(int(post.get('transaction_id')))
        payment_url = transaction.provider_id.negdi_create_order(transaction)
        if payment_url:
            return request.redirect(payment_url)
        return request.redirect('/shop/payment?error=negdi')

    @http.route('/payment/negdi/validate', type='json', auth='public')
    def negdi_validate(self, **post):
        transaction = request.env['payment.transaction'].sudo().search([
            ('reference', '=', post.get('ordernum'))
        ])
        if transaction:
            if post.get('status') == 'approved':
                transaction.sudo()._set_done()
            elif post.get('status') == 'cancelled':
                transaction.sudo()._set_canceled()
        return {'status': 'success'}