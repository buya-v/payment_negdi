# payment_negdi/controllers/portal.py

import logging
import pprint
import requests
import json

# Import the specific error from the database driver library
try:
    import psycopg.errors as sql_errors # psycopg3
except ImportError:
    import psycopg2.errors as sql_errors # psycopg2

from odoo import http, _
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from odoo.fields import Command
from odoo.http import request
from odoo.tools import SQL

# Ensure this is the correct import for Odoo 18 website_sale payment controller
from odoo.addons.website_sale.controllers.payment import PaymentPortal

_logger = logging.getLogger(__name__)
_logger.info("***** NegdiPaymentPortal Controller File Loaded *****")


class NegdiPaymentPortal(PaymentPortal):

    @http.route('/shop/payment/transaction/<int:order_id>', type='json', auth='public', website=True)
    def shop_payment_transaction(self, order_id, access_token, **kwargs):
        """
        Override the e-commerce transaction processing route.
        Creates the transaction, then if the provider is NEGDi, calls the backend API
        and returns redirect URL. Otherwise, calls the original _get_processing_values.
        """
        _logger.info(">>> ENTERED NegdiPaymentPortal.shop_payment_transaction override for Order %s <<<", order_id)
        tx_sudo = None # Initialize tx_sudo
        try:
            # --- Start: Logic copied/adapted from original controller ---
            try:
                order_sudo = self._document_check_access('sale.order', order_id, access_token)
                request.env.cr.execute(
                    'SELECT 1 FROM sale_order WHERE id = %s FOR NO KEY UPDATE NOWAIT', [order_id]
                )
            except MissingError:
                _logger.warning("Shop payment failed for order %s: Order not found.", order_id)
                raise
            except AccessError as e:
                _logger.warning("Shop payment failed for order %s: Access Denied (%s).", order_id, e)
                raise ValidationError(_("The access token is invalid.")) from e
            except sql_errors.LockNotAvailable: # Use the imported alias
                _logger.warning("Shop payment failed for order %s: Order is already locked (concurrent payment attempt?).", order_id)
                raise UserError(_("Payment is already being processed for this order. Please wait or refresh."))

            if order_sudo.state == "cancel":
                _logger.warning("Shop payment failed for order %s: Order is cancelled.", order_id)
                raise ValidationError(_("The order has been cancelled."))

            order_sudo._check_cart_is_ready_to_be_paid()
            self._validate_transaction_kwargs(kwargs)

            kwargs.update({
                'partner_id': order_sudo.partner_invoice_id.id,
                'currency_id': order_sudo.currency_id.id,
                'sale_order_id': order_id,
            })
            if not kwargs.get('amount'):
                kwargs['amount'] = order_sudo.amount_total

            compare_amounts = order_sudo.currency_id.compare_amounts
            if compare_amounts(kwargs['amount'], order_sudo.amount_total):
                 _logger.warning("Amount mismatch for order %s.", order_id)
                 raise ValidationError(_("The cart has been updated. Please refresh the page."))
            if compare_amounts(order_sudo.amount_paid, order_sudo.amount_total) == 0 and order_sudo.amount_total > 0:
                 _logger.warning("Order %s already paid.", order_id)
                 raise UserError(_("The cart has already been paid. Please refresh the page."))

            if not kwargs.get('provider_id') or not kwargs.get('payment_method_id'):
                 _logger.error("Missing provider/method ID for order %s.", order_id)
                 raise ValidationError(_("Payment provider information is missing."))

            # *** Create the transaction ***
            tx_sudo = self._create_transaction(
                custom_create_values={'sale_order_ids': [Command.set([order_id])]}, **kwargs,
            )
            _logger.info("Created Transaction %s (ID: %s) for Order %s", tx_sudo.reference, tx_sudo.id, order_id)
            request.session['__website_sale_last_tx_id'] = tx_sudo.id
            # --- End: Logic copied/adapted from original controller ---

        except (AccessError, MissingError, UserError, ValidationError) as e:
             _logger.warning("Shop payment pre-processing error for order %s: %s", order_id, e)
             error_msg = e.args[0] if e.args else _("An error occurred during payment preparation.")
             return {'error': {'message': str(error_msg)}}
        except Exception as e:
             _logger.error("Unexpected pre-processing error for order %s: %s", order_id, e, exc_info=True)
             return {'error': {'message': _("An unexpected error occurred.")}}

        # --- Start: Provider-specific logic ---
        # Check provider *after* tx is created
        if tx_sudo and tx_sudo.provider_code == 'negdi':
            _logger.info("Processing NEGDi payment for Tx %s (%s)", tx_sudo.id, tx_sudo.reference)
            try:
                # Call the API request method defined in the transaction model
                negdi_url = tx_sudo._negdi_make_ec1000_request()
                # Return JSON with the key the frontend will check
                return {
                    'negdi_redirect_url': negdi_url, # Use the custom key
                }
            except ValidationError as e:
                _logger.warning("NEGDi API validation error for tx %s: %s", tx_sudo.id, e.args[0])
                # Error state already set in _negdi_make_ec1000_request
                return {'error': {'message': str(e.args[0])}}
            except Exception as e:
                _logger.error("NEGDi API unexpected error for tx %s: %s", tx_sudo.id, e, exc_info=True)
                # Error state already set in _negdi_make_ec1000_request
                return {'error': {'message': _("An unexpected error occurred while contacting the payment provider.")}}
        elif tx_sudo:
            # If not NEGDi, call the original _get_processing_values to get standard data
            _logger.info("Tx %s is not NEGDi, getting standard processing values", tx_sudo.id)
            return tx_sudo._get_processing_values()
        else:
             # Should not happen if transaction creation succeeded, but handle defensively
             _logger.error("Transaction object tx_sudo not available after creation for order %s", order_id)
             return {'error': {'message': _("Failed to initialize payment transaction.")}}
        # --- End: Provider-specific logic ---