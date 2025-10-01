from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class WhatsAppSyncService(models.Model):
    _name = 'whatsapp.sync.service'
    _description = 'WhatsApp Sync Service for Automated Operations'
    
    name = fields.Char('Sync Service Name', default='WhatsApp Auto Sync')
    last_sync_time = fields.Datetime('Last Sync Time')
    sync_status = fields.Selection([
        ('idle', 'Idle'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('error', 'Error')
    ], string='Sync Status', default='idle')
    last_sync_message = fields.Text('Last Sync Message')

    @api.model
    def init_sync_service(self):
        """Initialize sync service record if it doesn't exist"""
        try:
            sync_service = self.search([], limit=1)
            if not sync_service:
                sync_service = self.create({
                    'name': 'WhatsApp Auto Sync Service'
                })
                _logger.info("Created WhatsApp sync service record")
            return sync_service
        except Exception as e:
            _logger.error(f"Failed to initialize sync service: {str(e)}")
            return False
    
    @api.model
    def cron_sync_all_data(self):
        """
        Cron job method to sync all WhatsApp data (contacts, groups, messages, group members)
        This method is called automatically by the scheduled action
        """
        try:
            _logger.info("Starting automated WhatsApp data sync")
            
            # Get all configurations and sync for each one
            configs = self.env['whatsapp.configuration'].search([('active', '=', True)])
            
            if not configs:
                _logger.warning("No active WhatsApp configurations found for sync")
                return
            
            total_contacts = 0
            total_groups = 0
            total_messages = 0
            total_group_members = 0
            errors = []
            
            for config in configs:
                try:
                    _logger.info(f"Syncing data for configuration: {config.name}")
                    
                    # For now, sync without specific context to avoid compatibility issues
                    sync_env = self.env
                    
                    # Sync contacts
                    try:
                        contact_result = sync_env['whatsapp.contact'].sync_all_contacts_from_api()
                        if contact_result.get('success'):
                            total_contacts += contact_result.get('count', 0)
                            _logger.info(f"Synced {contact_result.get('count', 0)} contacts for config {config.name}")
                        else:
                            errors.append(f"Config {config.name} - Contacts: {contact_result.get('message', 'Unknown error')}")
                    except Exception as e:
                        _logger.error(f"Error syncing contacts for config {config.name}: {str(e)}")
                        errors.append(f"Config {config.name} - Contacts error: {str(e)}")
                    
                    # Sync groups
                    try:
                        groups_synced = sync_env['whatsapp.group'].sync_all_groups_from_api()
                        total_groups += groups_synced
                        _logger.info(f"Synced {groups_synced} groups for config {config.name}")
                    except Exception as e:
                        _logger.error(f"Error syncing groups for config {config.name}: {str(e)}")
                        errors.append(f"Config {config.name} - Groups error: {str(e)}")
                    
                    # Sync messages
                    try:
                        message_result = sync_env['whatsapp.message'].sync_all_messages_from_api(count=50)
                        if message_result.get('success'):
                            total_messages += message_result.get('count', 0)
                            _logger.info(f"Synced {message_result.get('count', 0)} messages for config {config.name}")
                        else:
                            errors.append(f"Config {config.name} - Messages: {message_result.get('message', 'Unknown error')}")
                    except Exception as e:
                        _logger.error(f"Error syncing messages for config {config.name}: {str(e)}")
                        errors.append(f"Config {config.name} - Messages error: {str(e)}")
                    
                    # Sync group members
                    try:
                        member_result = sync_env['whatsapp.group'].sync_all_group_members_from_api()
                        if member_result.get('success'):
                            total_group_members += member_result.get('count', 0)
                            _logger.info(f"Synced {member_result.get('count', 0)} group members for config {config.name}")
                        else:
                            errors.append(f"Config {config.name} - Group members: {member_result.get('message', 'Unknown error')}")
                    except Exception as e:
                        _logger.error(f"Error syncing group members for config {config.name}: {str(e)}")
                        errors.append(f"Config {config.name} - Group members error: {str(e)}")
                        
                except Exception as e:
                    _logger.error(f"Error processing configuration {config.name}: {str(e)}")
                    errors.append(f"Config {config.name} - General error: {str(e)}")
            
            # Update sync service record
            sync_service = self.search([], limit=1)
            if not sync_service:
                sync_service = self.create({'name': 'WhatsApp Auto Sync'})
            
            status = 'success' if not errors else 'error'
            message = f"Synced {total_contacts} contacts, {total_groups} groups, {total_messages} messages, {total_group_members} group members"
            if errors:
                message += f"\nErrors ({len(errors)}):\n" + "\n".join(errors)
            
            sync_service.write({
                'last_sync_time': fields.Datetime.now(),
                'sync_status': status,
                'last_sync_message': message
            })
            
            _logger.info(f"Automated sync completed: {message}")
            
        except Exception as e:
            _logger.error(f"Critical error in automated sync: {str(e)}")
            # Try to update sync service with error
            try:
                sync_service = self.search([], limit=1)
                if not sync_service:
                    sync_service = self.create({'name': 'WhatsApp Auto Sync'})
                sync_service.write({
                    'last_sync_time': fields.Datetime.now(),
                    'sync_status': 'error',
                    'last_sync_message': f"Critical sync error: {str(e)}"
                })
            except:
                pass
    
    def manual_sync_all_data(self):
        """
        Manual trigger for sync (can be called from UI or directly)
        Returns action with notification
        """
        try:
            # Call the cron method
            self.cron_sync_all_data()
            
            sync_service = self.search([], limit=1)
            if sync_service and sync_service.sync_status == 'success':
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Sync Complete',
                        'message': sync_service.last_sync_message,
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Sync Completed with Errors',
                        'message': sync_service.last_sync_message if sync_service else 'Unknown error occurred',
                        'type': 'warning',
                    }
                }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync Failed',
                    'message': str(e),
                    'type': 'danger',
                }
            }

    def check_cron_status(self):
        """Check the status of WhatsApp cron jobs"""
        try:
            cron_jobs = self.env['ir.cron'].search([
                ('name', 'in', ['WhatsApp Data Sync', 'WhatsApp Data Sync (Frequent)', 'WhatsApp Full Data Sync (Daily)'])
            ])
            
            if not cron_jobs:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'No Cron Jobs Found',
                        'message': 'WhatsApp cron jobs are not installed. Please upgrade the module.',
                        'type': 'warning',
                    }
                }
            
            active_jobs = cron_jobs.filtered('active')
            message = f"Found {len(cron_jobs)} cron jobs, {len(active_jobs)} active:\n"
            for job in cron_jobs:
                status = "ACTIVE" if job.active else "INACTIVE"
                message += f"• {job.name} [{status}] - Next: {job.nextcall}\n"
                
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Cron Jobs Status',
                    'message': message,
                    'type': 'info',
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error Checking Cron Status',
                    'message': str(e),
                    'type': 'danger',
                }
            }