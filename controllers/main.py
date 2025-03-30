import logging
import pprint

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class NegdiController(http.Controller):
    _return_url = '/payment/negdi/return'
    _webhook_url = '/payment/negdi/webhook'

    @http.route(_return_url, methods=['POST'], type='http', auth='public', csrf=False, save_session=False)
    def negdi_return(self, **data):
        """ Route called by NEGDI at the end of the transaction.
        
        he route is flagged with `save_session=False` to prevent Odoo from assigning a new session
        to the user if they are redirected to this route with a POST request. Indeed, as the session
        cookie is created without a `SameSite` attribute, some browsers that don't implement the
        recommended default `SameSite=Lax` behavior will not include the cookie in the redirection
        request from the payment provider to Odoo. As the redirection to the '/payment/status' page
        will satisfy any specification of the `SameSite` attribute, the session of the user will be
        retrieved and with it the transaction which will be immediately post-processed.
        
        :param dict data: The notification data.
        """

        _logger.info("Handling redirection from NEGDi with data:\n%s", pprint.pformat(data))

        try:
            tx = request.env['payment.transaction'].sudo()._get_tx_from_feedback_data('negdi', data)
            _logger.info("Transaction found: %s", tx)
        except Exception as e:
            _logger.exception("Exception raised when handling NEGDi feedback: %s", e)
            return request.redirect('/payment/process')  # Redirect to payment page in case oGoof error
        # TODO: Need to review again
        # Process the feedback data
        tx._process_feedback_data(data)

        # Redirect the user to the payment status page
        return request.redirect('/payment/status')
    
    # TODO: Need to review with aps webhook
    @http.route(_webhook_url, type='json', auth='public', methods=['POST'])
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