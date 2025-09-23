from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class GroupMemberDebugWizard(models.TransientModel):
    _name = 'group.member.debug.wizard'
    _description = 'Group Member Sync Debug Wizard'

    group_id = fields.Many2one('whatsapp.group', string='Group to Test', help='Select a group to test member sync')
    test_all = fields.Boolean('Test All Groups', default=False, help='Test all active groups')
    
    # Results fields
    debug_result = fields.Text('Debug Result', readonly=True)
    api_response = fields.Text('API Response', readonly=True)
    
    def action_test_group_sync(self):
        """Test group member sync and show debug information"""
        try:
            if self.test_all:
                # Test sync for all groups
                result = self.env['whatsapp.group'].test_group_member_sync_debug()
            else:
                # Test sync for specific group
                if not self.group_id:
                    self.debug_result = "Error: Please select a group to test"
                    return {'type': 'ir.actions.act_window_close'}
                
                result = self.env['whatsapp.group'].test_group_member_sync_debug(self.group_id.group_id)
            
            # Format results for display
            if 'error' in result:
                self.debug_result = f"Error: {result['error']}"
                self.api_response = ""
            else:
                debug_info = []
                debug_info.append(f"✅ Test completed successfully")
                debug_info.append(f"📊 Tested {len(result.get('results', []))} groups")
                
                for i, group_result in enumerate(result.get('results', []), 1):
                    debug_info.append(f"\n--- Group {i}: {group_result['group_name']} ---")
                    debug_info.append(f"Group ID: {group_result['group_id']}")
                    debug_info.append(f"API Response Type: {group_result['api_response_type']}")
                    debug_info.append(f"API Response Keys: {group_result['api_response_keys']}")
                    debug_info.append(f"Participants Found: {group_result['participants_found']}")
                    debug_info.append(f"Participants Count: {group_result['participants_count']}")
                    
                    if group_result.get('participants_field'):
                        debug_info.append(f"Participants Field: {group_result['participants_field']}")
                    
                    if group_result.get('sample_participant'):
                        debug_info.append(f"Sample Participant: {group_result['sample_participant']}")
                
                self.debug_result = "\n".join(debug_info)
                
                # Show full API response for first group
                if result.get('results'):
                    self.api_response = str(result['results'][0].get('full_response', 'No API response'))
            
            # Return action to show the wizard with results
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'group.member.debug.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'context': self.env.context,
            }
            
        except Exception as e:
            self.debug_result = f"❌ Test failed with error: {str(e)}"
            self.api_response = ""
            _logger.error(f"Group member debug test failed: {e}")
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'group.member.debug.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'context': self.env.context,
            }

    def action_run_actual_sync(self):
        """Run the actual group member sync"""
        try:
            result = self.env['whatsapp.group'].sync_all_group_members_from_api()
            
            # Force database commit
            self.env.cr.commit()
            
            # Refresh the group data to see changes
            if self.group_id:
                self.group_id.invalidate_cache()
                participant_count = len(self.group_id.participant_ids)
                self.debug_result = f"""
✅ Group Member Sync Completed

📊 Results:
- Synced Groups: {result.get('synced_count', 0)}
- Errors: {result.get('error_count', 0)}
- Message: {result.get('message', 'No message')}

📋 Group '{self.group_id.name}' now has {participant_count} participants
"""
            else:
                self.debug_result = f"""
✅ Group Member Sync Completed

📊 Results:
- Synced Groups: {result.get('synced_count', 0)}
- Errors: {result.get('error_count', 0)}
- Message: {result.get('message', 'No message')}

💡 Tip: Refresh your browser or go to WhatsApp > Groups to see the updated participant lists
"""
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'group.member.debug.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'context': self.env.context,
            }
            
        except Exception as e:
            self.debug_result = f"❌ Sync failed with error: {str(e)}"
            _logger.error(f"Group member sync failed: {e}")
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'group.member.debug.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'context': self.env.context,
            }

    def action_refresh_and_view_groups(self):
        """Refresh and show groups list"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'WhatsApp Groups',
            'res_model': 'whatsapp.group',
            'view_mode': 'tree,form',
            'target': 'current',
            'context': {'search_default_is_active': 1}
        }
