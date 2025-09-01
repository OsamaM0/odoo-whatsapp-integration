"""
WhatsApp Provider Factory
Manages provider registration and instantiation
"""
from typing import Dict, Optional, Type
from odoo import models, api, fields
from .adapters.base_adapter import IWhatsAppProvider
import logging

_logger = logging.getLogger(__name__)


class WhatsAppProviderFactory(models.AbstractModel):
    """Factory for creating WhatsApp provider instances"""
    
    _name = 'whatsapp.provider.factory'
    _description = 'WhatsApp Provider Factory'
    
    # Registry of available providers
    _provider_registry: Dict[str, Type[IWhatsAppProvider]] = {}
    
    @classmethod
    def register_provider(cls, provider_name: str, provider_class: Type[IWhatsAppProvider]):
        """Register a provider adapter"""
        cls._provider_registry[provider_name] = provider_class
        _logger.info(f"Registered WhatsApp provider: {provider_name}")
    
    @classmethod
    def get_available_providers(cls) -> Dict[str, Type[IWhatsAppProvider]]:
        """Get all registered providers"""
        return cls._provider_registry.copy()
    
    @api.model
    def create_provider(self, provider_name: str, config: Dict) -> Optional[IWhatsAppProvider]:
        """Create a provider instance"""
        if provider_name not in self._provider_registry:
            _logger.error(f"Unknown provider: {provider_name}")
            return None
        
        try:
            provider_class = self._provider_registry[provider_name]
            provider_instance = provider_class(self.env, config)
            
            # Validate configuration
            validation = provider_instance.validate_config(config)
            if not validation.get('valid'):
                _logger.error(f"Provider {provider_name} configuration invalid: {validation.get('message')}")
                return None
            
            _logger.info(f"Created provider instance: {provider_name}")
            return provider_instance
            
        except Exception as e:
            _logger.error(f"Failed to create provider {provider_name}: {e}")
            return None
    
    @api.model
    def get_provider_for_user(self, user_id: int = None) -> Optional[IWhatsAppProvider]:
        """Get provider instance for specific user based on their configuration"""
        if not user_id:
            user_id = self.env.user.id
        
        # Get user's configuration
        config_obj = self.env['whatsapp.configuration'].get_user_configuration(user_id)
        if not config_obj:
            _logger.warning(f"No WhatsApp configuration found for user {user_id}")
            return None
        
        # Create provider instance
        provider_config = {
            'token': config_obj.token,
            'supervisor_phone': config_obj.supervisor_phone,
            'device_id': config_obj.device_id,  # For backward compatibility
        }
        
        return self.create_provider(config_obj.provider, provider_config)
    
    @api.model
    def get_default_provider(self) -> Optional[IWhatsAppProvider]:
        """Get default provider instance"""
        default_provider = self.env['ir.config_parameter'].sudo().get_param(
            'whatsapp.default_provider', 'whapi'
        )
        
        # Get a default configuration (first active one)
        config_obj = self.env['whatsapp.configuration'].search([
            ('active', '=', True),
            ('provider', '=', default_provider)
        ], limit=1)
        
        if not config_obj:
            _logger.warning(f"No configuration found for default provider: {default_provider}")
            return None
        
        provider_config = {
            'token': config_obj.token,
            'supervisor_phone': config_obj.supervisor_phone,
            'device_id': config_obj.device_id,
        }
        
        return self.create_provider(default_provider, provider_config)


# Auto-register built-in providers
def _register_builtin_providers():
    """Register built-in provider adapters"""
    try:
        from .adapters.whapi_adapter import WhapiAdapter
        WhatsAppProviderFactory.register_provider('whapi', WhapiAdapter)
    except ImportError as e:
        _logger.warning(f"Failed to register WHAPI adapter: {e}")
    
    try:
        from .adapters.wassenger_adapter import WassengerAdapter
        WhatsAppProviderFactory.register_provider('wassenger', WassengerAdapter)
    except ImportError as e:
        _logger.warning(f"Failed to register Wassenger adapter: {e}")
    
    try:
        from .adapters.twilio_adapter import TwilioAdapter
        WhatsAppProviderFactory.register_provider('twilio', TwilioAdapter)
    except ImportError as e:
        _logger.warning(f"Failed to register Twilio adapter: {e}")


# Register providers when module loads
_register_builtin_providers()
