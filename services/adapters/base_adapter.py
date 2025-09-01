"""
Base WhatsApp Provider Adapter Interface
Defines the contract that all WhatsApp providers must implement
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union
from odoo import models, api, fields
from ..dto import MessageDTO, MediaMessageDTO, ContactDTO, GroupDTO, GroupParticipantDTO
from ...constants import MAX_RETRIES, RETRY_BACKOFF_FACTOR, RETRY_STATUS_CODES


class IWhatsAppProvider(ABC):
    """Abstract base class for WhatsApp providers"""
    
    @abstractmethod
    def validate_config(self, config: Dict) -> Dict[str, Union[bool, str]]:
        """
        Validate provider configuration
        
        Args:
            config: Provider configuration dictionary
            
        Returns:
            Dict with 'valid': bool and 'message': str
        """
        pass
    
    @abstractmethod
    def health_check(self) -> Dict[str, Union[bool, str, Dict]]:
        """
        Check provider health/connectivity
        
        Returns:
            Dict with 'healthy': bool, 'message': str, 'data': dict
        """
        pass
    
    # Messaging Methods
    @abstractmethod
    def send_text_message(self, to: str, message: str, **kwargs) -> Dict:
        """
        Send text message
        
        Args:
            to: Recipient ID (phone number or group ID)
            message: Text message content
            **kwargs: Provider-specific parameters
            
        Returns:
            Dict with 'success': bool, 'message_id': str, 'data': dict
        """
        pass
    
    @abstractmethod
    def send_media_message(self, to: str, media_dto: MediaMessageDTO, **kwargs) -> Dict:
        """
        Send media message
        
        Args:
            to: Recipient ID
            media_dto: Media message data transfer object
            **kwargs: Provider-specific parameters
            
        Returns:
            Dict with 'success': bool, 'message_id': str, 'data': dict
        """
        pass
    
    @abstractmethod
    def get_message_status(self, message_id: str) -> Dict:
        """
        Get message delivery status
        
        Args:
            message_id: Message identifier
            
        Returns:
            Dict with 'status': str, 'timestamp': int, 'data': dict
        """
        pass
    
    # Contact Management
    @abstractmethod
    def get_contacts(self, limit: int = 100, offset: int = 0) -> Dict:
        """
        Retrieve contacts
        
        Args:
            limit: Maximum contacts to retrieve
            offset: Offset for pagination
            
        Returns:
            Dict with 'contacts': List[ContactDTO], 'total': int
        """
        pass
    
    @abstractmethod
    def check_contact_exists(self, phone_numbers: List[str]) -> Dict:
        """
        Check if phone numbers exist on WhatsApp
        
        Args:
            phone_numbers: List of phone numbers to check
            
        Returns:
            Dict with 'results': List[Dict] with phone and exists status
        """
        pass
    
    # Group Management
    @abstractmethod
    def get_groups(self, limit: int = 100, offset: int = 0) -> Dict:
        """
        Retrieve groups
        
        Args:
            limit: Maximum groups to retrieve
            offset: Offset for pagination
            
        Returns:
            Dict with 'groups': List[GroupDTO], 'total': int
        """
        pass
    
    @abstractmethod
    def create_group(self, name: str, participants: List[str], description: str = "") -> Dict:
        """
        Create new WhatsApp group
        
        Args:
            name: Group name
            participants: List of participant phone numbers
            description: Group description
            
        Returns:
            Dict with 'success': bool, 'group_id': str, 'data': dict
        """
        pass
    
    @abstractmethod
    def get_group_info(self, group_id: str) -> Optional[GroupDTO]:
        """
        Get group information
        
        Args:
            group_id: Group identifier
            
        Returns:
            GroupDTO or None if not found
        """
        pass
    
    @abstractmethod
    def get_group_invite_link(self, group_id: str) -> Optional[str]:
        """
        Get group invite link
        
        Args:
            group_id: Group identifier
            
        Returns:
            Invite link string or None
        """
        pass
    
    @abstractmethod
    def add_group_participants(self, group_id: str, participants: List[str]) -> Dict:
        """
        Add participants to group
        
        Args:
            group_id: Group identifier
            participants: List of participant phone numbers
            
        Returns:
            Dict with 'success': bool, 'added': List[str], 'failed': List[str]
        """
        pass
    
    @abstractmethod
    def remove_group_participants(self, group_id: str, participants: List[str]) -> Dict:
        """
        Remove participants from group
        
        Args:
            group_id: Group identifier
            participants: List of participant phone numbers
            
        Returns:
            Dict with 'success': bool, 'removed': List[str], 'failed': List[str]
        """
        pass
    
    # Webhook Methods
    @abstractmethod
    def validate_webhook(self, headers: Dict, body: Dict, signature: str = None) -> bool:
        """
        Validate webhook authenticity
        
        Args:
            headers: HTTP headers
            body: Webhook payload
            signature: Webhook signature if applicable
            
        Returns:
            True if valid, False otherwise
        """
        pass
    
    @abstractmethod
    def parse_webhook_message(self, webhook_data: Dict) -> List[MessageDTO]:
        """
        Parse webhook data into message DTOs
        
        Args:
            webhook_data: Raw webhook payload
            
        Returns:
            List of MessageDTO objects
        """
        pass
    
    @abstractmethod
    def parse_webhook_status(self, webhook_data: Dict) -> List[Dict]:
        """
        Parse webhook status updates
        
        Args:
            webhook_data: Raw webhook payload
            
        Returns:
            List of status update dictionaries
        """
        pass
    
    # Media Management
    @abstractmethod
    def upload_media(self, media_data: bytes, filename: str, media_type: str) -> Dict:
        """
        Upload media to provider
        
        Args:
            media_data: Media binary data
            filename: Original filename
            media_type: Media type (image, video, audio, document)
            
        Returns:
            Dict with 'success': bool, 'media_id': str, 'url': str
        """
        pass
    
    @abstractmethod
    def download_media(self, media_id: str) -> Dict:
        """
        Download media from provider
        
        Args:
            media_id: Media identifier
            
        Returns:
            Dict with 'success': bool, 'data': bytes, 'content_type': str
        """
        pass


class BaseWhatsAppAdapter(models.AbstractModel, IWhatsAppProvider):
    """
    Base Odoo model for WhatsApp adapters
    Implements common functionality and Odoo integration
    """
    _name = 'whatsapp.adapter.base'
    _description = 'Base WhatsApp Adapter'
    
    def __init__(self, env, config: Dict):
        """
        Initialize adapter with configuration
        
        Args:
            env: Odoo environment
            config: Provider configuration
        """
        super().__init__()
        self.env = env
        self.config = config
        self._http_client = None
    
    @property
    def provider_name(self) -> str:
        """Get provider name"""
        return self.__class__.__name__.replace('Adapter', '').lower()
    
    @api.model
    def get_http_client(self):
        """Get or create HTTP client with retry logic"""
        if not self._http_client:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            
            retry_strategy = Retry(
                total=MAX_RETRIES,
                backoff_factor=RETRY_BACKOFF_FACTOR,
                status_forcelist=RETRY_STATUS_CODES,
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            
            session = requests.Session()
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            self._http_client = session
        
        return self._http_client
    
    def log_api_call(self, method: str, endpoint: str, success: bool, 
                     response_time: float = None, error: str = None):
        """Log API call for observability"""
        try:
            self.env['whatsapp.audit.log'].sudo().create({
                'provider': self.provider_name,
                'method': method,
                'endpoint': endpoint,
                'success': success,
                'response_time': response_time,
                'error_message': error,
                'timestamp': fields.Datetime.now(),
            })
        except Exception as e:
            # Don't fail operations due to logging issues
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(f"Failed to log API call: {e}")
    
    def validate_phone_number(self, phone: str) -> str:
        """Validate and normalize phone number"""
        # Remove all non-digit characters
        clean_phone = ''.join(filter(str.isdigit, phone))
        
        # Basic validation
        if len(clean_phone) < 10:
            raise ValueError(f"Invalid phone number: {phone}")
        
        return clean_phone
    
    def handle_api_error(self, error: Exception, context: str = "") -> Dict:
        """Standardized error handling"""
        import logging
        _logger = logging.getLogger(__name__)
        
        error_msg = f"{context}: {str(error)}" if context else str(error)
        _logger.error(error_msg)
        
        return {
            'success': False,
            'error': error_msg,
            'error_type': type(error).__name__
        }
