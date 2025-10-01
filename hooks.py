import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def post_init_hook(cr, registry):
    """
    Post-installation hook to initialize WhatsApp sync service and create cron jobs
    This ensures everything is set up automatically when the module is installed
    """
    try:
        with api.Environment.manage():
            env = api.Environment(cr, SUPERUSER_ID, {})
            
            # Initialize sync service record
            sync_service = env['whatsapp.sync.service'].search([], limit=1)
            if not sync_service:
                sync_service = env['whatsapp.sync.service'].create({
                    'name': 'WhatsApp Auto Sync Service'
                })
                _logger.info("WhatsApp Integration: Created sync service record")
            else:
                _logger.info("WhatsApp Integration: Sync service record already exists")
            
            # Create cron jobs programmatically to avoid XML compatibility issues
            _create_cron_jobs(env)
                
            _logger.info("WhatsApp Integration: Post-init hook completed successfully")
            
    except Exception as e:
        _logger.error(f"WhatsApp Integration: Post-init hook failed: {str(e)}")

def _create_cron_jobs(env):
    """Create WhatsApp cron jobs programmatically"""
    try:
        # Check if cron jobs already exist
        existing_crons = env['ir.cron'].search([
            ('name', 'in', ['WhatsApp Data Sync', 'WhatsApp Data Sync (Frequent)', 'WhatsApp Full Data Sync (Daily)'])
        ])
        
        if existing_crons:
            _logger.info(f"WhatsApp Integration: Found {len(existing_crons)} existing cron jobs, skipping creation")
            return existing_crons
        
        # Get model reference
        model_id = env['ir.model'].search([('model', '=', 'whatsapp.sync.service')], limit=1)
        if not model_id:
            _logger.error("WhatsApp Integration: Could not find whatsapp.sync.service model")
            return False
        
        # Get admin user (fallback to superuser if admin not found)
        admin_user = env.ref('base.user_admin', raise_if_not_found=False)
        if not admin_user:
            admin_user = env.ref('base.user_root', raise_if_not_found=False)
        
        if not admin_user:
            _logger.error("WhatsApp Integration: Could not find admin or root user")
            return False
        
        # Create hourly sync cron (active)
        hourly_cron = env['ir.cron'].create({
            'name': 'WhatsApp Data Sync',
            'model_id': model_id.id,
            'state': 'code',
            'code': 'model.cron_sync_all_data()',
            'interval_number': 1,
            'interval_type': 'hours',
            'numbercall': -1,
            'active': True,
            'user_id': admin_user.id,
            'doall': False,
        })
        _logger.info("WhatsApp Integration: Created hourly sync cron job")
        
        # Create frequent sync cron (inactive)
        frequent_cron = env['ir.cron'].create({
            'name': 'WhatsApp Data Sync (Frequent)',
            'model_id': model_id.id,
            'state': 'code',
            'code': 'model.cron_sync_all_data()',
            'interval_number': 30,
            'interval_type': 'minutes',
            'numbercall': -1,
            'active': False,
            'user_id': admin_user.id,
            'doall': False,
        })
        _logger.info("WhatsApp Integration: Created frequent sync cron job")
        
        # Create daily sync cron (inactive)
        daily_sync_code = """configs = env['whatsapp.configuration'].search([('active', '=', True)])
for config in configs:
    try:
        env['whatsapp.message'].sync_all_messages_from_api(count=200)
        env['whatsapp.contact'].sync_all_contacts_from_api()
        env['whatsapp.group'].sync_all_groups_from_api()
        env['whatsapp.group'].sync_all_group_members_from_api()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Daily sync error for config {config.name}: {str(e)}")"""
        
        daily_cron = env['ir.cron'].create({
            'name': 'WhatsApp Full Data Sync (Daily)',
            'model_id': model_id.id,
            'state': 'code',
            'code': daily_sync_code,
            'interval_number': 1,
            'interval_type': 'days',
            'numbercall': -1,
            'active': False,
            'user_id': admin_user.id,
            'doall': False,
        })
        _logger.info("WhatsApp Integration: Created daily sync cron job")
        
        _logger.info("WhatsApp Integration: Successfully created all 3 cron jobs")
        return hourly_cron + frequent_cron + daily_cron
        
    except Exception as e:
        _logger.error(f"WhatsApp Integration: Failed to create cron jobs: {str(e)}")
        return False