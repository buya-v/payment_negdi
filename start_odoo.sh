#!/bin/bash

# Activate the virtual environment
source /Users/buyanmunkhvolodya/odoo16/odoo-venv/bin/activate

# Navigate to the Odoo directory
cd /Users/buyanmunkhvolodya/odoo_development/odoo16/custom_addons/hotus

# Run the Odoo server with the configuration file
~/odoo16/odoo-bin -c odoo.conf -u payment_negdi --dev=reload
