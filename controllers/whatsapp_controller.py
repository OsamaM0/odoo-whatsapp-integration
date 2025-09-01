import json
import logging
from odoo import http, fields
from odoo.http import request
from ..constants import PROVIDER_WHAPI, PROVIDER_WASSENGER, STATUS_SENT, STATUS_DELIVERED

_logger = logging.getLogger(__name__)

class WhatsAppController(http.Controller):
    
    @http.route('/api/whatsapp/groups', type='json', auth='user', methods=['GET'])
    def get_all_groups(self):
        """Get all WhatsApp groups with members"""
        try:
            groups = request.env['whatsapp.group'].search([('is_active', '=', True)])
            return [{
                'id': group.id,
                'group_id': group.group_id,
                'wid': group.wid,
                'name': group.name,
                'description': group.description,
                'member_count': len(group.member_ids),
                'members': [{'id': m.id, 'phone': m.phone, 'name': m.name} for m in group.member_ids]
            } for group in groups]
        except Exception as e:
            _logger.error(f"Error getting groups: {e}")
            return {'error': str(e)}
    
    @http.route('/api/whatsapp/groups/sync', type='json', auth='user', methods=['POST'])
    def sync_groups(self):
        """Sync groups from Wassenger API to database"""
        try:
            result = request.env['whatsapp.service'].sync_all_groups()
            return result
        except Exception as e:
            _logger.error(f"Error syncing groups: {e}")
            return {'error': str(e)}
    
    @http.route('/api/whatsapp/groups/create', type='json', auth='user', methods=['POST'])
    def create_group(self, name, description="", participants=None):
        """Create new WhatsApp group"""
        try:
            if participants is None:
                participants = []
            
            result = request.env['whatsapp.service'].create_group(
                name=name,
                description=description,
                participant_phones=participants
            )
            
            if result['success']:
                return result['data']
            else:
                return {'error': result['message']}
        except Exception as e:
            _logger.error(f"Error creating group: {e}")
            return {'error': str(e)}
    
    @http.route('/api/whatsapp/messages/send', type='json', auth='user', methods=['POST'])
    def send_message(self, to, message, is_group=False, sender_phone=None):
        """Send text message"""
        try:
            result = request.env['whatsapp.service'].send_text_message(
                to=to,
                message=message,
                is_group=is_group,
                sender_phone=sender_phone
            )
            
            if result['success']:
                return {
                    'message_id': result['message_id'],
                    'status': result['status'],
                    'sent_at': result['sent_at']
                }
            else:
                return {'error': result['error']}
        except Exception as e:
            _logger.error(f"Error sending message: {e}")
            return {'error': str(e)}
    
    @http.route('/api/whatsapp/messages/send-media', type='json', auth='user', methods=['POST'])
    def send_media_message(self, to, media_data, filename, media_type="image", caption="", is_group=False, sender_phone=None):
        """Send media message using NEW DATA URL APPROACH ONLY"""
        try:
            # Get configuration to determine provider
            config = request.env['whatsapp.configuration'].get_user_configuration()
            
            if config and config.provider == PROVIDER_WHAPI:
                # Use WHAPI with NEW approach
                api_service = request.env['whapi.service']
                result = api_service.send_media_message(
                    to=to,
                    media_data=media_data,  # Should be base64 string
                    filename=filename,
                    message_type=media_type,
                    caption=caption
                )
            else:
                # Use Wassenger (legacy)
                result = request.env['whatsapp.service'].send_media_message(
                    to=to,
                    media_url=None,  # Not used in new approach
                    caption=caption,
                    media_type=media_type,
                    is_group=is_group,
                    sender_phone=sender_phone
                )
            
            if result.get('success') or result.get('sent'):
                return {
                    'success': True,
                    'message_id': result.get('message_id', ''),
                    'status': STATUS_SENT,
                    'sent_at': fields.Datetime.now().isoformat()
                }
            else:
                return {
                    'success': False,
                    'error': result.get('message', 'Failed to send media message')
                }
        except Exception as e:
            _logger.error(f"Error sending media message: {e}")
            return {'success': False, 'error': str(e)}
    
    @http.route('/api/whatsapp/groups/<int:group_id>/members/<string:phone>/remove', type='json', auth='user', methods=['DELETE'])
    def remove_member_from_group(self, group_id, phone):
        """Remove member from specific group"""
        try:
            result = request.env['whatsapp.service'].remove_member_from_group(group_id, phone)
            return result
        except Exception as e:
            _logger.error(f"Error removing member from group: {e}")
            return {'error': str(e)}
    
    @http.route('/api/whatsapp/members/<string:phone_number>/remove-all', type='json', auth='user', methods=['DELETE'])
    def remove_member_from_all_groups(self, phone_number):
        """Remove member from all groups (for resigned employees)"""
        try:
            result = request.env['whatsapp.service'].remove_member_from_all_groups(phone_number)
            return result
        except Exception as e:
            _logger.error(f"Error removing member from all groups: {e}")
            return {'error': str(e)}
    
    @http.route('/api/whatsapp/contacts/sync', type='json', auth='user', methods=['POST'])
    def sync_contacts(self):
        """Sync contacts from Wassenger API"""
        try:
            result = request.env['whatsapp.contact'].sync_all_contacts_from_api()
            return result
        except Exception as e:
            _logger.error(f"Error syncing contacts: {e}")
            return {'error': str(e)}
    
    @http.route('/api/whatsapp/messages/sync', type='json', auth='user', methods=['POST'])
    def sync_messages(self, count=100, time_from=None, time_to=None, from_me=None, normal_types=False, sort='desc'):
        """Sync messages from WHAPI using messages/list with pagination. 
        
        Now syncs both incoming and outgoing messages regardless of from_me parameter.
        If time_from/time_to omitted, last 30 days are used."""
        try:
            result = request.env['whatsapp.message'].sync_all_messages_from_api(
                count=count,
                time_from=time_from,
                time_to=time_to,
                from_me=from_me,
                normal_types=normal_types,
                sort=sort,
            )
            return result
        except Exception as e:
            _logger.error(f"Error syncing messages: {e}")
            return {'error': str(e)}
    
    @http.route('/api/whatsapp/admin/database-status', type='json', auth='user', methods=['GET'])
    def get_database_status(self):
        """Get current database status and record counts"""
        try:
            return {
                'status': 'connected',
                'table_counts': {
                    'whatsapp_contacts': request.env['whatsapp.contact'].search_count([]),
                    'whatsapp_groups': request.env['whatsapp.group'].search_count([]),
                    'whatsapp_messages': request.env['whatsapp.message'].search_count([]),
                }
            }
        except Exception as e:
            return {'error': str(e)}
    
    @http.route('/api/whatsapp/health', type='http', auth='public', methods=['GET'])
    def health_check(self):
        """Health check endpoint"""
        return json.dumps({"status": "healthy", "service": "Wassenger WhatsApp Management API"})
