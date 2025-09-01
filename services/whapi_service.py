import requests
import json
import logging
import base64
import hashlib
from typing import Dict, List, Optional
from odoo import api, models, fields
from odoo.exceptions import AccessError, ValidationError
from ..constants import (
    API_TIMEOUT_SHORT, API_TIMEOUT_LONG, WHATSAPP_USER_SUFFIX,
    MIME_TYPES, IMAGE_HEADERS
)

_logger = logging.getLogger(__name__)

class WhapiService(models.AbstractModel):
    _name = 'whapi.service'
    _description = 'WHAPI Service'
    
    @api.model
    def _get_api_config(self, user_id=None):
        """Get API configuration for current user"""
        if not user_id:
            user_id = self.env.user.id
            
        config_obj = self.env['whatsapp.configuration'].get_user_configuration(user_id)
        if not config_obj:
            raise AccessError("No WhatsApp configuration found for your user account. Please contact administrator.")
        
        return {
            'token': config_obj.token,
            'supervisor_phone': config_obj.supervisor_phone,
            'config_id': config_obj.id,
            'config_name': config_obj.name
        }
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, files: Optional[Dict] = None, params: Optional[Dict] = None, json: Optional[Dict] = None) -> Dict:
        """Make HTTP request to WHAPI API"""
        config = self._get_api_config()
        
        if not config['token']:
            raise Exception("WHAPI API token not configured")
        
        base_url = "https://gate.whapi.cloud"
        url = f"{base_url}{endpoint}"
        
        _logger.info(f"Making {method} request to {url}")

        headers = {
            "Authorization": f"Bearer {config['token']}"
        }
        
        # Set content type and accept headers based on request type
        if files:
            # For file uploads, don't set Content-Type (let requests handle multipart)
            # and don't set Accept header
            pass
        else:
            # For JSON requests
            headers["Content-Type"] = "application/json"
            headers["accept"] = "application/json"

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=API_TIMEOUT_SHORT)
            elif method.upper() == "POST":
                if files:
                    response = requests.post(url, headers=headers, files=files, data=data, timeout=API_TIMEOUT_LONG)
                elif json:
                    _logger.info(f"Sending JSON data: {json}")
                    response = requests.post(url, headers=headers, json=json, params=params, timeout=API_TIMEOUT_SHORT)
                else:
                    response = requests.post(url, headers=headers, json=data, params=params, timeout=API_TIMEOUT_SHORT)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, json=data, timeout=API_TIMEOUT_SHORT)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers, json=data, timeout=API_TIMEOUT_SHORT)
            elif method.upper() == "HEAD":
                response = requests.head(url, headers=headers, timeout=API_TIMEOUT_SHORT)
            else:
                raise Exception(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            _logger.info(f"Response from WHAPI: {response.status_code}")
            
            # Handle different response types
            if response.status_code == 204:  # No content
                return {"success": True}
            
            try:
                return response.json()
            except ValueError:
                # If response is not JSON, return text content
                return {"success": True, "data": response.text}
        
        except requests.exceptions.RequestException as e:
            _logger.error(f"WHAPI request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    raise Exception(f"API request failed: {error_data}")
                except ValueError:
                    raise Exception(f"API request failed: {e.response.text}")
            raise Exception(f"API request failed: {str(e)}")

    def check_health(self) -> Dict:
        """Check WHAPI health status"""
        try:
            result = self._make_request("GET", "/health")
            return result
        except Exception as e:
            _logger.error(f"Failed to check health: {e}")
            return {"success": False, "message": str(e)}

    # Media Management Methods (REMOVED - Using direct media sending only)
    # All media upload methods removed - using new data URL approach only

    def send_media_message(self, to: str, media_data: str, filename: str, message_type: str = "image", caption: str = ""):
        """Send media message to WHAPI using JSON format with data URL - NEW APPROACH ONLY"""
        try:
            # Use the exact format from the working curl example
            endpoint = f'/messages/media/{message_type}'
            
            # Validate and convert to data URL format
            if isinstance(media_data, str):
                # Check for double encoding issue and fix if needed
                corrected_media_data = self._fix_double_encoding(media_data)
                
                mime_type = self._get_mime_type(message_type, filename)
                data_url = f"data:{mime_type};name={filename};base64,{corrected_media_data}"
            else:
                # Handle bytes that might contain double-encoded base64 string
                try:
                    # Try to decode as string first
                    potential_string = media_data.decode('utf-8')
                    
                    # Check if this string is double encoded and fix if needed
                    if self._is_double_encoded(potential_string):
                        corrected_string = self._fix_double_encoding(potential_string)
                        data_url_data = corrected_string
                    else:
                        data_url_data = potential_string
                        
                except UnicodeDecodeError:
                    # True binary data - encode to base64
                    data_url_data = base64.b64encode(media_data).decode('utf-8')
                except Exception:
                    # Fallback to base64 encode
                    data_url_data = base64.b64encode(media_data).decode('utf-8')
                
                mime_type = self._get_mime_type(message_type, filename)
                data_url = f"data:{mime_type};name={filename};base64,{data_url_data}"
            
            # Format recipient phone number properly
            if '@' not in to:
                to = f"{to}{WHATSAPP_USER_SUFFIX}"
            
            # Query parameters exactly as in curl example
            params = {
                'to': to,
            }
            
            if caption:
                params['caption'] = caption
            
            # Request body exactly as in curl example
            json_data = {
                'media': data_url,
                'no_encode': False
            }
            
            _logger.info(f"Sending media message to {params['to']}")
            _logger.info(f"Media type: {message_type}, filename: {filename}")
            _logger.info(f"Data URL length: {len(data_url)}")
            
            # Make request using the new approach
            result = self._make_request("POST", endpoint, json=json_data, params=params)
            
            if result and result.get('sent'):
                return {
                    'success': True,
                    'sent': True,
                    'message_id': result.get('message', {}).get('id', ''),
                    'message': result.get('message', {}),
                    'data': result
                }
            else:
                return {
                    'success': False,
                    'sent': False,
                    'message': result.get('message', 'Failed to send media message'),
                    'error_details': result
                }
                
        except Exception as e:
            _logger.error("Failed to send media message: %s", str(e))
            return {
                'success': False,
                'sent': False,
                'message': str(e)
            }
    
    def _is_double_encoded(self, data: str) -> bool:
        """Check if data is double encoded"""
        try:
            clean_data = data.replace('\n', '').replace('\r', '').replace(' ', '')
            first_decode = base64.b64decode(clean_data, validate=True)
            
            try:
                potential_base64 = first_decode.decode('utf-8')
                # Check if it looks like base64 with image headers
                for header in IMAGE_HEADERS:
                    if potential_base64.startswith(header):
                        return True
                return self._looks_like_base64(potential_base64)
            except UnicodeDecodeError:
                return False
        except Exception:
            return False
    
    def _fix_double_encoding(self, data: str) -> str:
        """Fix double encoding issue from Odoo binary fields"""
        try:
            # Clean the base64 data first
            clean_data = data.replace('\n', '').replace('\r', '').replace(' ', '')
            
            # Try to decode and check if it's double encoded
            try:
                first_decode = base64.b64decode(clean_data, validate=True)
                
                # Check if the first decode result is still base64 by trying to decode it as text
                try:
                    potential_base64 = first_decode.decode('utf-8')
                    
                    # Check if this looks like base64 by checking for image headers
                    for header in IMAGE_HEADERS:
                        if potential_base64.startswith(header):
                            # Validate this is actually valid base64 by decoding it
                            try:
                                base64.b64decode(potential_base64, validate=True)
                                return potential_base64  # Return the corrected base64
                            except Exception:
                                break
                    
                    # Additional check: if the decoded string is mostly base64 characters
                    if self._looks_like_base64(potential_base64):
                        try:
                            base64.b64decode(potential_base64, validate=True)
                            return potential_base64
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
            return data  # Return original data if anything fails
    
    def _looks_like_base64(self, text: str) -> bool:
        """Check if text looks like base64 encoded data"""
        if not text or len(text) < 4:
            return False
        
        # Base64 should be mostly alphanumeric with +, /, and = characters
        import re
        base64_pattern = re.compile(r'^[A-Za-z0-9+/]*={0,2}$')
        
        # Check if it matches base64 pattern and has reasonable length
        return (base64_pattern.match(text) and 
                len(text) % 4 == 0 and  # Base64 padding requires length divisible by 4
                len(text) > 20)  # Reasonable minimum size for image data

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

    # Contact Management Methods
    def get_contacts(self, count: int = 100, offset: int = 0) -> Dict:
        """Get all phone contacts from WHAPI"""
        try:
            params = {
                'count': count,
                'offset': offset
            }
            result = self._make_request("GET", "/contacts", params=params)
            return result
        except Exception as e:
            _logger.error(f"Failed to get contacts: {e}")
            return {"contacts": [], "count": 0, "total": 0}
    
    def get_chats(self, count: int = 100, offset: int = 0) -> Dict:
        """Get all chat conversations from WHAPI"""
        try:
            params = {
                'count': count,
                'offset': offset
            }
            result = self._make_request("GET", "/chats", params=params)
            return result
        except Exception as e:
            _logger.error(f"Failed to get chats: {e}")
            return {"chats": [], "count": 0, "total": 0}

    def get_contact_info(self, contact_id: str) -> Optional[Dict]:
        """Get detailed contact information"""
        try:
            result = self._make_request("GET", f"/chats/{contact_id}")
            return result
        except requests.HTTPError as e:
            if hasattr(e, 'response') and e.response.status_code == 404:
                return None
            raise
        except Exception as e:
            _logger.error(f"Failed to get contact info: {e}")
            return None

    def check_contacts_exist(self, contacts: List[str], blocking: str = "wait") -> Dict:
        """Check if phone numbers exist on WhatsApp"""
        try:
            data = {
                "blocking": blocking,
                "contacts": contacts
            }
            result = self._make_request("POST", "/contacts/check", data=data)
            return result
        except Exception as e:
            _logger.error(f"Failed to check contacts: {e}")
            return {"contacts": []}

    # Group Management Methods
    def get_groups(self, count: int = 100, offset: int = 0) -> Dict:
        """Get list of all WhatsApp groups"""
        try:
            params = {
                'count': count,
                'offset': offset
            }
            result = self._make_request("GET", "/groups", params=params)
            return result
        except Exception as e:
            _logger.error(f"Failed to get groups: {e}")
            return {"groups": [], "count": 0, "total": 0}

    def get_group_info(self, group_id: str) -> Optional[Dict]:
        """Get group information including participants"""
        try:
            result = self._make_request("GET", f"/groups/{group_id}")
            return result
        except Exception as e:
            _logger.error(f"Failed to get group info: {e}")
            return None

    def get_group_invite_code(self, group_id: str) -> Optional[str]:
        """Get group invite code"""
        try:

            result = self._make_request("GET", f"/groups/{group_id}/invite")
            
            if result and 'invite_code' in result:
                invite_code = result.get('invite_code')
                _logger.info(f"✅ Successfully fetched invite code: {invite_code}")
                return invite_code
            else:
                _logger.warning(f"❌ No invite_code in API response: {result}")
                return None
                
        except Exception as e:
            _logger.error(f"❌ Failed to get group invite code for {group_id}: {e}")
            return None

    def create_group(self, subject: str, participants: List[str]) -> Dict:
        """Create a new WhatsApp group"""
        try:
            data = {
                "subject": subject,
                "participants": participants
            }
            result = self._make_request("POST", "/groups", data=data)
            return result
        except Exception as e:
            _logger.error(f"Failed to create group: {e}")
            return {"success": False, "message": str(e)}

    def create_group_with_invite(self, subject: str, participants: List[str]) -> Dict:
        """Create a new WhatsApp group and immediately fetch invite link"""
        try:
            _logger.info(f"Creating group '{subject}' with {len(participants)} participants")
            
            # Step 1: Create the group
            data = {
                "subject": subject,
                "participants": participants
            }
            result = self._make_request("POST", "/groups", data=data)
            
            if not result.get('group_id') and not result.get('id'):
                error_msg = result.get('message', 'Unknown error occurred while creating group')
                return {"success": False, "message": error_msg}
            
            group_id = result.get('group_id') or result.get('id')
            _logger.info(f"✅ Group created successfully: {group_id}")
            
            # Step 2: Immediately fetch invite link (REQUIRED)
            invite_code = None
            max_retries = 3
            
            for attempt in range(max_retries):
                try:
                    _logger.info(f"Fetching invite link (attempt {attempt + 1}/{max_retries})")
                    invite_code = self.get_group_invite_code(group_id)
                    
                    if invite_code:
                        _logger.info(f"✅ Successfully fetched invite code: {invite_code}")
                        result['invite_code'] = invite_code
                        result['invite_link'] = f"https://chat.whatsapp.com/{invite_code}"
                        break
                    else:
                        _logger.warning(f"Attempt {attempt + 1}: No invite code returned")
                        
                except Exception as e:
                    _logger.warning(f"Attempt {attempt + 1} failed: {e}")
                
                # Wait before retry (except on last attempt)
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)
            
            if not invite_code:
                _logger.error(f"❌ Failed to fetch invite code after {max_retries} attempts")
                result['invite_warning'] = f"Group created but invite link could not be fetched after {max_retries} attempts"
            
            result['success'] = True
            return result
            
        except Exception as e:
            _logger.error(f"Failed to create group with invite: {e}")
            return {"success": False, "message": str(e)}

    def remove_group_participants(self, group_id: str, participants: List[str]) -> Dict:
        """Remove participants from group"""
        try:
            # URL encode the group ID
            data = {"participants": participants}
            result = self._make_request("DELETE", f"/groups/{group_id}/participants", data=data)
            return result
        except Exception as e:
            _logger.error(f"Failed to remove participants: {e}")
            return {"success": False, "message": str(e)}

    # Messaging Methods
    def send_text_message(self, to: str, body: str) -> Dict:
        """Send text message to individual or group"""
        try:
            data = {
                "to": to,
                "body": body
            }
            result = self._make_request("POST", "/messages/text", data=data)
            
            if result.get('sent'):
                return {
                    'success': True,
                    'id': result['message'].get('id', ''),
                    'data': result
                }
            else:
                return {
                    'success': False,
                    'message': 'Message not sent'
                }
        except Exception as e:
            _logger.error("Failed to send text message: %s", str(e))
            return {'success': False, 'message': str(e)}

    def send_group_message(self, group_id: str, text: str, media_data: str = None, filename: str = None, media_type: str = "image", caption: str = "") -> Dict:
        """Send message to group using NEW APPROACH ONLY"""
        try:
            if media_data and filename:
                # Send media message to group using NEW approach
                return self.send_media_message(group_id, media_data, filename, media_type, caption or text)
            else:
                # Send text message to group
                return self.send_text_message(group_id, text)
        except Exception as e:
            _logger.error("Failed to send group message: %s", str(e))
            return {'success': False, 'message': str(e)}

    def get_message_info(self, message_id: str) -> Optional[Dict]:
        """Get message information and status"""
        try:
            result = self._make_request("GET", f"/messages/{message_id}")
            return result
        except Exception as e:
            _logger.error(f"Failed to get message info: {e}")
            return None

    # Backward-compatible alias for models.whatsapp_message.sync_message_status
    def get_message_status(self, message_id: str) -> Optional[Dict]:
        return self.get_message_info(message_id)

    def get_messages(self, count: int = 100, offset: int = 0, time_from: int = None, time_to: int = None, 
                     normal_types: bool = False, from_me: bool = False, sort: str = "desc") -> Dict:
        """Get recent messages using modern list endpoint with proper params.

        - Uses /messages/list (not /api/messages/list) on WHAPI.
        - Ensures booleans are lowercase strings 'true'/'false'.
        - Adds default time_from/time_to if not provided (last 30 days).
        """
        try:
            import time as _t
            now = int(_t.time())
            if time_from is None:
                # default: last 30 days
                time_from = now - 30 * 24 * 60 * 60
            if time_to is None:
                time_to = now

            # Serialize booleans as lowercase strings per API expectations
            to_bool_str = lambda b: 'true' if bool(b) else 'false'

            params = {
                'count': count,
                'offset': offset,
                'time_from': time_from,
                'time_to': time_to,
                'normal_types': to_bool_str(normal_types),
                'from_me': to_bool_str(from_me),
                'sort': sort,
            }

            # Endpoint path on WHAPI
            result = self._make_request("GET", "/messages/list", params=params)
            return result
        except Exception as e:
            _logger.error(f"Failed to get messages: {e}")
            return {"messages": [], "count": 0, "total": 0}

    def get_chat_messages(self, chat_id: str, count: int = 100, offset: int = 0) -> Dict:
        """Get messages for a specific chat"""
        try:
            # URL encode the chat ID
            encoded_chat_id = chat_id.replace('@', '%40')
            params = {
                'count': count,
                'offset': offset
            }
            
            result = self._make_request("GET", f"/chats/{encoded_chat_id}/messages", params=params)
            return result
        except Exception as e:
            _logger.error(f"Failed to get chat messages: {e}")
            return {"messages": [], "count": 0, "total": 0}
