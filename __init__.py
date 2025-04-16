from . import controllers
from . import models

from odoo.addons.payment import setup_provider, reset_payment_provider
import logging

_logger = logging.getLogger(__name__)

def post_init_hook(env):
    _logger.info("Setting up NEGDi payment provider...")
    try:
        setup_provider(env, 'negdi')
    except Exception as e:
        env.cr.rollback()
        _logger.error(f"Error during post-init hook for NEGDi: {e}")

def uninstall_hook(env):
    _logger.info("Resetting NEGDi payment provider...")
    try:
        reset_payment_provider(env, 'negdi')
    except Exception as e:
        env.cr.rollback()
        _logger.error(f"Error during uninstall hook for NEGDi: {e}")
