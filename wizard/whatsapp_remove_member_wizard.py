from odoo import models, fields, api
import logging
from ..constants import PROVIDERS, PROVIDER_WHAPI, PROVIDER_WASSENGER

_logger = logging.getLogger(__name__)

class WhatsAppRemoveMemberWizard(models.TransientModel):
    _name = 'whatsapp.remove.member.wizard'
    _description = 'WhatsApp Remove Member Wizard'

    # Target user to remove
    contact_id = fields.Many2one('whatsapp.contact', string='Contact to Remove', required=True,
                                domain=[('isWAContact', '=', True)])
    phone_number = fields.Char('Phone Number', related='contact_id.phone', readonly=True)
    
    # Groups selection
    group_ids = fields.Many2many('whatsapp.group', 'whatsapp_remove_member_group_rel',
                                'wizard_id', 'group_id', string='Groups to Remove From',
                                domain=[('is_active', '=', True)])
    available_group_ids = fields.Many2many('whatsapp.group', string='Available Groups',
                                          compute='_compute_available_groups')
    
    # Options
    remove_from_all = fields.Boolean('Remove from All Groups', default=False,
                                    help='Remove the contact from all groups they are a member of')
    deactivate_contact = fields.Boolean('Deactivate Contact', default=True,
                                       help='Mark the contact as inactive after removal')
    
    # Information fields
    total_groups_count = fields.Integer('Total Groups', compute='_compute_group_counts')
    selected_groups_count = fields.Integer('Selected Groups', compute='_compute_group_counts')
    
    @api.depends('contact_id')
    def _compute_available_groups(self):
        """Compute groups where the contact is currently a member"""
        for wizard in self:
            if wizard.contact_id:
                # Find groups where this contact is a participant
                groups = self.env['whatsapp.group'].search([
                    ('participant_ids', 'in', [wizard.contact_id.id]),
                    ('is_active', '=', True)
                ])
                wizard.available_group_ids = groups
            else:
                wizard.available_group_ids = False
    
    @api.depends('available_group_ids', 'group_ids', 'remove_from_all')
    def _compute_group_counts(self):
        """Compute group counts for display"""
        for wizard in self:
            wizard.total_groups_count = len(wizard.available_group_ids)
            if wizard.remove_from_all:
                wizard.selected_groups_count = wizard.total_groups_count
            else:
                wizard.selected_groups_count = len(wizard.group_ids)
    
    @api.onchange('remove_from_all')
    def _onchange_remove_from_all(self):
        """When remove_from_all is checked, select all available groups"""
        if self.remove_from_all:
            self.group_ids = self.available_group_ids
        else:
            self.group_ids = False
    
    @api.onchange('contact_id')
    def _onchange_contact_id(self):
        """Reset group selection when contact changes"""
        self.group_ids = False
        self.remove_from_all = False
    
    def action_select_all_groups(self):
        """Action to select all available groups"""
        self.group_ids = self.available_group_ids
        self.remove_from_all = True
        return {'type': 'ir.actions.do_nothing'}
    
    def action_clear_selection(self):
        """Action to clear group selection"""
        self.group_ids = False
        self.remove_from_all = False
        return {'type': 'ir.actions.do_nothing'}
    
    def action_remove_member(self):
        """Remove the member from selected groups"""
        if not self.contact_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Please select a contact to remove',
                    'type': 'danger',
                }
            }
        
        # Determine which groups to remove from
        target_groups = self.available_group_ids if self.remove_from_all else self.group_ids
        
        if not target_groups:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Please select at least one group to remove the contact from',
                    'type': 'danger',
                }
            }
        
        try:
            # Implement the removal logic directly in the wizard
            # Determine which service to use based on configuration
            config = self.env['whatsapp.configuration'].get_user_configuration()
            provider = config.provider if config else PROVIDER_WHAPI
            
            if provider == PROVIDER_WHAPI:
                api_service = self.env['whapi.service']
            else:
                api_service = self.env['wassenger.api']
            
            results = []
            success_count = 0
            
            for group in target_groups:
                result = {
                    'group_id': group.id,
                    'group_name': group.name,
                    'success': False,
                    'message': ''
                }
                
                try:
                    # Remove from API based on provider
                    if provider == PROVIDER_WHAPI:
                        # For WHAPI, use group_id and contact_id
                        group_identifier = group.group_id or group.wid
                        contact_identifier = self.contact_id.contact_id or self.contact_id.phone
                        api_service.remove_group_participants(group_identifier, [contact_identifier])
                    else:
                        # Wassenger service (legacy)
                        phone_number = self.contact_id.phone or self.contact_id.contact_id
                        api_service.remove_group_participants(group.wid, [phone_number])
                    
                    # Remove from database using Odoo ORM
                    group.write({'participant_ids': [(3, self.contact_id.id)]})
                    
                    result['success'] = True
                    result['message'] = 'Successfully removed'
                    success_count += 1
                    
                except Exception as e:
                    result['message'] = str(e)
                    _logger.error(f"Error removing {self.contact_id.display_name} from group {group.name}: {e}")
                
                results.append(result)
            
            # Optionally deactivate the contact
            if self.deactivate_contact and success_count > 0:
                try:
                    self.contact_id.write({'is_active': False})
                except Exception as e:
                    _logger.error(f"Failed to deactivate contact {self.contact_id.display_name}: {e}")
            
            # Create a result object similar to the service method
            result = {
                'success': success_count > 0,
                'message': f"Removed from {success_count} out of {len(target_groups)} groups",
                'success_count': success_count,
                'total_count': len(target_groups),
                'results': results
            }
            
            # Prepare response based on results
            if result['success_count'] > 0 and result['success_count'] == result['total_count']:
                # Complete success
                message = f"Successfully removed {self.contact_id.name} from {result['success_count']} group(s)"
                if self.deactivate_contact:
                    message += " and deactivated the contact"
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success',
                        'message': message,
                        'type': 'success',
                    }
                }
            elif result['success_count'] > 0:
                # Partial success
                failed_count = result['total_count'] - result['success_count']
                message = f"Partially completed: removed from {result['success_count']} group(s), failed for {failed_count} group(s)"
                
                # Show details of failures
                failed_groups = [r for r in result.get('results', []) if not r['success']]
                if failed_groups:
                    message += f"\n\nFailed groups:\n"
                    for failure in failed_groups[:3]:  # Show first 3 failures
                        message += f"• {failure['group_name']}: {failure['message']}\n"
                    if len(failed_groups) > 3:
                        message += f"... and {len(failed_groups) - 3} more"
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Partial Success',
                        'message': message,
                        'type': 'warning',
                    }
                }
            else:
                # Complete failure
                message = f"Failed to remove {self.contact_id.name} from any groups"
                
                # Show details of failures
                failed_groups = result.get('results', [])
                if failed_groups:
                    message += f"\n\nErrors:\n"
                    for failure in failed_groups[:3]:  # Show first 3 failures
                        message += f"• {failure['group_name']}: {failure['message']}\n"
                    if len(failed_groups) > 3:
                        message += f"... and {len(failed_groups) - 3} more"
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': message,
                        'type': 'danger',
                    }
                }
                
        except Exception as e:
            _logger.error(f"Unexpected error in remove member wizard: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Unexpected error: {str(e)}',
                    'type': 'danger',
                }
            }
