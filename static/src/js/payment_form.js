odoo.define('payment_negdi.payment_form', function (require) {
    "use strict";

    var PaymentForm = require('payment.payment_form');
    var core = require('web.core');

    var _t = core._t;
    PaymentForm.include({
        /**
         * @override
         * @param {string} providerCode
         * @param {jQuery} $paymentOption
         * @param {string} txContext
         */
        willStart: function () {
            var self = this;
            return this._super.apply(this, arguments);
        },

        _createInlineForm: function (providerCode, paymentOptionId, txContext) {
            if (providerCode !== 'negdi') {
                return this._super.apply(this, arguments);
            }

            // Here we can add javascript code for when the form is negdi

        },
    });
});