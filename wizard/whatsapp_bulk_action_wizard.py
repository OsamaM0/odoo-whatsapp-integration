from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class WhatsAppBulkActionWizard(models.TransientModel):
    _name = 'whatsapp.bulk.action.wizard'
    _description = 'WhatsApp Bulk Action Wizard'

    action_type = fields.Selection([
        ('bulk_sync', 'Sync Groups'),
        ('bulk_invite', 'Generate Invite Codes'),
        ('bulk_members', 'Update Members'),
    ], string='Action Type', required=True)
    
    group_ids = fields.Many2many('whatsapp.group', string='Selected Groups')
    
    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        
        # Get selected groups from context
        active_ids = self.env.context.get('active_ids', [])
        _logger.info(f"Bulk action wizard - active_ids from context: {active_ids}")
        
        if active_ids:
            res['group_ids'] = [(6, 0, active_ids)]
            _logger.info(f"Set group_ids to: {res['group_ids']}")
        
        # Get action type from context
        action_type = self.env.context.get('default_action_type')
        if action_type:
            res['action_type'] = action_type
            _logger.info(f"Set action_type to: {action_type}")
            
        _logger.info(f"Bulk wizard default_get result: {res}")
        return res
    
    def execute_action(self):
        """Execute the selected bulk action"""
        if not self.group_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Groups Selected',
                    'message': 'Please select groups to process',
                    'type': 'warning',
                }
            }
        
        try:
            _logger.info(f"Executing bulk action: {self.action_type} for {len(self.group_ids)} groups")
            
            if self.action_type == 'bulk_sync':
                result = self.group_ids.action_bulk_sync_groups()
            elif self.action_type == 'bulk_invite':
                result = self.group_ids.action_bulk_generate_invite_codes()
            elif self.action_type == 'bulk_members':
                result = self.group_ids.action_bulk_update_members()
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Unknown Action',
                        'message': f'Invalid action type selected: {self.action_type}',
                        'type': 'warning',
                    }
                }
            
            _logger.info(f"Bulk action result: {result}")
            return result
            
        except Exception as e:
            _logger.error(f"Error executing bulk action {self.action_type}: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Bulk Action Failed',
                    'message': f'Error executing {self.action_type}: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }