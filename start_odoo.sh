#!/bin/bash

# Activate the virtual environment
# source ~/odoo16/venv/bin/activate

# Navigate to the Odoo directory
# cd ~/odoo16/custom_addons/payment_negdi

# Run the Odoo server with the configuration file
~/odoo16/venv/bin/python3 ~/odoo16/odoo/odoo-bin -c odoo.conf -u payment_negdi --dev=reload
