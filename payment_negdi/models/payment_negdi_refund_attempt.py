# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class PaymentNegdiRefundAttempt(models.Model):
    """A refund whose outcome nobody knows, kept until a human has looked.

    The failure it guards against: the gateway is asked to send money back and
    the answer never arrives. Money may or may not have moved. Odoo rolls the
    refund back with the error, so without this record nothing remembers the
    attempt, the Refund button stays live, and the next click sends the money
    a second time.

    These rows are written on their own cursor, so the rollback of the failed
    refund cannot erase them, and while one is unresolved the payment refuses
    every further refund.
    """
    _name = 'payment.negdi.refund.attempt'
    _description = "NEGDI refund with an unknown outcome"
    _order = 'id desc'

    source_transaction_id = fields.Many2one(
        'payment.transaction', string="Payment", required=True, readonly=True,
        ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='source_transaction_id.currency_id')
    amount = fields.Monetary(readonly=True)
    rail = fields.Selection(
        [('ec1099', "Reversal (ec1099)"), ('ec1095', "Refund (ec1095)")],
        readonly=True, required=True)
    reason = fields.Text(readonly=True)
    resolution = fields.Selection(
        [('refunded', "Money was sent back"), ('not_refunded', "No money moved")],
        readonly=True)
    resolved_by_id = fields.Many2one('res.users', readonly=True)
    resolved_date = fields.Datetime(readonly=True)

    def _check_can_resolve(self):
        if any(self.mapped('resolution')):
            raise UserError(_("This refund attempt was already resolved."))
        # Whoever may refund this payment may also say what became of a refund.
        self.source_transaction_id.check_access('write')

    def _resolve(self, resolution):
        self.sudo().write({
            'resolution': resolution,
            'resolved_by_id': self.env.uid,
            'resolved_date': fields.Datetime.now(),
        })

    def action_mark_refunded(self):
        """NEGDI's portal shows the money went back: record it as a refund."""
        self._check_can_resolve()
        for attempt in self.sudo():
            source = attempt.source_transaction_id
            refund_tx = source._create_child_transaction(attempt.amount, is_refund=True)
            refund_tx._set_done(state_message=_(
                "Confirmed in NEGDI's portal by %(user)s after the gateway's answer was lost.",
                user=self.env.user.display_name))
            source._negdi_refund_confirmed_manually(attempt.amount)
        self._resolve('refunded')

    def action_mark_not_refunded(self):
        """NEGDI's portal shows no money moved: clear the way for a new refund."""
        self._check_can_resolve()
        self._resolve('not_refunded')
