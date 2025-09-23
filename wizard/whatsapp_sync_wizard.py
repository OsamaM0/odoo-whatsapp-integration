from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class WhatsAppSyncWizard(models.TransientModel):
    _name = 'whatsapp.sync.wizard'
    _description = 'WhatsApp Sync Wizard'
    
    sync_type = fields.Selection([
        ('contacts', 'Sync Contacts'),
        ('groups', 'Sync Groups'),
        ('messages', 'Sync Messages'),
        ('group_members', 'Sync Group Members'),
        ('all', 'Sync All'),
        ('custom', 'Custom Sync'),
    ], string='Sync Type', default='all', required=True)
    
    # Custom sync options
    sync_contacts = fields.Boolean('Sync Contacts', default=True)
    sync_groups = fields.Boolean('Sync Groups', default=True)
    sync_messages = fields.Boolean('Sync Messages', default=True)
    sync_group_members = fields.Boolean('Sync Group Members', default=True)
    auto_fetch_invite_codes = fields.Boolean('Auto-fetch Invite Codes', default=True, 
                                            help='Automatically fetch invite codes after group sync')
    
    # Progress tracking
    is_syncing = fields.Boolean('Is Syncing', default=False)
    progress = fields.Float('Progress', default=0.0)
    current_operation = fields.Char('Current Operation')
    
    # Results
    contacts_synced = fields.Integer('Contacts Synced', default=0)
    groups_synced = fields.Integer('Groups Synced', default=0)
    messages_synced = fields.Integer('Messages Synced', default=0)
    group_members_synced = fields.Integer('Group Members Synced', default=0)
    errors_count = fields.Integer('Errors Count', default=0)
    error_messages = fields.Text('Error Messages')
    
    def action_start_sync(self):
        """Start the sync process"""
        self.write({
            'is_syncing': True,
            'progress': 0.0,
            'current_operation': 'Starting sync...',
            'contacts_synced': 0,
            'groups_synced': 0,
            'messages_synced': 0,
            'group_members_synced': 0,
            'errors_count': 0,
            'error_messages': '',
        })
        
        # Call the actual sync method
        return self.sync_data()
    
    def sync_data(self):
        """Perform sync based on selected type with proper transaction handling"""
        # Check if user has access to any configuration
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if not config:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Access Denied',
                    'message': 'You do not have access to any WhatsApp configuration. Please contact your administrator.',
                    'type': 'danger',
                }
            }
        
        errors = []
        
        try:
            total_steps = 0
            current_step = 0
            
            # Calculate total steps
            if self.sync_type in ['contacts', 'all'] or (self.sync_type == 'custom' and self.sync_contacts):
                total_steps += 1
            if self.sync_type in ['groups', 'all'] or (self.sync_type == 'custom' and self.sync_groups):
                total_steps += 1
            if self.sync_type in ['messages', 'all'] or (self.sync_type == 'custom' and self.sync_messages):
                total_steps += 1
            if self.sync_type in ['group_members', 'all'] or (self.sync_type == 'custom' and self.sync_group_members):
                total_steps += 1
            
            # Sync contacts
            if self.sync_type in ['contacts', 'all'] or (self.sync_type == 'custom' and self.sync_contacts):
                current_step += 1
                self.write({
                    'current_operation': 'Syncing contacts...',
                    'progress': (current_step / total_steps) * 100
                })
                
                try:
                    # Use a separate transaction for each sync operation
                    with self.env.cr.savepoint():
                        result = self.env['whatsapp.contact'].sync_all_contacts_from_api()
                        if result.get('success'):
                            self.contacts_synced = result.get('count', 0)
                        else:
                            errors.append(f"Contacts sync: {result.get('message', 'Unknown error')}")
                            self.errors_count += 1
                except Exception as e:
                    # Log error and continue with next sync
                    _logger.error(f"Contacts sync error: {str(e)}")
                    errors.append(f"Contacts sync error: {str(e)}")
                    self.errors_count += 1
            
            # Sync groups
            if self.sync_type in ['groups', 'all'] or (self.sync_type == 'custom' and self.sync_groups):
                current_step += 1
                self.write({
                    'current_operation': 'Syncing groups...',
                    'progress': (current_step / total_steps) * 100
                })
                
                try:
                    with self.env.cr.savepoint():
                        synced_count = self.env['whatsapp.group'].sync_all_groups_from_api()
                        self.groups_synced = synced_count
                        
                        # Auto-fetch invite codes if enabled and groups were synced
                        if self.auto_fetch_invite_codes and synced_count > 0:
                            self.write({
                                'current_operation': 'Fetching invite codes...',
                            })
                            try:
                                invite_result = self.env['whatsapp.group']._auto_fetch_invite_codes()
                                _logger.info(f"Auto-fetched invite codes: {invite_result.get('message', 'Unknown result')}")
                            except Exception as invite_error:
                                _logger.error(f"Auto invite code fetch error: {invite_error}")
                                errors.append(f"Invite codes fetch error: {str(invite_error)}")
                        
                except Exception as e:
                    _logger.error(f"Groups sync error: {str(e)}")
                    errors.append(f"Groups sync error: {str(e)}")
                    self.errors_count += 1
            
            # Sync messages
            if self.sync_type in ['messages', 'all'] or (self.sync_type == 'custom' and self.sync_messages):
                current_step += 1
                self.write({
                    'current_operation': 'Syncing messages...',
                    'progress': (current_step / total_steps) * 100
                })
                
                try:
                    with self.env.cr.savepoint():
                        result = self.env['whatsapp.message'].sync_all_messages_from_api()
                        if result.get('success'):
                            self.messages_synced = result.get('count', 0)
                        else:
                            errors.append(f"Messages sync: {result.get('message', 'Unknown error')}")
                            self.errors_count += 1
                except Exception as e:
                    _logger.error(f"Messages sync error: {str(e)}")
                    errors.append(f"Messages sync error: {str(e)}")
                    self.errors_count += 1
            
            # Sync group members
            if self.sync_type in ['group_members', 'all'] or (self.sync_type == 'custom' and self.sync_group_members):
                current_step += 1
                self.write({
                    'current_operation': 'Syncing group members...',
                    'progress': (current_step / total_steps) * 100
                })
                
                try:
                    with self.env.cr.savepoint():
                        result = self.env['whatsapp.group'].sync_all_group_members_from_api()
                        if result.get('success'):
                            self.group_members_synced = result.get('count', 0)
                        else:
                            errors.append(f"Group members sync: {result.get('message', 'Unknown error')}")
                            self.errors_count += 1
                except Exception as e:
                    _logger.error(f"Group members sync error: {str(e)}")
                    errors.append(f"Group members sync error: {str(e)}")
                    self.errors_count += 1
            
            # Complete sync
            self.write({
                'is_syncing': False,
                'progress': 100.0,
                'current_operation': 'Sync completed',
                'error_messages': '\n'.join(errors) if errors else False,
            })
            
            if not errors:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Sync Complete',
                        'message': f'Synced {self.contacts_synced} contacts, {self.groups_synced} groups, {self.messages_synced} messages, {self.group_members_synced} group members',
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Sync Complete with Errors',
                        'message': f'Completed with {len(errors)} errors. Check the wizard for details.',
                        'type': 'warning',
                    }
                }
                
        except Exception as e:
            _logger.error(f"Sync wizard error: {str(e)}")
            self.write({
                'is_syncing': False,
                'error_messages': str(e),
                'errors_count': 1,
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync Failed',
                    'message': str(e),
                    'type': 'danger',
                }
            }
    
    def action_close(self):
        """Close the wizard"""
        return {'type': 'ir.actions.act_window_close'}
