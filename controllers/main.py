from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class NegdiController(http.Controller):

    @http.route('/payment/negdi/webhook', type='json', auth='public', methods=['POST'])
    def negdi_webhook(self):
        """Endpoint to handle NEGDI webhook notifications."""
        data = request.jsonrequest
        _logger.info("NEGDI Webhook received data: %s", data)

        # Find the transaction
        tranid = data.get('order', {}).get('tranid')
        transaction = request.env['payment.transaction'].sudo().search([('negdi_tranid', '=', tranid)], limit=1)

        if not transaction:
            _logger.warning("NEGDI Webhook: Transaction not found for tranid %s", tranid)
            return {'success': False, 'message': 'Transaction not found'}

        try:
            transaction._process_feedback_data(data)
            return {'success': True}
        except Exception as e:
            _logger.exception("NEGDI Webhook: Error processing data: %s", e)
            return {'success': False, 'message': str(e)}

    @http.route('/payment/negdi/return', auth='public', methods=['GET', 'POST'], csrf=False)
    def negdi_return(self, **post):
        """Endpoint to handle NEGDI return."""
        _logger.info("NEGDI Return URL called with data: %s", post)

        tranid = post.get('tranid')
        transaction = request.env['payment.transaction'].sudo().search([('negdi_tranid', '=', tranid)], limit=1)

        if not transaction:
            _logger.warning("NEGDI Return: Transaction not found for tranid %s", tranid)
            return 'Transaction not found'

        try:
            transaction._process_feedback_data(post)
            return request.redirect('/payment/status')
        except Exception as e:
            _logger.exception("NEGDI Return: Error processing data: %s", e)
            return 'Error processing data'