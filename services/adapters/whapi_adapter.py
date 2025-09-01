"""
WHAPI Provider Adapter
Implements the IWhatsAppProvider interface for WHAPI.cloud
"""
from typing_extensions import Union
import requests
import json
import logging
import base64
import time
from typing import Dict, List, Optional
from odoo import models, api, fields
from .base_adapter import BaseWhatsAppAdapter
from ..dto import MessageDTO, MediaMessageDTO, ContactDTO, GroupDTO, GroupParticipantDTO
from ...constants import (
    API_TIMEOUT_SHORT, API_TIMEOUT_LONG, WHATSAPP_USER_SUFFIX,
    MIME_TYPES, IMAGE_HEADERS, MAX_RETRIES, RETRY_BACKOFF_FACTOR, RETRY_STATUS_CODES
)

_logger = logging.getLogger(__name__)


class WhapiAdapter(BaseWhatsAppAdapter):
    """WHAPI Provider Adapter"""
    
    _name = 'whatsapp.adapter.whapi'
    _description = 'WHAPI WhatsApp Adapter'
    
    def __init__(self, env, config: Dict):
        super().__init__(env, config)
        self.base_url = "https://gate.whapi.cloud"
        self.token = config.get('token')
        if not self.token:
            raise ValueError("WHAPI token is required")
    
    def validate_config(self, config: Dict) -> Dict[str, Union[bool, str]]:
        """Validate WHAPI configuration"""
        required_fields = ['token']
        
        for field in required_fields:
            if not config.get(field):
                return {
                    'valid': False, 
                    'message': f'Missing required field: {field}'
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
        """Check WHAPI health status"""
        try:
            start_time = time.time()
            response = self._make_request("GET", "/health")
            response_time = time.time() - start_time
            
            self.log_api_call("GET", "/health", True, response_time)
            
            return {
                'healthy': True,
                'message': 'WHAPI service is healthy',
                'data': {
                    'response_time': response_time,
                    'api_response': response
                }
            }
        except Exception as e:
            self.log_api_call("GET", "/health", False, error=str(e))
            return {
                'healthy': False,
                'message': f'Health check failed: {str(e)}',
                'data': {}
            }
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                     files: Optional[Dict] = None, params: Optional[Dict] = None, 
                     json_data: Optional[Dict] = None) -> Dict:
        """Make HTTP request to WHAPI API"""
        url = f"{self.base_url}{endpoint}"
        
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        
        if files:
            # For file uploads, don't set Content-Type
            pass
        else:
            headers["Content-Type"] = "application/json"
            headers["accept"] = "application/json"
        
        client = self.get_http_client()
        
        try:
            if method.upper() == "GET":
                response = client.get(url, headers=headers, params=params, timeout=API_TIMEOUT_SHORT)
            elif method.upper() == "POST":
                if files:
                    response = client.post(url, headers=headers, files=files, data=data, timeout=API_TIMEOUT_LONG)
                elif json_data:
                    response = client.post(url, headers=headers, json=json_data, params=params, timeout=API_TIMEOUT_SHORT)
                else:
                    response = client.post(url, headers=headers, json=data, params=params, timeout=API_TIMEOUT_SHORT)
            elif method.upper() == "PUT":
                response = client.put(url, headers=headers, json=data, timeout=API_TIMEOUT_SHORT)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers, json=data, timeout=API_TIMEOUT_SHORT)
            else:
                raise Exception(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            
            if response.status_code == 204:
                return {"success": True}
            
            try:
                return response.json()
            except ValueError:
                return {"success": True, "data": response.text}
        
        except requests.exceptions.RequestException as e:
            error_msg = f"WHAPI request failed: {e}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = f"API request failed: {error_data}"
                except ValueError:
                    error_msg = f"API request failed: {e.response.text}"
            raise Exception(error_msg)
    
    # Messaging Methods
    def send_text_message(self, to: str, message: str, **kwargs) -> Dict:
        """Send text message via WHAPI"""
        try:
            start_time = time.time()
            
            data = {
                "to": to,
                "body": message
            }
            
            result = self._make_request("POST", "/messages/text", data=data)
            response_time = time.time() - start_time
            
            success = result.get('sent', False)
            self.log_api_call("POST", "/messages/text", success, response_time)
            
            if success:
                return {
                    'success': True,
                    'message_id': result.get('message', {}).get('id', ''),
                    'data': result
                }
            else:
                return {
                    'success': False,
                    'message': 'Message not sent',
                    'data': result
                }
        except Exception as e:
            self.log_api_call("POST", "/messages/text", False, error=str(e))
            return self.handle_api_error(e, "send_text_message")
    
    def send_media_message(self, to: str, media_dto: MediaMessageDTO, **kwargs) -> Dict:
        """Send media message via WHAPI using data URL approach"""
        try:
            start_time = time.time()
            
            # Convert binary data to base64 if needed
            if isinstance(media_dto.media_data, bytes):
                base64_data = base64.b64encode(media_dto.media_data).decode('utf-8')
            else:
                base64_data = media_dto.media_data
            
            # Fix double encoding if present
            base64_data = self._fix_double_encoding(base64_data)
            
            # Get MIME type
            mime_type = media_dto.mime_type or self._get_mime_type(
                media_dto.media_type, media_dto.filename
            )
            
            # Create data URL
            data_url = f"data:{mime_type};name={media_dto.filename};base64,{base64_data}"
            
            # Format recipient
            if '@' not in to:
                to = f"{to}@s.whatsapp.net"
            
            endpoint = f'/messages/media/{media_dto.media_type}'
            params = {'to': to}
            if media_dto.caption:
                params['caption'] = media_dto.caption
            
            json_data = {
                'media': data_url,
                'no_encode': False
            }
            
            result = self._make_request("POST", endpoint, json_data=json_data, params=params)
            response_time = time.time() - start_time
            
            success = result.get('sent', False)
            self.log_api_call("POST", endpoint, success, response_time)
            
            if success:
                return {
                    'success': True,
                    'message_id': result.get('message', {}).get('id', ''),
                    'data': result
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Failed to send media message'),
                    'data': result
                }
        except Exception as e:
            self.log_api_call("POST", f"/messages/media/{media_dto.media_type}", False, error=str(e))
            return self.handle_api_error(e, "send_media_message")
    
    def _fix_double_encoding(self, data: str) -> str:
        """Fix double encoding issue from Odoo binary fields"""
        try:
            clean_data = data.replace('\n', '').replace('\r', '').replace(' ', '')
            
            # Try to decode and check if it's double encoded
            try:
                first_decode = base64.b64decode(clean_data, validate=True)
                
                # Check if the first decode result is still base64 by trying to decode it as text
                try:
                    potential_base64 = first_decode.decode('utf-8')
                    
                    # Check if this looks like base64 by checking for image headers
                    header_match = False
                    for header in IMAGE_HEADERS:
                        if potential_base64.startswith(header):
                            header_match = True
                            break
                    
                    if header_match:
                        # Validate this is actually valid base64 by decoding it
                        try:
                            base64.b64decode(potential_base64, validate=True)
                            return potential_base64  # Return the corrected base64
                        except Exception:
                            pass
                            
                except UnicodeDecodeError:
                    # First decode is binary (correct), not double encoded
                    pass
                    
                # Not double encoded, return original cleaned data
                return clean_data
                
            except Exception:
                return clean_data
        except Exception:
            return data
    
    def _get_mime_type(self, message_type: str, filename: str) -> str:
        """Get MIME type based on message type and filename"""
        if message_type in MIME_TYPES:
            type_map = MIME_TYPES[message_type]
            if filename:
                for ext, mime in type_map.items():
                    if ext != 'default' and filename.lower().endswith(ext):
                        return mime
            return type_map['default']
        
        return 'application/octet-stream'
    
    def get_message_status(self, message_id: str) -> Dict:
        """Get message status from WHAPI"""
        try:
            result = self._make_request("GET", f"/messages/{message_id}")
            
            return {
                'status': result.get('status', 'unknown'),
                'timestamp': result.get('timestamp', 0),
                'data': result
            }
        except Exception as e:
            return self.handle_api_error(e, "get_message_status")
    
    # Contact Management
    def get_contacts(self, limit: int = 100, offset: int = 0) -> Dict:
        """Get contacts from WHAPI"""
        try:
            params = {
                'count': limit,
                'offset': offset
            }
            result = self._make_request("GET", "/contacts", params=params)
            
            contacts = []
            for contact_data in result.get('contacts', []):
                contact_dto = ContactDTO(
                    contact_id=contact_data.get('id', ''),
                    phone=contact_data.get('phone', ''),
                    name=contact_data.get('name', ''),
                    pushname=contact_data.get('pushname', ''),
                    is_whatsapp_user=contact_data.get('isWAContact', True),
                    metadata=contact_data
                )
                contacts.append(contact_dto)
            
            return {
                'contacts': contacts,
                'total': result.get('total', len(contacts))
            }
        except Exception as e:
            return self.handle_api_error(e, "get_contacts")
    
    def check_contact_exists(self, phone_numbers: List[str]) -> Dict:
        """Check if contacts exist on WhatsApp via WHAPI"""
        try:
            data = {
                "blocking": "wait",
                "contacts": phone_numbers
            }
            result = self._make_request("POST", "/contacts/check", data=data)
            
            results = []
            for contact in result.get('contacts', []):
                results.append({
                    'phone': contact.get('input', ''),
                    'exists': contact.get('status', '') == 'valid'
                })
            
            return {'results': results}
        except Exception as e:
            return self.handle_api_error(e, "check_contact_exists")
    
    # Group Management
    def get_groups(self, limit: int = 100, offset: int = 0) -> Dict:
        """Get groups from WHAPI"""
        try:
            params = {
                'count': limit,
                'offset': offset
            }
            result = self._make_request("GET", "/groups", params=params)
            
            groups = []
            for group_data in result.get('groups', []):
                group_dto = GroupDTO(
                    group_id=group_data.get('id', ''),
                    name=group_data.get('name', ''),
                    description=group_data.get('description', ''),
                    participant_count=len(group_data.get('participants', [])),
                    created_at=group_data.get('created_at', 0),
                    metadata=group_data
                )
                groups.append(group_dto)
            
            return {
                'groups': groups,
                'total': result.get('total', len(groups))
            }
        except Exception as e:
            return self.handle_api_error(e, "get_groups")
    
    def create_group(self, name: str, participants: List[str], description: str = "") -> Dict:
        """Create group via WHAPI"""
        try:
            data = {
                "subject": name,
                "participants": participants
            }
            if description:
                data["description"] = description
            
            result = self._make_request("POST", "/groups", data=data)
            
            group_id = result.get('group_id') or result.get('id')
            if not group_id:
                return {
                    'success': False,
                    'message': result.get('message', 'Failed to create group')
                }
            
            # Try to get invite link
            invite_code = None
            try:
                invite_result = self._make_request("GET", f"/groups/{group_id}/invite")
                invite_code = invite_result.get('invite_code')
            except Exception as e:
                _logger.warning(f"Failed to get invite code: {e}")
            
            return {
                'success': True,
                'group_id': group_id,
                'invite_link': f"https://chat.whatsapp.com/{invite_code}" if invite_code else None,
                'data': result
            }
        except Exception as e:
            return self.handle_api_error(e, "create_group")
    
    def get_group_info(self, group_id: str) -> Optional[GroupDTO]:
        """Get group info from WHAPI"""
        try:
            result = self._make_request("GET", f"/groups/{group_id}")
            
            if not result:
                return None
            
            participants = []
            for p in result.get('participants', []):
                participant = GroupParticipantDTO(
                    contact_id=p.get('id', ''),
                    phone=p.get('phone', ''),
                    name=p.get('name', ''),
                    role=p.get('role', 'member')
                )
                participants.append(participant)
            
            return GroupDTO(
                group_id=result.get('id', ''),
                name=result.get('name', ''),
                description=result.get('description', ''),
                participants=participants,
                participant_count=len(participants),
                metadata=result
            )
        except Exception as e:
            _logger.error(f"Failed to get group info: {e}")
            return None
    
    def get_group_invite_link(self, group_id: str) -> Optional[str]:
        """Get group invite link from WHAPI"""
        try:
            result = self._make_request("GET", f"/groups/{group_id}/invite")
            invite_code = result.get('invite_code')
            
            if invite_code:
                return f"https://chat.whatsapp.com/{invite_code}"
            return None
        except Exception as e:
            _logger.error(f"Failed to get invite link: {e}")
            return None
    
    def add_group_participants(self, group_id: str, participants: List[str]) -> Dict:
        """Add participants to group via WHAPI"""
        try:
            data = {"participants": participants}
            result = self._make_request("POST", f"/groups/{group_id}/participants", data=data)
            
            return {
                'success': True,
                'added': participants,  # WHAPI doesn't provide detailed feedback
                'failed': [],
                'data': result
            }
        except Exception as e:
            return self.handle_api_error(e, "add_group_participants")
    
    def remove_group_participants(self, group_id: str, participants: List[str]) -> Dict:
        """Remove participants from group via WHAPI"""
        try:
            data = {"participants": participants}
            result = self._make_request("DELETE", f"/groups/{group_id}/participants", data=data)
            
            return {
                'success': True,
                'removed': participants,  # WHAPI doesn't provide detailed feedback
                'failed': [],
                'data': result
            }
        except Exception as e:
            return self.handle_api_error(e, "remove_group_participants")
    
    # Webhook Methods
    def validate_webhook(self, headers: Dict, body: Dict, signature: str = None) -> bool:
        """Validate WHAPI webhook (basic validation)"""
        # WHAPI doesn't use signature validation by default
        # You can implement custom validation here if needed
        return True
    
    def parse_webhook_message(self, webhook_data: Dict) -> List[MessageDTO]:
        """Parse WHAPI webhook into message DTOs"""
        messages = []
        
        for message_data in webhook_data.get('messages', []):
            # Skip outgoing messages
            if message_data.get('from_me', False):
                continue
            
            # Extract content based on message type
            message_type = message_data.get('type', 'text')
            content = ''
            
            if message_type == 'text':
                text_data = message_data.get('text', {})
                content = text_data.get('body', '') if isinstance(text_data, dict) else str(text_data)
            elif message_type in ['image', 'video', 'audio', 'document']:
                media_data = message_data.get(message_type, {})
                if isinstance(media_data, dict):
                    content = media_data.get('caption', f'{message_type.title()} message')
                else:
                    content = f'{message_type.title()} message'
            else:
                content = f'{message_type.title()} message'
            
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
    
    def parse_webhook_status(self, webhook_data: Dict) -> List[Dict]:
        """Parse WHAPI webhook status updates"""
        status_updates = []
        
        for entry in webhook_data.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value', {})
                
                for status in value.get('statuses', []):
                    status_updates.append({
                        'message_id': status.get('id'),
                        'status': status.get('status'),
                        'timestamp': status.get('timestamp', 0),
                        'error': status.get('errors', [])
                    })
        
        return status_updates
    
    # Media Management
    def upload_media(self, media_data: bytes, filename: str, media_type: str) -> Dict:
        """Upload media to WHAPI (not typically needed as we use data URLs)"""
        return {
            'success': False,
            'message': 'WHAPI uses data URLs for media, upload not required'
        }
    
    def download_media(self, media_id: str) -> Dict:
        """Download media from WHAPI"""
        try:
            result = self._make_request("GET", f"/media/{media_id}")
            
            # Implementation depends on WHAPI media download API
            return {
                'success': True,
                'data': result.get('data', b''),
                'content_type': result.get('content_type', 'application/octet-stream')
            }
        except Exception as e:
            return self.handle_api_error(e, "download_media")
