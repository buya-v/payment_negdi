/** @odoo-module **/
/* global NegdiCheckout */

import { _t } from '@web/core/l10n/translation';
import { pyToJsLocale } from '@web/core/l10n/utils';
import paymentForm from '@payment/js/payment_form';
import { rpc, RPCError } from '@web/core/network/rpc';

paymentForm.include({


    // #=== DOM MANIPULATION ===#

    /**
     * Prepare the inline form of Adyen for direct payment.
     *
     * @override method from payment.payment_form
     * @private
     * @param {number} providerId - The id of the selected payment option's provider.
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The online payment flow of the selected payment option
     * @return {void}
     */
    

    // #=== PAYMENT FLOW ===#

    async _initiatePaymentFlow(providerCode, paymentOptionId, paymentMethodCode, flow) {
        await rpc(
            this.paymentContext['transactionRoute'],
            this._prepareTransactionRouteParams(),
        ).then(processingValues => {
            console.log("Processing values received from backend:", processingValues);

            // Check for backend errors
            if (processingValues.error && processingValues.error.message) {
                console.error("Payment processing error from backend:", processingValues.error.message);
                this._displayErrorDialog(
                    _t("Payment Error"),
                    processingValues.error.message
                );
                this._enableButton();
                return;
            }

            // Handle NEGDi-specific redirection
            if (processingValues.negdi_redirect_url) {
                console.log("NEGDi: Redirecting to:", processingValues.negdi_redirect_url);
                try {
                    if (processingValues.negdi_redirect_url.startsWith('https://')) {
                        window.top.location.assign(processingValues.negdi_redirect_url); // Redirect in top-level window
                    } else {
                        throw new Error("Invalid redirect URL");
                    }
                } catch (error) {
                    console.error("Redirection failed:", error);
                    this._displayErrorDialog(
                        _t("Redirection Error"),
                        _t("Failed to redirect to the payment provider. Please try again.")
                    );
                }
                return;
            }

            // Handle Odoo's standard payment flows
            if (flow === 'redirect') {
                this._processRedirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues);
            } else if (flow === 'direct') {
                this._processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues);
            } else if (flow === 'token') {
                this._processTokenFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues);
            } else if (processingValues.error) {
                console.error("Payment processing error:", processingValues.error.message);
                this._displayErrorDialog(
                    _t("Payment Error"),
                    processingValues.error.message || _t("An error occurred during payment processing.")
                );
                this._enableButton();
            }
        }).catch(error => {
            console.error("Payment RPC failed:", error);
            if (error instanceof RPCError) {
                this._displayErrorDialog(
                    _t("Payment processing failed"),
                    error.data?.message || error.message || _t("An unknown server error occurred.")
                );
            } else {
                this._displayErrorDialog(
                    _t("Error"),
                    _t("Could not connect to the payment server. Please check your connection and try again.")
                );
            }
            this._enableButton();
        });
    },

    

});
