#!/bin/bash

# Activate the virtual environment
source $ODOO_16_VENV/bin/activate

# Navigate to the Odoo directory
cd $ODOO_16_CUSTOM_ADDONS/payment_negdi

# Run the Odoo server with the configuration file
$ODOO_16_HOME/odoo-bin -c odoo.conf -u payment_negdi --dev=reload
