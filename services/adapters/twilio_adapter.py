"""
Twilio WhatsApp Provider Adapter
Implements the IWhatsAppProvider interface for Twilio WhatsApp Business API
This is a hypothetical implementation showing how to map different request/response schemas
"""
import requests
import json
import logging
import base64
import time
from typing import Dict, List, Optional, Union
from odoo import models, api, fields
from .base_adapter import BaseWhatsAppAdapter
from ..dto import MessageDTO, MediaMessageDTO, ContactDTO, GroupDTO, GroupParticipantDTO
from ...constants import API_TIMEOUT_SHORT, API_TIMEOUT_LONG, MIME_TYPES

_logger = logging.getLogger(__name__)


class TwilioAdapter(BaseWhatsAppAdapter):
    """Twilio WhatsApp Provider Adapter"""
    
    _name = 'whatsapp.adapter.twilio'
    _description = 'Twilio WhatsApp Adapter'
    
    def __init__(self, env, config: Dict):
        super().__init__(env, config)
        self.base_url = "https://api.twilio.com/2010-04-01"
        self.account_sid = config.get('account_sid')
        self.auth_token = config.get('auth_token')
        self.from_number = config.get('from_number')  # Twilio WhatsApp sender number
        
        if not all([self.account_sid, self.auth_token, self.from_number]):
            raise ValueError("Twilio account_sid, auth_token, and from_number are required")
    
    def validate_config(self, config: Dict) -> Dict[str, Union[bool, str]]:
        """Validate Twilio configuration"""
        required_fields = ['account_sid', 'auth_token', 'from_number']
        
        for field in required_fields:
            if not config.get(field):
                return {
                    'valid': False, 
                    'message': f'Missing required field: {field}'
                }
        
        # Validate WhatsApp number format
        from_number = config.get('from_number', '')
        if not from_number.startswith('whatsapp:'):
            return {
                'valid': False,
                'message': 'from_number must be in format: whatsapp:+1234567890'
            }
        
        # Test API connectivity
        try:
            health = self.health_check()
            if not health.get('healthy'):
                return {
                    'valid': False,
                    'message': f"API health check failed: {health.get('message', 'Unknown error')}"
                }
        except Exception as e:
            return {
                'valid': False,
                'message': f'Configuration validation failed: {str(e)}'
            }
        
        return {'valid': True, 'message': 'Configuration is valid'}
    
    def health_check(self) -> Dict[str, Union[bool, str, Dict]]:
        """Check Twilio account status"""
        try:
            start_time = time.time()
            # Check account status
            response = self._make_request("GET", f"/Accounts/{self.account_sid}.json")
            response_time = time.time() - start_time
            
            self.log_api_call("GET", "/Accounts", True, response_time)
            
            account_status = response.get('status', 'unknown')
            
            return {
                'healthy': account_status == 'active',
                'message': f'Twilio account status: {account_status}',
                'data': {
                    'response_time': response_time,
                    'account_status': account_status,
                    'account_sid': response.get('sid', '')
                }
            }
        except Exception as e:
            self.log_api_call("GET", "/Accounts", False, error=str(e))
            return {
                'healthy': False,
                'message': f'Health check failed: {str(e)}',
                'data': {}
            }
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                     files: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict:
        """Make HTTP request to Twilio API"""
        url = f"{self.base_url}{endpoint}"
        
        # Twilio uses basic auth
        auth = (self.account_sid, self.auth_token)
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        client = self.get_http_client()
        
        try:
            if method.upper() == "GET":
                response = client.get(url, auth=auth, params=params, timeout=API_TIMEOUT_SHORT)
            elif method.upper() == "POST":
                # Twilio expects form data, not JSON
                response = client.post(url, auth=auth, data=data, files=files, timeout=API_TIMEOUT_SHORT)
            else:
                raise Exception(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            error_msg = f"Twilio request failed: {e}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = f"Twilio API error: {error_data.get('message', str(e))}"
                except ValueError:
                    error_msg = f"Twilio API error: {e.response.text}"
            raise Exception(error_msg)
    
    # Messaging Methods
    def send_text_message(self, to: str, message: str, **kwargs) -> Dict:
        """Send text message via Twilio WhatsApp API"""
        try:
            start_time = time.time()
            
            # Transform phone number format for Twilio
            to_number = self._format_phone_for_twilio(to)
            
            # Twilio request format (form data)
            data = {
                'From': self.from_number,
                'To': to_number,
                'Body': message
            }
            
            result = self._make_request("POST", f"/Accounts/{self.account_sid}/Messages.json", data=data)
            response_time = time.time() - start_time
            
            # Twilio returns different status codes
            success = result.get('status') in ['queued', 'sent', 'delivered']
            self.log_api_call("POST", "/Messages", success, response_time)
            
            if success:
                return {
                    'success': True,
                    'message_id': result.get('sid', ''),  # Twilio uses 'sid' not 'id'
                    'data': result
                }
            else:
                return {
                    'success': False,
                    'message': f"Message failed with status: {result.get('status')}",
                    'data': result
                }
        except Exception as e:
            self.log_api_call("POST", "/Messages", False, error=str(e))
            return self.handle_api_error(e, "send_text_message")
    
    def send_media_message(self, to: str, media_dto: MediaMessageDTO, **kwargs) -> Dict:
        """Send media message via Twilio WhatsApp API"""
        try:
            start_time = time.time()
            
            to_number = self._format_phone_for_twilio(to)
            
            # For Twilio, we need to upload media first and get a URL
            media_url = self._upload_media_to_twilio(media_dto)
            if not media_url:
                return {
                    'success': False,
                    'message': 'Failed to upload media to Twilio'
                }
            
            # Twilio request format for media
            data = {
                'From': self.from_number,
                'To': to_number,
                'MediaUrl': media_url
            }
            
            if media_dto.caption:
                data['Body'] = media_dto.caption
            
            result = self._make_request("POST", f"/Accounts/{self.account_sid}/Messages.json", data=data)
            response_time = time.time() - start_time
            
            success = result.get('status') in ['queued', 'sent', 'delivered']
            self.log_api_call("POST", "/Messages", success, response_time)
            
            if success:
                return {
                    'success': True,
                    'message_id': result.get('sid', ''),
                    'data': result
                }
            else:
                return {
                    'success': False,
                    'message': f"Media message failed with status: {result.get('status')}",
                    'data': result
                }
        except Exception as e:
            self.log_api_call("POST", "/Messages", False, error=str(e))
            return self.handle_api_error(e, "send_media_message")
    
    def _format_phone_for_twilio(self, phone: str) -> str:
        """Format phone number for Twilio WhatsApp API"""
        # Remove existing whatsapp: prefix if present
        clean_phone = phone.replace('whatsapp:', '')
        
        # Ensure it starts with +
        if not clean_phone.startswith('+'):
            clean_phone = '+' + clean_phone
        
        return f"whatsapp:{clean_phone}"
    
    def _upload_media_to_twilio(self, media_dto: MediaMessageDTO) -> Optional[str]:
        """Upload media to Twilio and return URL"""
        try:
            # This is a simplified implementation
            # In reality, you might need to upload to your own server first
            # then provide a publicly accessible URL to Twilio
            
            # For demonstration, we'll assume media is already accessible via URL
            if media_dto.media_url:
                return media_dto.media_url
            
            # Otherwise, would need to upload binary data to accessible location
            # This is provider-specific implementation detail
            _logger.warning("Media upload to Twilio requires accessible URL")
            return None
            
        except Exception as e:
            _logger.error(f"Failed to upload media to Twilio: {e}")
            return None
    
    def get_message_status(self, message_id: str) -> Dict:
        """Get message status from Twilio"""
        try:
            result = self._make_request("GET", f"/Accounts/{self.account_sid}/Messages/{message_id}.json")
            
            # Map Twilio status to standard status
            twilio_status = result.get('status', 'unknown')
            standard_status = self._map_twilio_status(twilio_status)
            
            return {
                'status': standard_status,
                'timestamp': self._parse_twilio_date(result.get('date_sent')),
                'data': result
            }
        except Exception as e:
            return self.handle_api_error(e, "get_message_status")
    
    def _map_twilio_status(self, twilio_status: str) -> str:
        """Map Twilio status to standard status"""
        mapping = {
            'queued': 'pending',
            'sending': 'pending', 
            'sent': 'sent',
            'delivered': 'delivered',
            'undelivered': 'failed',
            'failed': 'failed',
            'read': 'read'
        }
        return mapping.get(twilio_status, 'unknown')
    
    def _parse_twilio_date(self, date_str: str) -> int:
        """Parse Twilio date format to timestamp"""
        if not date_str:
            return 0
        
        try:
            from datetime import datetime
            # Twilio uses RFC 2822 format
            dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %z')
            return int(dt.timestamp())
        except Exception:
            return 0
    
    # Contact Management (Twilio has limited contact management)
    def get_contacts(self, limit: int = 100, offset: int = 0) -> Dict:
        """Twilio doesn't provide contact listing - return empty"""
        return {
            'contacts': [],
            'total': 0,
            'message': 'Twilio WhatsApp API does not support contact listing'
        }
    
    def check_contact_exists(self, phone_numbers: List[str]) -> Dict:
        """Check if contacts exist (Twilio limitation - can't verify beforehand)"""
        # Twilio doesn't provide contact validation endpoint
        # We can only know after sending fails
        results = []
        for phone in phone_numbers:
            results.append({
                'phone': phone,
                'exists': True,  # Assume true, will know on send failure
                'note': 'Twilio cannot verify WhatsApp availability beforehand'
            })
        
        return {'results': results}
    
    # Group Management (Not supported by Twilio WhatsApp API)
    def get_groups(self, limit: int = 100, offset: int = 0) -> Dict:
        """Twilio WhatsApp API doesn't support groups"""
        return {
            'groups': [],
            'total': 0,
            'message': 'Twilio WhatsApp API does not support group management'
        }
    
    def create_group(self, name: str, participants: List[str], description: str = "") -> Dict:
        """Twilio WhatsApp API doesn't support group creation"""
        return {
            'success': False,
            'message': 'Twilio WhatsApp API does not support group creation'
        }
    
    def get_group_info(self, group_id: str) -> Optional[GroupDTO]:
        """Twilio WhatsApp API doesn't support groups"""
        return None
    
    def get_group_invite_link(self, group_id: str) -> Optional[str]:
        """Twilio WhatsApp API doesn't support groups"""
        return None
    
    def add_group_participants(self, group_id: str, participants: List[str]) -> Dict:
        """Twilio WhatsApp API doesn't support groups"""
        return {
            'success': False,
            'message': 'Twilio WhatsApp API does not support group management'
        }
    
    def remove_group_participants(self, group_id: str, participants: List[str]) -> Dict:
        """Twilio WhatsApp API doesn't support groups"""
        return {
            'success': False,
            'message': 'Twilio WhatsApp API does not support group management'
        }
    
    # Webhook Methods
    def validate_webhook(self, headers: Dict, body: Dict, signature: str = None) -> bool:
        """Validate Twilio webhook signature"""
        if not signature:
            return False
        
        try:
            from twilio.request_validator import RequestValidator
            
            validator = RequestValidator(self.auth_token)
            url = headers.get('HTTP_X_FORWARDED_PROTO', 'https') + '://' + headers.get('HTTP_HOST', '') + headers.get('REQUEST_URI', '')
            
            return validator.validate(url, body, signature)
        except ImportError:
            _logger.warning("twilio package not installed, cannot validate webhooks")
            return True  # Allow through if package not available
        except Exception as e:
            _logger.error(f"Webhook validation failed: {e}")
            return False
    
    def parse_webhook_message(self, webhook_data: Dict) -> List[MessageDTO]:
        """Parse Twilio webhook into message DTOs"""
        messages = []
        
        # Twilio webhook format is different - single message per webhook
        message_id = webhook_data.get('MessageSid', '')
        if not message_id:
            return messages
        
        # Skip outgoing messages
        if webhook_data.get('From', '').startswith(self.from_number):
            return messages
        
        content = webhook_data.get('Body', '')
        message_type = 'text'
        
        # Check for media
        num_media = int(webhook_data.get('NumMedia', '0'))
        if num_media > 0:
            media_content_type = webhook_data.get('MediaContentType0', '')
            if media_content_type.startswith('image/'):
                message_type = 'image'
            elif media_content_type.startswith('video/'):
                message_type = 'video'
            elif media_content_type.startswith('audio/'):
                message_type = 'audio'
            else:
                message_type = 'document'
            
            if not content:
                content = f'{message_type.title()} message'
        
        message_dto = MessageDTO(
            message_id=message_id,
            content=content,
            message_type=message_type,
            chat_id=webhook_data.get('From', ''),
            from_me=False,
            timestamp=int(time.time()),  # Twilio doesn't provide exact timestamp in webhook
            sender_phone=webhook_data.get('From', '').replace('whatsapp:', ''),
            metadata=webhook_data
        )
        messages.append(message_dto)
        
        return messages
    
    def parse_webhook_status(self, webhook_data: Dict) -> List[Dict]:
        """Parse Twilio webhook status updates"""
        status_updates = []
        
        # Twilio sends status updates as separate webhooks
        message_id = webhook_data.get('MessageSid')
        status = webhook_data.get('MessageStatus')
        
        if message_id and status:
            status_updates.append({
                'message_id': message_id,
                'status': self._map_twilio_status(status),
                'timestamp': int(time.time()),
                'raw_status': status
            })
        
        return status_updates
    
    # Media Management
    def upload_media(self, media_data: bytes, filename: str, media_type: str) -> Dict:
        """Upload media for Twilio (requires external hosting)"""
        return {
            'success': False,
            'message': 'Twilio requires media to be hosted externally and accessed via URL'
        }
    
    def download_media(self, media_id: str) -> Dict:
        """Download media from Twilio"""
        try:
            # Twilio media URLs are temporary and expire
            result = self._make_request("GET", f"/Accounts/{self.account_sid}/Messages/{media_id}/Media.json")
            
            media_items = result.get('media_list', [])
            if not media_items:
                return {
                    'success': False,
                    'message': 'No media found'
                }
            
            # Download the first media item
            media_url = media_items[0].get('uri', '')
            if media_url:
                media_response = requests.get(media_url, auth=(self.account_sid, self.auth_token))
                return {
                    'success': True,
                    'data': media_response.content,
                    'content_type': media_items[0].get('content_type', 'application/octet-stream')
                }
            
            return {
                'success': False,
                'message': 'Media URL not available'
            }
        except Exception as e:
            return self.handle_api_error(e, "download_media")
