import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def post_init_hook(cr, registry):
    """
    Post-installation hook to initialize WhatsApp sync service
    This ensures the sync service record is created automatically when the module is installed
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
            
            # Verify cron jobs are installed
            cron_jobs = env['ir.cron'].search([
                ('name', 'in', ['WhatsApp Data Sync', 'WhatsApp Data Sync (Frequent)', 'WhatsApp Full Data Sync (Daily)'])
            ])
            
            if cron_jobs:
                _logger.info(f"WhatsApp Integration: Found {len(cron_jobs)} cron jobs")
                for job in cron_jobs:
                    status = "ACTIVE" if job.active else "INACTIVE"
                    _logger.info(f"  - {job.name} [{status}]")
            else:
                _logger.warning("WhatsApp Integration: No cron jobs found - they should be created by XML data")
                
            _logger.info("WhatsApp Integration: Post-init hook completed successfully")
            
    except Exception as e:
        _logger.error(f"WhatsApp Integration: Post-init hook failed: {str(e)}")