# Part of Odoo. See LICENSE file for full copyright and licensing details.

import hmac
import logging
import pprint

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import ValidationError, UserError
from odoo.http import request


_logger = logging.getLogger(__name__)


class NEGDiController(http.Controller):
    _return_url = '/payment/negdi/return'
    _webhook_url = '/payment/negdi/webhook'

    @http.route(_return_url, type='http', auth='public', methods=['GET'], csrf=False, save_session=False)
    def negdi_return_from_checkout(self, **kwargs):
        """ Handle the callback from NEGDi after payment attempt. """
        _logger.info("NEGDi: Handling return request with data:\n%s", pprint.pformat(kwargs))

        # Extract tranid and checkid from the GET parameters
        tranid = kwargs.get('tranid')
        checkid = kwargs.get('checkid')

        if not tranid or not checkid:
            _logger.warning("NEGDi: Received incomplete return data: %s", kwargs)
            # Redirect to a generic error or status page if data is missing
            return request.redirect('/payment/status?error=missing_data')

        try:
            # Find the Odoo transaction based on the provider_reference (tranid)
            # Use sudo() for access rights, as the user might not be logged in reliably
            tx_sudo = request.env['payment.transaction'].sudo().search([
                ('provider_reference', '=', tranid),
                ('provider_code', '=', 'negdi')
            ], limit=1)

            if not tx_sudo:
                _logger.warning("NEGDi: Transaction not found for tranid: %s", tranid)
                return request.redirect('/payment/status?error=tx_not_found')

            # Trigger the inquiry and feedback processing within the transaction model
            _logger.info("NEGDi: Found tx %s, initiating inquiry.", tx_sudo.reference)
            inquiry_response_data = tx_sudo._negdi_make_inquiry_request(check_id=checkid)
            _logger.info("NEGDi: Inquiry successful for tx %s, processing feedback.", tx_sudo.reference)
            tx_sudo._handle_feedback_data('negdi', inquiry_response_data)

        except (ValidationError, UserError) as e:
            # Log errors encountered during inquiry or processing
            _logger.error("NEGDi: Error processing return for tranid %s: %s", tranid, e)
            # Optionally pass error message to status page? Requires custom handling there.
            # return request.redirect(f'/payment/status?error={str(e.args[0])}')
            return request.redirect('/payment/status?error=processing_error')
        except Exception as e:
            _logger.exception("NEGDi: Unexpected error processing return for tranid %s.", tranid)
            return request.redirect('/payment/status?error=unexpected_error')

        # Redirect user to the generic payment status page
        # Odoo's JS on that page will fetch the final transaction state
        _logger.info("NEGDi: Redirecting user to /payment/status for tx %s", tx_sudo.reference if 'tx_sudo' in locals() and tx_sudo else tranid)
        return request.redirect('/payment/status')
    
    @http.route(_webhook_url, type='http', auth='public', methods=['POST'], csrf=False)
    def negdi_webhook(self, **data):
        """ Process the notification data sent by NEGDi to the webhook.

        See https://paymentservices-reference.payfort.com/docs/api/build/index.html#transaction-feedback.

        :param dict data: The notification data.
        :return: The 'SUCCESS' string to acknowledge the notification
        :rtype: str
        """
        _logger.info("Notification received from NEGDi with data:\n%s", pprint.pformat(data))
        try:
            # Check the integrity of the notification.
            tx_sudo = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                'negdi', data
            )
            # self._verify_notification_signature(data, tx_sudo)

            # Handle the notification data.
            tx_sudo._handle_notification_data('negdi', data)
        except ValidationError:  # Acknowledge the notification to avoid getting spammed.
            _logger.exception("Unable to handle the notification data; skipping to acknowledge.")

        return ''  # Acknowledge the notification.

    @staticmethod
    def _verify_notification_signature(notification_data, tx_sudo):
        """ Check that the received signature matches the expected one.

        :param dict notification_data: The notification data
        :param recordset tx_sudo: The sudoed transaction referenced by the notification data, as a
                                  `payment.transaction` record
        :return: None
        :raise: :class:`werkzeug.exceptions.Forbidden` if the signatures don't match
        """
        received_signature = notification_data.get('signature')
        if not received_signature:
            _logger.warning("received notification with missing signature")
            raise Forbidden()

        # Compare the received signature with the expected signature computed from the data.
        expected_signature = tx_sudo.provider_id._negdi_calculate_signature(
            notification_data, incoming=True
        )
        if not hmac.compare_digest(received_signature, expected_signature):
            _logger.warning("received notification with invalid signature")
            raise Forbidden()
