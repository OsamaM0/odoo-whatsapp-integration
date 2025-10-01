from odoo import models, fields, api
import logging
import base64
from ..constants import MESSAGE_TYPES, PROVIDERS, PROVIDER_WHAPI, PROVIDER_WASSENGER, STATUS_SENT

_logger = logging.getLogger(__name__)

class WhatsAppSendMessageWizard(models.TransientModel):
    _name = 'whatsapp.send.message.wizard'
    _description = 'WhatsApp Send Message Wizard'

    message_type = fields.Selection([
        ('text', 'Text Message'),
        ('media', 'Media Message'),
    ], string='Message Type', default='text', required=True)
    
    # Recipients
    recipient_id = fields.Many2one('whatsapp.contact', string='Contact')
    group_id = fields.Many2one('whatsapp.group', string='Group')
    group_ids = fields.Many2many('whatsapp.group', string='Multiple Groups')
    phone = fields.Char('Phone Number')
    is_bulk = fields.Boolean('Bulk Message', default=False)
    
    # Message content
    message = fields.Text('Message', required=True)
    media_file = fields.Binary('Media File', help='Upload media file (image, video, document, etc.)')
    media_file_name = fields.Char('File Name')
    media_caption = fields.Text('Media Caption')
    
    # Options
    preview_url = fields.Boolean('Preview URL', default=True)
    
    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        
        # Handle bulk message context
        if self.env.context.get('default_is_bulk') and self.env.context.get('active_ids'):
            active_ids = self.env.context.get('active_ids', [])
            res['group_ids'] = [(6, 0, active_ids)]
            res['is_bulk'] = True
        
        return res
    
    @api.onchange('recipient_id')
    def _onchange_recipient_id(self):
        if self.recipient_id:
            self.phone = self.recipient_id.phone or self.recipient_id.contact_id
    
    def send_message(self):
        """Send WhatsApp message with provider detection and bulk support"""
        try:
            # Handle bulk messages to multiple groups
            if self.is_bulk and self.group_ids:
                return self._send_bulk_messages()
            
            # Original single message logic
            # Determine which service to use based on configuration
            config = self.env['whatsapp.configuration'].get_user_configuration()
            if config and config.provider == PROVIDER_WHAPI:
                api_service = self.env['whapi.service']
            else:
                api_service = self.env['wassenger.api']
            
            # Determine recipient
            recipient_phone = self.phone
            if self.recipient_id:
                recipient_phone = self.recipient_id.phone or self.recipient_id.contact_id
            elif self.group_id:
                recipient_phone = self.group_id.group_id if config and config.provider == PROVIDER_WHAPI else self.group_id.wid
            
            if not recipient_phone:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': 'No recipient specified',
                        'type': 'danger',
                    }
                }
            
            # Send single message using existing logic
            return self._send_single_message(api_service, config, recipient_phone)
                
        except Exception as e:
            _logger.error("Error sending WhatsApp message: %s", str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': str(e),
                    'type': 'danger',
                }
            }

    def _send_bulk_messages(self):
        """Send messages to multiple groups"""
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if config and config.provider == PROVIDER_WHAPI:
            api_service = self.env['whapi.service']
        else:
            api_service = self.env['wassenger.api']
        
        success_count = 0
        error_count = 0
        
        for group in self.group_ids:
            try:
                # Get group identifier
                recipient_phone = group.group_id if config and config.provider == PROVIDER_WHAPI else group.wid
                
                if not recipient_phone:
                    error_count += 1
                    continue
                
                # Send message using single message logic
                result = self._send_message_to_recipient(api_service, config, recipient_phone, group)
                
                if result.get('success') or result.get('sent'):
                    success_count += 1
                else:
                    error_count += 1
                
                # Small delay to avoid rate limiting
                import time
                time.sleep(0.3)
                
            except Exception as e:
                _logger.error(f"Failed to send message to group {group.name}: {e}")
                error_count += 1
                continue
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Bulk Message Complete',
                'message': f'Sent messages to {success_count} groups. {error_count} failed.',
                'type': 'success' if success_count > 0 else 'warning',
                'sticky': True,
            }
        }

    def _send_single_message(self, api_service, config, recipient_phone):
        """Send message to single recipient"""
        result = self._send_message_to_recipient(api_service, config, recipient_phone, self.group_id)
        
        if result.get('success') or result.get('sent'):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': 'Message sent successfully',
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': result.get('message', 'Failed to send message'),
                    'type': 'danger',
                }
            }

    def _send_message_to_recipient(self, api_service, config, recipient_phone, target_group=None):
        """Core logic to send message to a specific recipient"""
        # Determine media type if sending media
        detected_media_type = 'text'  # Default
        if self.message_type == 'media':
            if self.media_file_name:
                # Detect media type from filename
                lower_name = self.media_file_name.lower()
                if any(ext in lower_name for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']):
                    detected_media_type = 'image'
                elif any(ext in lower_name for ext in ['.mp4', '.avi', '.mov', '.webm']):
                    detected_media_type = 'video'
                elif any(ext in lower_name for ext in ['.mp3', '.wav', '.ogg', '.m4a']):
                    detected_media_type = 'audio'
                else:
                    detected_media_type = 'document'
                
                _logger.info(f"Detected media type: {detected_media_type} from filename: {self.media_file_name}")
            else:
                # No filename, default to document
                detected_media_type = 'document'
                _logger.warning("Media message without filename, defaulting to document type")

        # Send message based on provider and type
        if config and config.provider == PROVIDER_WHAPI:
            # WHAPI service - NEW APPROACH ONLY
            if self.message_type == 'text':
                result = api_service.send_text_message(recipient_phone, self.message)
            else:  # media
                if not self.media_file:
                    raise Exception('Please select a media file')
                
                # Convert binary data to base64 string for the NEW data URL approach
                # Odoo Binary fields are already base64-encoded strings
                media_base64 = self.media_file
                
                if not media_base64:
                    raise Exception('Invalid media file data')
                
                # Send media message using NEW APPROACH (data URL format)
                result = api_service.send_media_message(
                    recipient_phone, 
                    media_base64,  # Base64 string, not bytes
                    self.media_file_name,
                    detected_media_type,  # Use local variable
                    self.media_caption or self.message
                )
        else:
            # Wassenger service (legacy) - keeping for backwards compatibility
            if target_group or self.group_id:
                # Send to group
                if self.message_type == 'text':
                    result = api_service.send_group_message(recipient_phone, self.message)
                else:  # media
                    if not self.media_file:
                        raise Exception('Please select a media file')
                    
                    # Upload file first (Wassenger legacy approach)
                    file_result = api_service.upload_file(self.media_file, self.media_file_name)
                    if not file_result.get('success'):
                        raise Exception(f"Failed to upload file: {file_result.get('message', 'Unknown error')}")
                    
                    result = api_service.send_group_message(recipient_phone, self.media_caption or self.message, file_id=file_result['file_id'])
            else:
                # Send to individual
                if self.message_type == 'text':
                    result = api_service.send_text_message(recipient_phone, self.message, self.preview_url)
                else:  # media
                    if not self.media_file:
                        raise Exception('Please select a media file')
                    
                    # Upload file first (Wassenger legacy approach)
                    file_result = api_service.upload_file(self.media_file, self.media_file_name)
                    if not file_result.get('success'):
                        raise Exception(f"Failed to upload file: {file_result.get('message', 'Unknown error')}")
                    
                    result = api_service.send_media_message(recipient_phone, file_id=file_result['file_id'], caption=self.media_caption or self.message)
        
        if result.get('success') or result.get('sent'):
            # Create message record with clean field mapping
            # Use detected media type for database record
            actual_message_type = detected_media_type if self.message_type == 'media' else 'text'
            _logger.info(f"Creating message record - actual_message_type: {actual_message_type}, original message_type: {self.message_type}")
                
            message_vals = {
                'body': self.message,
                'message_type': actual_message_type,  # Use detected type (image/video/audio/document)
                'status': STATUS_SENT,
                'from_me': True,
                'timestamp': int(fields.Datetime.now().timestamp()),
                'provider': config.provider if config else PROVIDER_WHAPI,
            }
            
            # Set message ID based on provider response format
            if config and config.provider == PROVIDER_WHAPI:
                message_vals['message_id'] = result.get('id', '') or result.get('message', {}).get('id', '')
            else:
                message_vals['message_id'] = result.get('id', '')
            
            # Set media fields if applicable
            if self.message_type == 'media':
                message_vals.update({
                    'caption': self.media_caption,
                    'media_type': actual_message_type,  # Use specific type (image/video/etc)
                })
            
            # Set recipient based on message target
            if target_group or self.group_id:
                message_vals['group_id'] = (target_group or self.group_id).id
                # For WHAPI, also set chat_id
                if config and config.provider == PROVIDER_WHAPI:
                    message_vals['chat_id'] = (target_group or self.group_id).group_id
            else:
                message_vals['contact_id'] = self.recipient_id.id if self.recipient_id else False
                # For WHAPI, also set chat_id 
                if config and config.provider == PROVIDER_WHAPI:
                    message_vals['chat_id'] = recipient_phone
            
            self.env['whatsapp.message'].create(message_vals)
        
        return result
