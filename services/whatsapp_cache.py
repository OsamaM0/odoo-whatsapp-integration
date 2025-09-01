"""
WhatsApp Integration Caching
Redis-based caching for improved performance
"""
import json
import logging
from typing import Optional, Any, Dict
from odoo import models, api, fields, tools

_logger = logging.getLogger(__name__)


class WhatsAppCache(models.AbstractModel):
    """Cache service for WhatsApp operations"""
    
    _name = 'whatsapp.cache'
    _description = 'WhatsApp Cache Service'
    
    # Cache TTL settings (in seconds)
    CONTACT_TTL = 3600      # 1 hour
    GROUP_TTL = 1800        # 30 minutes
    MESSAGE_STATUS_TTL = 300 # 5 minutes
    PROVIDER_CONFIG_TTL = 86400  # 24 hours
    
    @api.model
    def get(self, key: str) -> Optional[Any]:
        """Get cached value"""
        try:
            cached = self.env.cache.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            _logger.warning(f"Cache get failed for key {key}: {e}")
        return None
    
    @api.model
    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set cached value"""
        try:
            serialized = json.dumps(value, default=str)
            self.env.cache.set(key, serialized, ttl)
            return True
        except Exception as e:
            _logger.warning(f"Cache set failed for key {key}: {e}")
            return False
    
    @api.model
    def delete(self, key: str) -> bool:
        """Delete cached value"""
        try:
            self.env.cache.delete(key)
            return True
        except Exception as e:
            _logger.warning(f"Cache delete failed for key {key}: {e}")
            return False
    
    @api.model
    def get_contact_key(self, contact_id: str, provider: str) -> str:
        """Generate cache key for contact"""
        return f"whatsapp:contact:{provider}:{contact_id}"
    
    @api.model
    def get_group_key(self, group_id: str, provider: str) -> str:
        """Generate cache key for group"""
        return f"whatsapp:group:{provider}:{group_id}"
    
    @api.model
    def get_message_status_key(self, message_id: str) -> str:
        """Generate cache key for message status"""
        return f"whatsapp:message_status:{message_id}"
    
    @api.model
    def cache_contact(self, contact_data: Dict, provider: str) -> bool:
        """Cache contact data"""
        if not contact_data.get('contact_id'):
            return False
        
        key = self.get_contact_key(contact_data['contact_id'], provider)
        return self.set(key, contact_data, self.CONTACT_TTL)
    
    @api.model
    def get_cached_contact(self, contact_id: str, provider: str) -> Optional[Dict]:
        """Get cached contact data"""
        key = self.get_contact_key(contact_id, provider)
        return self.get(key)
    
    @api.model
    def cache_group(self, group_data: Dict, provider: str) -> bool:
        """Cache group data"""
        if not group_data.get('group_id'):
            return False
        
        key = self.get_group_key(group_data['group_id'], provider)
        return self.set(key, group_data, self.GROUP_TTL)
    
    @api.model
    def get_cached_group(self, group_id: str, provider: str) -> Optional[Dict]:
        """Get cached group data"""
        key = self.get_group_key(group_id, provider)
        return self.get(key)
    
    @api.model
    def invalidate_contact_cache(self, contact_id: str, provider: str) -> bool:
        """Invalidate contact cache"""
        key = self.get_contact_key(contact_id, provider)
        return self.delete(key)
    
    @api.model
    def invalidate_group_cache(self, group_id: str, provider: str) -> bool:
        """Invalidate group cache"""
        key = self.get_group_key(group_id, provider)
        return self.delete(key)
