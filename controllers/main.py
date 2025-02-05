from odoo import http
from odoo.http import request

class NegdiPaymentController(http.Controller):

    @http.route(['/payment/negdi/redirect'], type='http', auth='public', website=True)
    def negdi_redirect(self, **kw):
        reference = kw.get('reference')
        transaction = request.env['payment.transaction'].sudo().search([('reference', '=', reference)])
        if not transaction:
            return "Transaction not found"

        provider = transaction.provider_id
        if not provider:
            return "Provider not found"

        if not provider.negdi_payment(transaction, **kw):
            return "Payment Failed"

        return request.redirect('/payment/process/success') # Redirect to the success page

    # ... (negdi_callback remains if needed for server-to-server callbacks)