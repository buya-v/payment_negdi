from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class NegdiController(http.Controller):
    _return_url = '/payment/negdi/return'

    @http.route(_return_url, methods=['GET', 'POST'], type='http', auth='public', csrf=False)
    def negdi_return(self, **data):
        """ Route called by NEGDI at the end of the transaction. """
        _logger.info("Entering negdi_return with data: %s", data)

        try:
            tx = request.env['payment.transaction'].sudo()._get_tx_from_feedback_data('negdi', data)
            _logger.info("Transaction found: %s", tx)
        except Exception as e:
            _logger.exception("Exception raised when handling NEGDi feedback: %s", e)
            return request.redirect('/payment/process')  # Redirect to payment page in case of error
        # Process the feedback data
        tx._process_feedback_data(data)

        # Redirect the user to the payment status page
        return request.redirect('/payment/status')

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