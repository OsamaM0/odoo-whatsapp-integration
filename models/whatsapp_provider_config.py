"""
Provider Configuration Model
Stores provider-specific settings and credentials
"""
from odoo import models, fields, api
from odoo.exceptions import ValidationError
import json
from ..constants import PROVIDERS


class WhatsAppProviderConfig(models.Model):
    """Provider-specific configuration and credentials"""
    
    _name = 'whatsapp.provider.config'
    _description = 'WhatsApp Provider Configuration'
    _order = 'provider, name'
    
    name = fields.Char('Configuration Name', required=True)
    provider = fields.Selection(PROVIDERS, string='Provider', required=True)
    
    # Core settings
    active = fields.Boolean('Active', default=True)
    is_default = fields.Boolean('Default Configuration', 
                               help='Use this as default configuration for the provider')
    
    # API credentials (stored securely)
    api_token = fields.Char('API Token', help='Primary API token/key')
    api_secret = fields.Char('API Secret', help='API secret if required')
    account_id = fields.Char('Account ID', help='Account/Customer ID')
    instance_id = fields.Char('Instance ID', help='Instance/Device ID')
    
    # Endpoint configuration
    base_url = fields.Char('Base URL', help='Custom API base URL if different from default')
    webhook_url = fields.Char('Webhook URL', help='Webhook endpoint URL')
    webhook_secret = fields.Char('Webhook Secret', help='Webhook validation secret')
    
    # Provider-specific settings (stored as JSON)
    provider_settings = fields.Text('Provider Settings', 
                                   help='JSON configuration for provider-specific options')
    
    # Rate limiting and performance
    rate_limit_per_minute = fields.Integer('Rate Limit (per minute)', default=60)
    max_retries = fields.Integer('Max Retries', default=3)
    timeout_seconds = fields.Integer('Timeout (seconds)', default=30)
    
    # Access control
    user_ids = fields.Many2many('res.users', string='Allowed Users')
    group_ids = fields.Many2many('res.groups', string='Allowed Groups')
    
    # Monitoring
    last_health_check = fields.Datetime('Last Health Check')
    health_status = fields.Selection([
        ('unknown', 'Unknown'),
        ('healthy', 'Healthy'),
        ('degraded', 'Degraded'),
        ('unhealthy', 'Unhealthy')
    ], string='Health Status', default='unknown')
    health_message = fields.Text('Health Message')
    
    # Statistics
    messages_sent_today = fields.Integer('Messages Sent Today', readonly=True)
    messages_sent_month = fields.Integer('Messages Sent This Month', readonly=True)
    last_message_sent = fields.Datetime('Last Message Sent', readonly=True)
    
    @api.constrains('is_default', 'provider', 'active')
    def _check_default_config(self):
        """Ensure only one default config per provider"""
        for record in self:
            if record.is_default and record.active:
                existing_default = self.search([
                    ('provider', '=', record.provider),
                    ('is_default', '=', True),
                    ('active', '=', True),
                    ('id', '!=', record.id)
                ])
                if existing_default:
                    raise ValidationError(
                        f"Only one default configuration allowed per provider. "
                        f"'{existing_default.name}' is already set as default for {record.provider}."
                    )
    
    @api.model
    def get_default_config(self, provider: str):
        """Get default configuration for provider"""
        return self.search([
            ('provider', '=', provider),
            ('is_default', '=', True),
            ('active', '=', True)
        ], limit=1)
    
    @api.model
    def get_user_configs(self, user_id: int = None, provider: str = None):
        """Get configurations accessible by user"""
        if not user_id:
            user_id = self.env.user.id
        
        user = self.env['res.users'].browse(user_id)
        
        domain = [('active', '=', True)]
        if provider:
            domain.append(('provider', '=', provider))
        
        # Check direct user assignment
        configs = self.search(domain + [('user_ids', 'in', [user_id])])
        
        # Check group assignment if no direct configs
        if not configs:
            user_groups = user.groups_id.ids
            configs = self.search(domain + [('group_ids', 'in', user_groups)])
        
        return configs
    
    def get_provider_settings_dict(self):
        """Parse provider settings JSON to dictionary"""
        if not self.provider_settings:
            return {}
        
        try:
            return json.loads(self.provider_settings)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_provider_settings(self, settings_dict: dict):
        """Set provider settings from dictionary"""
        self.provider_settings = json.dumps(settings_dict)
    
    def test_connection(self):
        """Test connection to provider API"""
        try:
            from ..services.whatsapp_provider_factory import WhatsAppProviderFactory
            
            factory = self.env['whatsapp.provider.factory']
            config = self._build_provider_config()
            
            provider = factory.create_provider(self.provider, config)
            if not provider:
                return {
                    'success': False,
                    'message': 'Failed to create provider instance'
                }
            
            health_result = provider.health_check()
            
            # Update health status
            self.write({
                'last_health_check': fields.Datetime.now(),
                'health_status': 'healthy' if health_result.get('healthy') else 'unhealthy',
                'health_message': health_result.get('message', '')
            })
            
            return {
                'success': health_result.get('healthy', False),
                'message': health_result.get('message', ''),
                'data': health_result.get('data', {})
            }
            
        except Exception as e:
            self.write({
                'last_health_check': fields.Datetime.now(),
                'health_status': 'unhealthy',
                'health_message': str(e)
            })
            
            return {
                'success': False,
                'message': f'Connection test failed: {str(e)}'
            }
    
    def _build_provider_config(self):
        """Build configuration dictionary for provider"""
        config = {
            'token': self.api_token,
            'api_secret': self.api_secret,
            'account_id': self.account_id,
            'instance_id': self.instance_id,
            'base_url': self.base_url,
            'webhook_secret': self.webhook_secret,
            'rate_limit': self.rate_limit_per_minute,
            'max_retries': self.max_retries,
            'timeout': self.timeout_seconds,
        }
        
        # Add provider-specific settings
        provider_settings = self.get_provider_settings_dict()
        config.update(provider_settings)
        
        # Provider-specific mappings
        if self.provider == 'twilio':
            config.update({
                'account_sid': self.account_id,
                'auth_token': self.api_token,
                'from_number': provider_settings.get('from_number', '')
            })
        elif self.provider == 'wassenger':
            config.update({
                'device_id': self.instance_id,
                'supervisor_phone': provider_settings.get('supervisor_phone', '')
            })
        elif self.provider == 'whapi':
            config.update({
                'supervisor_phone': provider_settings.get('supervisor_phone', '')
            })
        
        return config
    
    def increment_message_count(self):
        """Increment daily/monthly message counters"""
        today = fields.Date.today()
        current_month = today.replace(day=1)
        
        # Reset daily counter if it's a new day
        if not self.last_message_sent or self.last_message_sent.date() != today:
            self.messages_sent_today = 1
        else:
            self.messages_sent_today += 1
        
        # Reset monthly counter if it's a new month
        if not self.last_message_sent or self.last_message_sent.date() < current_month:
            self.messages_sent_month = 1
        else:
            self.messages_sent_month += 1
        
        self.last_message_sent = fields.Datetime.now()
    
    def name_get(self):
        """Display name with provider info"""
        result = []
        for record in self:
            provider_name = dict(record._fields['provider'].selection).get(record.provider, record.provider)
            name = f"{record.name} ({provider_name})"
            if record.is_default:
                name += " [Default]"
            result.append((record.id, name))
        return result
