"""
Message Transformer
Handles transformation between DTOs and provider-specific formats
"""
import time
from typing import Dict, Any, List
from ..dto import MessageDTO, MediaMessageDTO
import logging

_logger = logging.getLogger(__name__)


class MessageTransformer:
    """Transforms messages between internal DTOs and provider formats"""
    
    @staticmethod
    def dto_to_whapi_request(message_dto: MessageDTO, media_dto: MediaMessageDTO = None) -> Dict[str, Any]:
        """Transform MessageDTO to WHAPI request format"""
        if media_dto:
            # Media message request
            endpoint = f'/messages/media/{media_dto.media_type}'
            
            # Create data URL for WHAPI
            import base64
            if isinstance(media_dto.media_data, bytes):
                base64_data = base64.b64encode(media_dto.media_data).decode('utf-8')
            else:
                base64_data = media_dto.media_data
            
            mime_type = media_dto.mime_type or MessageTransformer._get_mime_type(
                media_dto.media_type, media_dto.filename
            )
            data_url = f"data:{mime_type};name={media_dto.filename};base64,{base64_data}"
            
            return {
                'endpoint': endpoint,
                'params': {
                    'to': message_dto.chat_id,
                    'caption': media_dto.caption or message_dto.content
                },
                'json': {
                    'media': data_url,
                    'no_encode': False
                }
            }
        else:
            # Text message request
            return {
                'endpoint': '/messages/text',
                'json': {
                    'to': message_dto.chat_id,
                    'body': message_dto.content
                }
            }
    
    @staticmethod
    def dto_to_twilio_request(message_dto: MessageDTO, media_dto: MediaMessageDTO = None) -> Dict[str, Any]:
        """Transform MessageDTO to Twilio request format"""
        # Ensure phone number is in Twilio WhatsApp format
        to_number = message_dto.chat_id
        if not to_number.startswith('whatsapp:'):
            if not to_number.startswith('+'):
                to_number = '+' + to_number
            to_number = f'whatsapp:{to_number}'
        
        if media_dto:
            # Media message requires external URL for Twilio
            data = {
                'To': to_number,
                'Body': media_dto.caption or message_dto.content,
                'MediaUrl': media_dto.media_url  # Must be publicly accessible URL
            }
        else:
            # Text message
            data = {
                'To': to_number,
                'Body': message_dto.content
            }
        
        return {
            'endpoint': f'/Messages.json',
            'form_data': data
        }
    
    @staticmethod
    def whapi_response_to_dto(response_data: Dict[str, Any]) -> MessageDTO:
        """Transform WHAPI response to MessageDTO"""
        message_data = response_data.get('message', {})
        
        return MessageDTO(
            message_id=message_data.get('id', ''),
            content=message_data.get('body', ''),
            message_type=message_data.get('type', 'text'),
            chat_id=message_data.get('chat_id', ''),
            from_me=message_data.get('from_me', True),  # Outgoing message
            timestamp=message_data.get('timestamp', 0),
            status='sent' if response_data.get('sent') else 'failed',
            metadata=response_data
        )
    
    @staticmethod
    def twilio_response_to_dto(response_data: Dict[str, Any]) -> MessageDTO:
        """Transform Twilio response to MessageDTO"""
        # Map Twilio status to standard status
        twilio_status = response_data.get('status', 'unknown')
        status_mapping = {
            'queued': 'pending',
            'sending': 'pending',
            'sent': 'sent',
            'delivered': 'delivered',
            'undelivered': 'failed',
            'failed': 'failed'
        }
        
        return MessageDTO(
            message_id=response_data.get('sid', ''),
            content=response_data.get('body', ''),
            message_type='text',  # Twilio doesn't specify in response
            chat_id=response_data.get('to', '').replace('whatsapp:', ''),
            from_me=True,  # Outgoing message
            timestamp=MessageTransformer._parse_twilio_date(response_data.get('date_sent')),
            status=status_mapping.get(twilio_status, 'unknown'),
            metadata=response_data
        )
    
    @staticmethod
    def whapi_webhook_to_dto(webhook_data: Dict[str, Any]) -> List[MessageDTO]:
        """Transform WHAPI webhook to MessageDTO list"""
        messages = []
        
        for message_data in webhook_data.get('messages', []):
            # Skip outgoing messages
            if message_data.get('from_me', False):
                continue
            
            # Extract content based on message type
            message_type = message_data.get('type', 'text')
            content = MessageTransformer._extract_content_from_whapi(message_data, message_type)
            
            message_dto = MessageDTO(
                message_id=message_data.get('id', ''),
                content=content,
                message_type=message_type,
                chat_id=message_data.get('chat_id', ''),
                from_me=False,
                timestamp=message_data.get('timestamp', 0),
                sender_phone=message_data.get('from', ''),
                sender_name=message_data.get('from_name', ''),
                metadata=message_data
            )
            messages.append(message_dto)
        
        return messages
    
    @staticmethod
    def twilio_webhook_to_dto(webhook_data: Dict[str, Any]) -> List[MessageDTO]:
        """Transform Twilio webhook to MessageDTO list"""
        messages = []
        
        message_id = webhook_data.get('MessageSid', '')
        if not message_id:
            return messages
        
        # Skip outgoing messages (from our number)
        if webhook_data.get('From', '').endswith('your_twilio_number'):  # Replace with actual check
            return messages
        
        content = webhook_data.get('Body', '')
        message_type = 'text'
        
        # Check for media
        num_media = int(webhook_data.get('NumMedia', '0'))
        if num_media > 0:
            media_content_type = webhook_data.get('MediaContentType0', '')
            message_type = MessageTransformer._get_message_type_from_mime(media_content_type)
            
            if not content:
                content = f'{message_type.title()} message'
        
        message_dto = MessageDTO(
            message_id=message_id,
            content=content,
            message_type=message_type,
            chat_id=webhook_data.get('From', '').replace('whatsapp:', ''),
            from_me=False,
            timestamp=int(time.time()),
            sender_phone=webhook_data.get('From', '').replace('whatsapp:', ''),
            metadata=webhook_data
        )
        messages.append(message_dto)
        
        return messages
    
    @staticmethod
    def _extract_content_from_whapi(message_data: Dict, message_type: str) -> str:
        """Extract content from WHAPI message based on type"""
        if message_type == 'text':
            text_data = message_data.get('text', {})
            return text_data.get('body', '') if isinstance(text_data, dict) else str(text_data)
        elif message_type in ['image', 'video', 'audio', 'document', 'gif', 'voice']:
            media_data = message_data.get(message_type, {})
            if isinstance(media_data, dict):
                caption = media_data.get('caption', '')
                if caption:
                    return caption
                # For documents, try to get filename
                if message_type == 'document':
                    filename = media_data.get('filename', '')
                    if filename:
                        return f'Document: {filename}'
            return f'{message_type.title()} message'
        else:
            return f'{message_type.title()} message'
    
    @staticmethod
    def _get_mime_type(message_type: str, filename: str) -> str:
        """Get MIME type based on message type and filename"""
        mime_types = {
            'image': {
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                'default': 'image/jpeg'
            },
            'video': {'default': 'video/mp4'},
            'audio': {'default': 'audio/mpeg'},
            'document': {
                '.pdf': 'application/pdf',
                'default': 'application/octet-stream'
            }
        }
        
        if message_type in mime_types:
            type_map = mime_types[message_type]
            if filename:
                for ext, mime in type_map.items():
                    if ext != 'default' and filename.lower().endswith(ext):
                        return mime
            return type_map['default']
        
        return 'application/octet-stream'
    
    @staticmethod
    def _get_message_type_from_mime(mime_type: str) -> str:
        """Get message type from MIME type"""
        if mime_type.startswith('image/'):
            return 'image'
        elif mime_type.startswith('video/'):
            return 'video'
        elif mime_type.startswith('audio/'):
            return 'audio'
        else:
            return 'document'
    
    @staticmethod
    def _parse_twilio_date(date_str: str) -> int:
        """Parse Twilio date format to timestamp"""
        if not date_str:
            return 0
        
        try:
            from datetime import datetime
            import time
            # Twilio uses RFC 2822 format
            dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %z')
            return int(dt.timestamp())
        except Exception:
            return int(time.time())
