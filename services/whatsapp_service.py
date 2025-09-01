from odoo import models, api, fields
import logging
import base64
import mimetypes
import requests

_logger = logging.getLogger(__name__)

class WhatsAppService(models.AbstractModel):
    _name = 'whatsapp.service'
    _description = 'WhatsApp Management Service'
    
    @api.model
    def sync_all_groups(self):
        """Sync all groups with provider detection"""
        try:
            # Determine which service to use based on configuration
            config = self.env['whatsapp.configuration'].get_user_configuration()
            provider = config.provider if config else 'whapi'
            
            synced_count = self.env['whatsapp.group'].sync_all_groups_from_api(provider)
            return {
                'success': True,
                'message': f'Synced {synced_count} groups',
                'count': synced_count
            }
        except Exception as e:
            _logger.error(f"Error syncing groups: {e}")
            return {
                'success': False,
                'message': str(e),
                'count': 0
            }
    
    @api.model
    def create_group(self, name, description="", participant_phones=None):
        """Create new WhatsApp group with supervisor auto-added"""
        if participant_phones is None:
            participant_phones = []
        
        try:
            # Add supervisor phone if configured
            supervisor_phone = self.env['ir.config_parameter'].sudo().get_param('wassenger.supervisor_phone')
            if supervisor_phone and supervisor_phone not in participant_phones:
                participant_phones.append(supervisor_phone)
            
            # Create via API
            api_service = self.env['wassenger.api']
            api_result = api_service.create_group(name, participant_phones, description)
            
            # Create in database
            group = self.env['whatsapp.group'].create({
                'name': name,
                'group_id': api_result['id'],
                'wid': api_result.get('wid', ''),
                'device': api_result.get('device', ''),
                'description': description,
            })
            
            # Add participants
            for phone in participant_phones:
                contact = self._get_or_create_contact(phone)
                if contact:
                    group.write({'participant_ids': [(4, contact.id)]})
            
            return {
                'success': True,
                'group': group,
                'data': {
                    'id': group.id,
                    'group_id': group.group_id,
                    'wid': group.wid,
                    'name': group.name,
                    'description': group.description
                }
            }
        except Exception as e:
            _logger.error(f"Error creating group: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    @api.model
    def send_text_message(self, to, message, is_group=False, sender_phone=None):
        """Send text message using provider detection"""
        try:
            # Determine which service to use based on configuration
            config = self.env['whatsapp.configuration'].get_user_configuration()
            if config and config.provider == 'whapi':
                api_service = self.env['whapi.service']
            else:
                api_service = self.env['wassenger.api']
            
            # Get or create sender contact
            sender = None
            if sender_phone:
                sender = self.env['whatsapp.contact'].search([
                    '|', ('phone', '=', sender_phone), ('contact_id', '=', sender_phone)
                ], limit=1)
                if not sender:
                    sender = self.env['whatsapp.contact'].create({
                        'contact_id': sender_phone,
                        'phone': sender_phone if sender_phone.isdigit() else '',
                        'name': sender_phone,
                        'provider': config.provider if config else 'whapi',
                    })
            
            # Send via API based on provider
            if config and config.provider == 'whapi':
                # WHAPI service
                api_result = api_service.send_text_message(to, message)
            else:
                # Wassenger service (legacy)
                api_result = api_service.send_text_message(to, message, is_group)
            
            # Create message record using clean field mapping
            message_vals = {
                'content': message,
                'message_type': 'text',
                'status': 'sent' if (api_result.get('success') or api_result.get('sent')) else 'failed',
                'sent_at': fields.Datetime.now(),
                'direction': 'outbound',
                'provider': config.provider if config else 'whapi',
            }
            
            # Set message ID based on provider response
            if config and config.provider == 'whapi':
                message_vals['message_id'] = api_result.get('id', '') or api_result.get('message', {}).get('id', '')
                message_vals['chat_id'] = to
            else:
                message_vals['message_id'] = api_result.get('id', '')
            
            if sender:
                message_vals['sender_id'] = sender.id
            
            if is_group:
                group = self.env['whatsapp.group'].search([
                    '|', ('group_id', '=', to), ('wid', '=', to)
                ], limit=1)
                if group:
                    message_vals['group_id'] = group.id
            else:
                recipient = self._get_or_create_contact(to)
                if recipient:
                    message_vals['recipient_id'] = recipient.id
            
            message_record = self.env['whatsapp.message'].create(message_vals)
            
            return {
                'success': True,
                'message_id': message_record.message_id,
                'status': message_record.status,
                'sent_at': message_record.sent_at.isoformat() if message_record.sent_at else None
            }
        except Exception as e:
            _logger.error(f"Error sending message: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @api.model
    def send_media_message(self, to, media_data=None, filename=None, media_type="image", caption="", is_group=False, sender_phone=None):
        """Send media message using NEW APPROACH for WHAPI, legacy for Wassenger"""
        try:
            # Determine which service to use based on configuration
            config = self.env['whatsapp.configuration'].get_user_configuration()
            if config and config.provider == 'whapi':
                api_service = self.env['whapi.service']
            else:
                api_service = self.env['wassenger.api']
            
            # Get or create sender contact
            sender = None
            if sender_phone:
                sender = self._get_or_create_contact(sender_phone)
            
            # Send via API based on provider
            if config and config.provider == 'whapi':
                # WHAPI service - NEW APPROACH ONLY
                if not media_data or not filename:
                    return {'success': False, 'error': 'media_data and filename are required for WHAPI'}
                
                api_result = api_service.send_media_message(
                    to=to,
                    media_data=media_data,  # Base64 string
                    filename=filename,
                    message_type=media_type,
                    caption=caption
                )
            else:
                # Wassenger service (legacy) - keeping for backwards compatibility
                # This would use the old file_id/media_url approach
                return {'success': False, 'error': 'Wassenger legacy media sending not implemented in this update'}
            
            # Create message record with clean field mapping
            message_vals = {
                'content': caption,
                'message_type': media_type,
                'status': 'sent' if (api_result.get('success') or api_result.get('sent')) else 'failed',
                'sent_at': fields.Datetime.now(),
                'direction': 'outbound',
                'provider': config.provider if config else 'whapi',
            }
            
            # Set message ID based on provider response
            if config and config.provider == 'whapi':
                message_vals['message_id'] = api_result.get('message_id', '') or api_result.get('message', {}).get('id', '')
                message_vals['chat_id'] = to
            else:
                message_vals['message_id'] = api_result.get('id', '')
            
            if sender:
                message_vals['sender_id'] = sender.id
            
            if is_group:
                group = self.env['whatsapp.group'].search([
                    '|', ('group_id', '=', to), ('wid', '=', to)
                ], limit=1)
                if group:
                    message_vals['group_id'] = group.id
            else:
                recipient = self._get_or_create_contact(to)
                if recipient:
                    message_vals['recipient_id'] = recipient.id
            
            message_record = self.env['whatsapp.message'].create(message_vals)
            
            return {
                'success': True,
                'message_id': message_record.message_id,
                'status': message_record.status,
                'sent_at': message_record.sent_at.isoformat() if message_record.sent_at else None
            }
        except Exception as e:
            _logger.error(f"Error sending media message: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @api.model
    def remove_member_from_all_groups(self, phone_number):
        """Remove member from all groups using Odoo ORM with provider detection"""
        contact = self.env['whatsapp.contact'].search([
            '|', ('phone', '=', phone_number), ('contact_id', '=', phone_number)
        ], limit=1)
        
        if not contact:
            return {
                'success': False,
                'message': 'Contact not found',
                'groups_removed': 0
            }
        
        groups_removed = 0
        
        # Determine which service to use based on configuration
        config = self.env['whatsapp.configuration'].get_user_configuration()
        provider = config.provider if config else 'whapi'
        
        if provider == 'whapi':
            api_service = self.env['whapi.service']
        else:
            api_service = self.env['wassenger.api']
        
        # Get all groups this contact is member of
        groups = self.env['whatsapp.group'].search([('participant_ids', 'in', [contact.id])])
        
        for group in groups:
            try:
                # Remove from API based on provider
                if provider == 'whapi':
                    # For WHAPI, use group_id and contact_id
                    group_identifier = group.group_id or group.wid
                    contact_identifier = contact.contact_id or contact.phone
                    api_service.remove_group_participants(group_identifier, [contact_identifier])
                else:
                    # Wassenger service (legacy)
                    api_service.remove_group_participants(group.wid, [phone_number])
                
                # Remove from database using Odoo ORM
                group.write({'participant_ids': [(3, contact.id)]})
                groups_removed += 1
            except Exception as e:
                _logger.error(f"Error removing {phone_number} from group {group.name}: {e}")
        
        # Mark contact as inactive
        contact.write({'is_active': False})
        
        return {
            'success': True,
            'message': f"Removed {phone_number} from {groups_removed} groups",
            'groups_removed': groups_removed
        }
    
    @api.model
    def remove_member_from_selected_groups(self, contact_id, group_ids, deactivate_contact=False):
        """Remove member from selected groups with detailed results"""
        contact = self.env['whatsapp.contact'].browse(contact_id)
        groups = self.env['whatsapp.group'].browse(group_ids)
        
        if not contact.exists():
            return {
                'success': False,
                'message': 'Contact not found',
                'results': []
            }
        
        if not groups:
            return {
                'success': False,
                'message': 'No groups specified',
                'results': []
            }
        
        # Determine which service to use based on configuration
        config = self.env['whatsapp.configuration'].get_user_configuration()
        provider = config.provider if config else 'whapi'
        
        if provider == 'whapi':
            api_service = self.env['whapi.service']
        else:
            api_service = self.env['wassenger.api']
        
        results = []
        success_count = 0
        
        for group in groups:
            result = {
                'group_id': group.id,
                'group_name': group.name,
                'success': False,
                'message': ''
            }
            
            try:
                # Remove from API based on provider
                if provider == 'whapi':
                    # For WHAPI, use group_id and contact_id
                    group_identifier = group.group_id or group.wid
                    contact_identifier = contact.contact_id or contact.phone
                    api_service.remove_group_participants(group_identifier, [contact_identifier])
                else:
                    # Wassenger service (legacy)
                    phone_number = contact.phone or contact.contact_id
                    api_service.remove_group_participants(group.wid, [phone_number])
                
                # Remove from database using Odoo ORM
                group.write({'participant_ids': [(3, contact.id)]})
                
                result['success'] = True
                result['message'] = 'Successfully removed'
                success_count += 1
                
            except Exception as e:
                result['message'] = str(e)
                _logger.error(f"Error removing {contact.display_name} from group {group.name}: {e}")
            
            results.append(result)
        
        # Optionally deactivate the contact
        if deactivate_contact and success_count > 0:
            try:
                contact.write({'is_active': False})
            except Exception as e:
                _logger.error(f"Failed to deactivate contact {contact.display_name}: {e}")
        
        return {
            'success': success_count > 0,
            'message': f"Removed from {success_count} out of {len(groups)} groups",
            'success_count': success_count,
            'total_count': len(groups),
            'results': results
        }
    
    @api.model
    def remove_member_from_group(self, group_id, contact_phone):
        """Remove specific member from specific group using Odoo ORM with provider detection"""
        group = self.env['whatsapp.group'].browse(group_id)
        contact = self.env['whatsapp.contact'].search([
            '|', ('phone', '=', contact_phone), ('contact_id', '=', contact_phone)
        ], limit=1)
        
        if not group.exists() or not contact:
            return {
                'success': False,
                'message': 'Group or contact not found'
            }
        
        try:
            # Determine which service to use based on configuration
            config = self.env['whatsapp.configuration'].get_user_configuration()
            provider = config.provider if config else 'whapi'
            
            # Remove from API based on provider
            if provider == 'whapi':
                api_service = self.env['whapi.service']
                # For WHAPI, use group_id and contact_id
                group_identifier = group.group_id or group.wid
                contact_identifier = contact.contact_id or contact.phone
                api_service.remove_group_participants(group_identifier, [contact_identifier])
            else:
                # Wassenger service (legacy)
                api_service = self.env['wassenger.api']
                api_service.remove_group_participants(group.wid, [contact_phone])
            
            # Remove from database using Odoo ORM
            group.write({'participant_ids': [(3, contact.id)]})
            
            return {
                'success': True,
                'message': f'Removed {contact_phone} from group {group.name}'
            }
        except Exception as e:
            _logger.error(f"Error removing member from group: {e}")
            return {
                'success': False,
                'message': str(e)
            }
    
    def _get_or_create_contact(self, phone_or_id, name=None):
        """Get existing contact or create new one using clean field mapping"""
        # Try to find contact by phone or contact_id
        contact = self.env['whatsapp.contact'].search([
            '|', ('phone', '=', phone_or_id), ('contact_id', '=', phone_or_id)
        ], limit=1)
        
        if not contact:
            # Determine provider for new contacts
            config = self.env['whatsapp.configuration'].get_user_configuration()
            provider = config.provider if config else 'whapi'
            
            # Create new contact with clean field mapping
            contact_vals = {
                'contact_id': phone_or_id,
                'name': name or phone_or_id,
                'provider': provider,
                'isWAContact': True,
            }
            
            # Set phone field if the ID looks like a phone number
            if phone_or_id.isdigit():
                contact_vals['phone'] = phone_or_id
            
            contact = self.env['whatsapp.contact'].create(contact_vals)
        
        return contact
