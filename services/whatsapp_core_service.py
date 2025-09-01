"""
WhatsApp Core Service
Main orchestration service that provides a unified interface for WhatsApp operations
"""
import time
from typing import Dict, List, Optional, Any
from odoo import models, api, fields
from .whatsapp_provider_factory import WhatsAppProviderFactory
from .dto import MessageDTO, MediaMessageDTO, ContactDTO, GroupDTO
from .transformers import MessageTransformer
from ..constants import WHATSAPP_GROUP_SUFFIX
import logging

_logger = logging.getLogger(__name__)


class WhatsAppCoreService(models.AbstractModel):
    """Core WhatsApp service that orchestrates all operations"""
    
    _name = 'whatsapp.core.service'
    _description = 'WhatsApp Core Service'
    
    @api.model
    def send_text_message(self, to: str, message: str, user_id: int = None, **kwargs) -> Dict:
        """
        Send text message using configured provider
        
        Args:
            to: Recipient phone number or group ID
            message: Text message content
            user_id: User ID for configuration lookup
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Dict with success status and details
        """
        try:
            # Get provider for user
            provider = self._get_provider_for_user(user_id)
            if not provider:
                return {
                    'success': False,
                    'error': 'No WhatsApp provider configured'
                }
            
            # Validate inputs
            if not to or not message:
                return {
                    'success': False,
                    'error': 'Recipient and message are required'
                }
            
            # Send via provider
            start_time = time.time()
            result = provider.send_text_message(to, message, **kwargs)
            response_time = time.time() - start_time
            
            # Log the operation
            self._log_operation('send_text_message', result.get('success', False), 
                              response_time, provider.provider_name)
            
            # Save message to database if successful
            if result.get('success'):
                self._save_outgoing_message(
                    message_id=result.get('message_id', ''),
                    content=message,
                    recipient=to,
                    provider=provider.provider_name,
                    user_id=user_id
                )
            
            return result
            
        except Exception as e:
            _logger.error(f"Failed to send text message: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @api.model
    def send_media_message(self, to: str, media_data: bytes, filename: str, 
                          media_type: str = 'image', caption: str = '', 
                          user_id: int = None, **kwargs) -> Dict:
        """
        Send media message using configured provider
        
        Args:
            to: Recipient phone number or group ID
            media_data: Binary media data
            filename: Original filename
            media_type: Type of media (image, video, audio, document)
            caption: Media caption
            user_id: User ID for configuration lookup
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Dict with success status and details
        """
        try:
            # Get provider for user
            provider = self._get_provider_for_user(user_id)
            if not provider:
                return {
                    'success': False,
                    'error': 'No WhatsApp provider configured'
                }
            
            # Validate inputs
            if not to or not media_data or not filename:
                return {
                    'success': False,
                    'error': 'Recipient, media data, and filename are required'
                }
            
            # Create media DTO
            media_dto = MediaMessageDTO(
                media_data=media_data,
                filename=filename,
                media_type=media_type,
                caption=caption
            )
            
            # Send via provider
            start_time = time.time()
            result = provider.send_media_message(to, media_dto, **kwargs)
            response_time = time.time() - start_time
            
            # Log the operation
            self._log_operation('send_media_message', result.get('success', False),
                              response_time, provider.provider_name)
            
            # Save message to database if successful
            if result.get('success'):
                self._save_outgoing_message(
                    message_id=result.get('message_id', ''),
                    content=caption,
                    recipient=to,
                    provider=provider.provider_name,
                    message_type=media_type,
                    user_id=user_id
                )
            
            return result
            
        except Exception as e:
            _logger.error(f"Failed to send media message: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @api.model
    def create_group(self, name: str, participants: List[str], description: str = '', 
                    user_id: int = None, **kwargs) -> Dict:
        """
        Create WhatsApp group using configured provider
        
        Args:
            name: Group name
            participants: List of participant phone numbers
            description: Group description
            user_id: User ID for configuration lookup
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Dict with success status and group details
        """
        try:
            # Get provider for user
            provider = self._get_provider_for_user(user_id)
            if not provider:
                return {
                    'success': False,
                    'error': 'No WhatsApp provider configured'
                }
            
            # Validate inputs
            if not name or not participants:
                return {
                    'success': False,
                    'error': 'Group name and participants are required'
                }
            
            # Create group via provider
            start_time = time.time()
            result = provider.create_group(name, participants, description, **kwargs)
            response_time = time.time() - start_time
            
            # Log the operation
            self._log_operation('create_group', result.get('success', False),
                              response_time, provider.provider_name)
            
            # Save group to database if successful
            if result.get('success'):
                self._save_group(
                    group_id=result.get('group_id', ''),
                    name=name,
                    description=description,
                    participants=participants,
                    provider=provider.provider_name,
                    invite_link=result.get('invite_link'),
                    user_id=user_id
                )
            
            return result
            
        except Exception as e:
            _logger.error(f"Failed to create group: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @api.model
    def sync_contacts(self, user_id: int = None, **kwargs) -> Dict:
        """
        Sync contacts from provider
        
        Args:
            user_id: User ID for configuration lookup
            **kwargs: Additional parameters (limit, offset, etc.)
            
        Returns:
            Dict with sync results
        """
        try:
            # Get provider for user
            provider = self._get_provider_for_user(user_id)
            if not provider:
                return {
                    'success': False,
                    'error': 'No WhatsApp provider configured'
                }
            
            # Get contacts from provider
            start_time = time.time()
            result = provider.get_contacts(**kwargs)
            response_time = time.time() - start_time
            
            # Log the operation
            self._log_operation('sync_contacts', True, response_time, provider.provider_name)
            
            # Process and save contacts
            synced_count = 0
            if result.get('contacts'):
                for contact_dto in result['contacts']:
                    if self._save_contact(contact_dto, provider.provider_name):
                        synced_count += 1
            
            return {
                'success': True,
                'synced_count': synced_count,
                'total_available': result.get('total', synced_count)
            }
            
        except Exception as e:
            _logger.error(f"Failed to sync contacts: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @api.model
    def sync_groups(self, user_id: int = None, **kwargs) -> Dict:
        """
        Sync groups from provider
        
        Args:
            user_id: User ID for configuration lookup
            **kwargs: Additional parameters (limit, offset, etc.)
            
        Returns:
            Dict with sync results
        """
        try:
            # Get provider for user
            provider = self._get_provider_for_user(user_id)
            if not provider:
                return {
                    'success': False,
                    'error': 'No WhatsApp provider configured'
                }
            
            # Get groups from provider
            start_time = time.time()
            result = provider.get_groups(**kwargs)
            response_time = time.time() - start_time
            
            # Log the operation
            self._log_operation('sync_groups', True, response_time, provider.provider_name)
            
            # Process and save groups
            synced_count = 0
            if result.get('groups'):
                for group_dto in result['groups']:
                    if self._save_group_from_dto(group_dto, provider.provider_name):
                        synced_count += 1
            
            return {
                'success': True,
                'synced_count': synced_count,
                'total_available': result.get('total', synced_count)
            }
            
        except Exception as e:
            _logger.error(f"Failed to sync groups: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @api.model
    def process_webhook(self, provider_name: str, webhook_data: Dict, headers: Dict = None) -> Dict:
        """
        Process incoming webhook from provider
        
        Args:
            provider_name: Name of the provider sending webhook
            webhook_data: Webhook payload
            headers: HTTP headers
            
        Returns:
            Dict with processing results
        """
        try:
            # Get provider instance (use default config for webhook processing)
            factory = self.env['whatsapp.provider.factory']
            provider = factory.get_default_provider()
            
            if not provider or provider.provider_name != provider_name:
                return {
                    'success': False,
                    'error': f'No provider configured for {provider_name}'
                }
            
            # Validate webhook
            if not provider.validate_webhook(headers or {}, webhook_data):
                _logger.warning(f"Invalid webhook from {provider_name}")
                return {
                    'success': False,
                    'error': 'Webhook validation failed'
                }
            
            processed_messages = 0
            processed_statuses = 0
            
            # Process messages
            messages = provider.parse_webhook_message(webhook_data)
            for message_dto in messages:
                if self._save_incoming_message(message_dto, provider_name):
                    processed_messages += 1
            
            # Process status updates
            status_updates = provider.parse_webhook_status(webhook_data)
            for status_update in status_updates:
                if self._update_message_status(status_update):
                    processed_statuses += 1
            
            return {
                'success': True,
                'processed_messages': processed_messages,
                'processed_statuses': processed_statuses
            }
            
        except Exception as e:
            _logger.error(f"Failed to process webhook: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_provider_for_user(self, user_id: int = None) -> Optional:
        """Get provider instance for user"""
        try:
            factory = self.env['whatsapp.provider.factory']
            return factory.get_provider_for_user(user_id)
        except Exception as e:
            _logger.error(f"Failed to get provider for user {user_id}: {e}")
            return None
    
    def _save_outgoing_message(self, message_id: str, content: str, recipient: str, 
                              provider: str, message_type: str = 'text', user_id: int = None):
        """Save outgoing message to database"""
        try:
            message_vals = {
                'message_id': message_id,
                'content': content,
                'message_type': message_type,
                'chat_id': recipient,
                'from_me': True,
                'timestamp': int(time.time()),
                'status': 'sent',
                'direction': 'outbound',
                'provider': provider,
                'sent_at': fields.Datetime.now(),
            }
            
            # Find or create recipient contact
            if not recipient.endswith(WHATSAPP_GROUP_SUFFIX):  # Not a group
                contact = self._find_or_create_contact(recipient, provider)
                if contact:
                    message_vals['contact_id'] = contact.id
            else:  # Group message
                group = self._find_group(recipient, provider)
                if group:
                    message_vals['group_id'] = group.id
            
            self.env['whatsapp.message'].sudo().create(message_vals)
            
        except Exception as e:
            _logger.error(f"Failed to save outgoing message: {e}")
    
    def _save_incoming_message(self, message_dto: MessageDTO, provider: str) -> bool:
        """Save incoming message to database"""
        try:
            # Check if message already exists
            existing = self.env['whatsapp.message'].sudo().search([
                ('message_id', '=', message_dto.message_id)
            ], limit=1)
            
            if existing:
                return True  # Already processed
            
            message_vals = {
                'message_id': message_dto.message_id,
                'content': message_dto.content,
                'message_type': message_dto.message_type,
                'chat_id': message_dto.chat_id,
                'from_me': message_dto.from_me,
                'timestamp': message_dto.timestamp,
                'status': 'delivered',  # Incoming messages are delivered
                'direction': 'inbound',
                'provider': provider,
                'synced_at': fields.Datetime.now(),
                'metadata': str(message_dto.metadata) if message_dto.metadata else '',
            }
            
            # Handle contact/group relationships
            if message_dto.sender_phone:
                contact = self._find_or_create_contact(message_dto.sender_phone, provider, 
                                                     message_dto.sender_name)
                if contact:
                    message_vals['contact_id'] = contact.id
            
            if message_dto.chat_id.endswith(WHATSAPP_GROUP_SUFFIX):  # Group message
                group = self._find_or_create_group(message_dto.chat_id, provider)
                if group:
                    message_vals['group_id'] = group.id
            
            self.env['whatsapp.message'].sudo().create(message_vals)
            return True
            
        except Exception as e:
            _logger.error(f"Failed to save incoming message: {e}")
            return False
    
    def _save_contact(self, contact_dto: ContactDTO, provider: str) -> bool:
        """Save contact from DTO"""
        try:
            # Check if contact exists
            existing = self.env['whatsapp.contact'].sudo().search([
                ('contact_id', '=', contact_dto.contact_id),
                ('provider', '=', provider)
            ], limit=1)
            
            contact_vals = {
                'contact_id': contact_dto.contact_id,
                'phone': contact_dto.phone,
                'name': contact_dto.name,
                'pushname': contact_dto.pushname,
                'provider': provider,
                'isWAContact': contact_dto.is_whatsapp_user,
                'synced_at': fields.Datetime.now(),
            }
            
            if existing:
                existing.write(contact_vals)
            else:
                self.env['whatsapp.contact'].sudo().create(contact_vals)
            
            return True
            
        except Exception as e:
            _logger.error(f"Failed to save contact: {e}")
            return False
    
    def _find_or_create_contact(self, contact_id: str, provider: str, name: str = '') -> Optional:
        """Find or create contact"""
        try:
            contact = self.env['whatsapp.contact'].sudo().search([
                '|', 
                ('contact_id', '=', contact_id),
                ('phone', '=', contact_id)
            ], limit=1)
            
            if not contact:
                contact_vals = {
                    'contact_id': contact_id,
                    'phone': contact_id if contact_id.isdigit() else '',
                    'name': name,
                    'provider': provider,
                    'isWAContact': True,
                }
                contact = self.env['whatsapp.contact'].sudo().create(contact_vals)
            
            return contact
            
        except Exception as e:
            _logger.error(f"Failed to find/create contact: {e}")
            return None
    
    def _log_operation(self, operation: str, success: bool, response_time: float, 
                      provider: str, error: str = None):
        """Log operation for observability"""
        try:
            self.env['whatsapp.audit.log'].sudo().create({
                'operation': operation,
                'provider': provider,
                'success': success,
                'response_time': response_time,
                'error_message': error,
                'timestamp': fields.Datetime.now(),
                'user_id': self.env.user.id,
            })
        except Exception as e:
            # Don't fail operations due to logging issues
            _logger.warning(f"Failed to log operation: {e}")
    
    # Additional helper methods...
    def _save_group(self, group_id: str, name: str, description: str, 
                   participants: List[str], provider: str, invite_link: str = None, 
                   user_id: int = None):
        """Save group to database"""
        # Implementation similar to _save_contact
        pass
    
    def _save_group_from_dto(self, group_dto: GroupDTO, provider: str) -> bool:
        """Save group from DTO"""
        # Implementation for saving GroupDTO
        pass
    
    def _find_group(self, group_id: str, provider: str) -> Optional:
        """Find group by ID"""
        # Implementation for finding groups
        pass
    
    def _find_or_create_group(self, group_id: str, provider: str, name: str = '') -> Optional:
        """Find or create group"""
        # Implementation for finding/creating groups
        pass
    
    def _update_message_status(self, status_update: Dict) -> bool:
        """Update message status from webhook"""
        # Implementation for updating message status
        pass
