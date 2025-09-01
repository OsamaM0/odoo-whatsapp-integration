import requests
import json
import logging
import base64
import hashlib
from typing import Dict, List, Optional
from odoo import api, models, fields
from odoo.exceptions import AccessError, ValidationError
from ..constants import API_TIMEOUT_SHORT, API_TIMEOUT_LONG

_logger = logging.getLogger(__name__)

class WassengerAPI(models.AbstractModel):
    _name = 'wassenger.api'
    _description = 'Wassenger API Service'
    
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
            'device_id': config_obj.device_id,
            'supervisor_phone': config_obj.supervisor_phone,
            'config_id': config_obj.id,
            'config_name': config_obj.name
        }
    
    def _check_access_to_data(self, device_id):
        """Check if current user has access to data from this device"""
        config = self._get_api_config()
        if config['device_id'] != device_id:
            raise AccessError("You don't have access to data from this device.")
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, files: Optional[Dict] = None) -> Dict:
        """Make HTTP request to Wassenger API"""
        config = self._get_api_config()
        
        if not config['token']:
            raise Exception("Wassenger API token not configured")
        
        base_url = "https://api.wassenger.com/v1"
        url = f"{base_url}{endpoint}"
        
        _logger.info(f"Making {method} request to {url}")

        headers = {
            "Authorization": f"Bearer {config['token']}",
        }
        
        # Don't set Content-Type for file uploads, let requests handle it
        if not files:
            headers["Content-Type"] = "application/json"

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=API_TIMEOUT_SHORT)
            elif method.upper() == "POST":
                if files:
                    response = requests.post(url, headers=headers, files=files, data=data, timeout=API_TIMEOUT_LONG)
                else:
                    response = requests.post(url, headers=headers, json=data, timeout=API_TIMEOUT_SHORT)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, json=data, timeout=API_TIMEOUT_SHORT)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers, json=data, timeout=API_TIMEOUT_SHORT)
            else:
                raise Exception(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            logging.info(f"Response from Wassenger API: {response.status_code} - {response.json()}")
            return response.json()
        
        except requests.exceptions.RequestException as e:
            _logger.error(f"Wassenger API request failed: {e}")
            raise Exception(f"API request failed: {str(e)}")
    
    def _calculate_file_hash(self, file_data: str) -> str:
        """Calculate SHA-2 hash of file data"""
        try:
            file_bytes = base64.b64decode(file_data)
            return hashlib.sha256(file_bytes).hexdigest()
        except Exception as e:
            _logger.error(f"Failed to calculate file hash: {e}")
            return ""

    def get_files(self) -> List[Dict]:
        """Get all files from Wassenger API"""
        try:
            result = self._make_request("GET", "/files")
            return result if isinstance(result, list) else []
        except Exception as e:
            _logger.error(f"Failed to get files: {e}")
            return []

    def find_file_by_hash(self, file_hash: str) -> Optional[Dict]:
        """Find file by SHA-2 hash"""
        try:
            files = self.get_files()
            for file_obj in files:
                if file_obj.get('sha2') == file_hash:
                    return file_obj
            return None
        except Exception as e:
            _logger.error(f"Failed to find file by hash: {e}")
            return None

    def upload_file(self, file_data: str, filename: str) -> Dict:
        """Upload file to Wassenger API with deduplication"""
        try:
            # Calculate file hash
            file_hash = self._calculate_file_hash(file_data)
            if not file_hash:
                return {
                    'success': False,
                    'message': 'Failed to calculate file hash'
                }
            
            # Check if file already exists
            existing_file = self.find_file_by_hash(file_hash)
            if existing_file:
                _logger.info(f"File with hash {file_hash} already exists, using existing file ID: {existing_file['id']}")
                return {
                    'success': True,
                    'file_id': existing_file['id'],
                    'data': existing_file,
                    'is_existing': True
                }
            
            # File doesn't exist, upload new one
            file_bytes = base64.b64decode(file_data)
            
            files = {
                'file': (filename, file_bytes)
            }
            
            result = self._make_request("POST", "/files", files=files)
            
            if isinstance(result, list) and len(result) > 0:
                file_obj = result[0]
                return {
                    'success': True,
                    'file_id': file_obj.get('id', ''),
                    'data': file_obj,
                    'is_existing': False
                }
            elif isinstance(result, dict):
                return {
                    'success': True,
                    'file_id': result.get('id', ''),
                    'data': result,
                    'is_existing': False
                }
            else:
                return {
                    'success': False,
                    'message': 'Invalid response format from API'
                }
        except Exception as e:
            _logger.error("Failed to upload file: %s", str(e))
            return {
                'success': False,
                'message': str(e)
            }

    # Group Management Methods
    def get_groups(self) -> List[Dict]:
        """Get list of all WhatsApp groups"""
        config = self._get_api_config()
        return self._make_request("GET", f"/devices/{config['device_id']}/groups")
    
    def create_group(self, name: str, participants: List[str], description: str = "") -> Dict:
        """Create new WhatsApp group"""
        config = self._get_api_config()
        data = {
            "name": name,
            "participants": participants,
            "description": description
        }
        return self._make_request("POST", f"/devices/{config['device_id']}/groups", data)
    
    def remove_group_participants(self, group_wid: str, participants: List[str]) -> Dict:
        """Remove participants from group"""
        config = self._get_api_config()
        data = {"participants": participants}
        return self._make_request("DELETE", f"/devices/{config['device_id']}/groups/{group_wid}/participants", data)
    
    def get_group_participants(self, group_wid: str) -> List[Dict]:
        """Get group participants"""
        config = self._get_api_config()
        return self._make_request("GET", f"/chat/{config['device_id']}/chats/{group_wid}/participants")
    
    # Contact Management Methods
    def get_contacts(self) -> List[Dict]:
        """Get all contacts with pagination"""
        config = self._get_api_config()
        all_contacts = []
        page = 0
        max_size = 500
        
        while True:
            try:
                contacts = self._make_request("GET", f"/chat/{config['device_id']}/contacts?page={page}&size={max_size}")
                
                if not contacts or len(contacts) == 0:
                    break
                    
                all_contacts.extend(contacts)
                
                if len(contacts) < max_size:
                    break
                    
                page += 1
                
            except Exception as e:
                _logger.error(f"Error fetching contacts page {page}: {e}")
                break
        _logger.info(f"Total contacts fetched: {len(all_contacts)}")
        return all_contacts
    
    def get_contact_info(self, contact_id: str) -> Optional[Dict]:
        """Get detailed contact information"""
        try:
            config = self._get_api_config()
            result = self._make_request("GET", f"/chat/{config['device_id']}/contacts/{contact_id}")
            return result
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    def check_number_exists(self, phone: str) -> bool:
        """Check if phone number exists on WhatsApp"""
        try:
            config = self._get_api_config()
            result = self._make_request("GET", f"/devices/{config['device_id']}/numbers/{phone}/exists")
            return result.get("exists", False)
        except:
            return False
    
    # Messaging Methods - FIXED IMPLEMENTATION
    def send_text_message(self, to: str, message: str, preview_url: bool = True) -> Dict:
        """Send text message to individual"""
        config = self._get_api_config()
        data = {
            "phone": to,
            "message": message,
            "device": config['device_id'],
            "previewUrl": preview_url
        }
        try:
            result = self._make_request("POST", "/messages", data)
            return {'success': True, 'id': result.get('id', ''), 'data': result}
        except Exception as e:
            _logger.error("Failed to send text message: %s", str(e))
            return {'success': False, 'message': str(e)}
    
    def send_media_message(self, to: str, file_id: str = None, media_url: str = None, caption: str = "") -> Dict:
        """Send media message using file ID or URL"""
        data = {
            "phone": to,
            "message": caption,
        }
        
        if file_id:
            data["media"] = {"file": file_id}
        elif media_url:
            data["media"] = {"url": media_url}
        else:
            return {'success': False, 'message': 'Either file_id or media_url must be provided'}
            
        try:
            result = self._make_request("POST", "/messages", data)
            return {'success': True, 'id': result.get('id', ''), 'data': result}
        except Exception as e:
            _logger.error("Failed to send media message: %s", str(e))
            return {'success': False, 'message': str(e)}
    
    def send_group_message(self, group_id: str, message: str, media_url: str = None, file_id: str = None, caption: str = "") -> Dict:
        """Send message to group using file ID or URL"""
        data = {
            "group": group_id,
        }
        
        if file_id:
            data.update({
                "media": {"file": file_id},
                "message": caption or message
            })
        elif media_url:
            data.update({
                "media": {"url": media_url},
                "message": caption or message
            })
        else:
            data["message"] = message
            
        try:
            result = self._make_request("POST", "/messages", data)
            return {'success': True, 'id': result.get('id', ''), 'data': result}
        except Exception as e:
            _logger.error("Failed to send group message: %s", str(e))
            return {'success': False, 'message': str(e)}
    
    def schedule_message(self, to: str, message: str, scheduled_at: str, is_group: bool = False) -> Dict:
        """Schedule message for future delivery"""
        config = self._get_api_config()
        data = {
            "phone" if not is_group else "group": to,
            "message": message,
            "scheduled_at": scheduled_at,
            "device": config['device_id']
        }
        return self._make_request("POST", "/messages/schedule", data)
    
    def get_message_status(self, message_id: str) -> Dict:
        """Get message status"""
        return self._make_request("GET", f"/messages/{message_id}/status")
    
    def get_recent_messages(self, limit: int = 100) -> List[Dict]:
        """Get recent messages with pagination"""
        config = self._get_api_config()
        all_messages = []
        page = 0
        max_size = 500
        
        while True:
            try:
                messages = self._make_request("GET", f"/chat/{config['device_id']}/messages?page={page}&size={max_size}")
                
                if not messages or len(messages) == 0:
                    break
                    
                all_messages.extend(messages)
                
                if len(all_messages) >= limit:
                    all_messages = all_messages[:limit]
                    break
                
                if len(messages) < max_size:
                    break
                    
                page += 1
                
            except Exception as e:
                _logger.error(f"Error fetching messages page {page}: {e}")
                break
        
        _logger.info(f"Total messages fetched: {len(all_messages)}")
        return all_messages
    def get_group_info(self, group_wid: str) -> Dict:
        """Get group information"""
        config = self._get_api_config()
        return self._make_request("GET", f"/devices/{config['device_id']}/groups/{group_wid}")
