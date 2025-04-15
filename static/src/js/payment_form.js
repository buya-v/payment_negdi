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
        // Create a transaction and retrieve its processing values.
        await rpc(
            this.paymentContext['transactionRoute'],
            this._prepareTransactionRouteParams(),
        ).then(processingValues => { // The 'processingValues' dictionary is returned by the backend

             // <<< --- START: CHECK FOR BACKEND ERROR FIRST --- >>>
             if (processingValues.error && processingValues.error.message) {
                console.error("Payment processing error from backend:", processingValues.error.message);
                this._displayErrorDialog(
                    _t("Payment Error"),
                    processingValues.error.message
                );
                this._enableButton();
                return; // Stop processing on error
            }
            // <<< --- END: CHECK FOR BACKEND ERROR FIRST --- >>>


            // <<< --- START: ADD NEGDI CHECK --- >>>
            
            if (processingValues.negdi_redirect_url) { // Check for YOUR custom key
                console.log("NEGDi: Redirecting to:", processingValues.negdi_redirect_url);
                window.location.href = processingValues.negdi_redirect_url;
                return; // <- Stop processing this response further
            }
            // <<< --- END: ADD NEGDi CHECK --- >>>

            // --- Odoo's Standard Flow Handling ---
            if (flow === 'redirect') {
                // This part normally handles the redirect_form_html
                this._processRedirectFlow(
                    providerCode, paymentOptionId, paymentMethodCode, processingValues
                );
            } else if (flow === 'direct') {
                this._processDirectFlow(
                    providerCode, paymentOptionId, paymentMethodCode, processingValues
                );
            } else if (flow === 'token') {
                this._processTokenFlow(
                    providerCode, paymentOptionId, paymentMethodCode, processingValues
                );
            }
            // Add handling for potential backend errors passed in processingValues
            else if (processingValues.error) {
                 console.error("Payment processing error:", processingValues.error.message);
                 this._displayErrorDialog(
                      _t("Payment Error"),
                      processingValues.error.message || _t("An error occurred during payment processing.")
                 );
                 this._enableButton(); // Re-enable button on error
            }

        }).catch(error => { // Catch AJAX communication errors
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
