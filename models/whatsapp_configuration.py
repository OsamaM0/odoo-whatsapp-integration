from odoo import api, fields, models
from odoo.exceptions import ValidationError
from ..constants import PROVIDERS

class WhatsAppConfiguration(models.Model):
    _name = 'whatsapp.configuration'
    _description = 'WhatsApp API Configuration'
    _order = 'name'

    name = fields.Char('Configuration Name', required=True)
    token = fields.Char('API Token', required=True)
    device_id = fields.Char('Device ID', help='Legacy field - not used with WHAPI')
    supervisor_phone = fields.Char('Supervisor Phone', required=True)
    active = fields.Boolean('Active', default=True)
    provider = fields.Selection(
        PROVIDERS,
        string='Provider', 
        default='whapi', 
        required=True
    )
    # Webhook routing key
    channel_id = fields.Char(
        'Channel ID',
        help='Identifier provided by the provider and sent in webhooks to route data to this configuration',
        index=True
    )
    
    # Access control fields
    user_ids = fields.Many2many('res.users', string='Allowed Users', 
                               help='Users who can use this configuration')
    group_ids = fields.Many2many('res.groups', string='Allowed Groups',
                                help='Groups who can use this configuration')
    
    @api.constrains('token')
    def _check_unique_token(self):
        for record in self:
            if record.active:
                existing = self.search([
                    ('token', '=', record.token),
                    ('id', '!=', record.id),
                    ('active', '=', True)
                ])
                # if existing:
                #     raise ValidationError(f"API Token is already in use by another active configuration.")

    @api.model
    def get_by_channel_id(self, channel_id: str):
        """Return active configuration matching a webhook channel_id."""
        if not channel_id:
            return None
        return self.search([
            ('active', '=', True),
            ('channel_id', '=', channel_id)
        ], limit=1)

    @api.constrains('channel_id', 'active')
    def _check_unique_channel_id_when_active(self):
        for record in self:
            if record.active and record.channel_id:
                dup = self.search([
                    ('id', '!=', record.id),
                    ('active', '=', True),
                    ('channel_id', '=', record.channel_id)
                ], limit=1)
                if dup:
                    raise ValidationError("Channel ID must be unique among active configurations.")

    @api.model
    def get_user_configuration(self, user_id=None):
        """Get the configuration accessible by the current user"""
        if not user_id:
            user_id = self.env.user.id
        
        user = self.env['res.users'].browse(user_id)
        
        # Admin users get the first active configuration if no specific assignment
        if user.has_group('whatsapp_integration.group_whatsapp_admin'):
            # First try assigned configurations
            configs = self.search([
                ('active', '=', True),
                '|', 
                ('user_ids', 'in', [user_id]),
                ('group_ids', 'in', user.groups_id.ids)
            ])
            
            # If no specific assignment, get first active configuration
            if not configs:
                configs = self.search([('active', '=', True)], limit=1)
            
            return configs[0] if configs else None
        
        # Regular users: Check configurations assigned to user directly
        configs = self.search([
            ('active', '=', True),
            ('user_ids', 'in', [user_id])
        ])
        
        # Check configurations assigned to user's groups
        if not configs:
            user_groups = user.groups_id.ids
            configs = self.search([
                ('active', '=', True),
                ('group_ids', 'in', user_groups)
            ])
        
        return configs[0] if configs else None

    @api.model
    def get_user_accessible_config_ids(self, user_id=None):
        """Get all configuration IDs accessible by the current user"""
        if not user_id:
            user_id = self.env.user.id
        
        user = self.env['res.users'].browse(user_id)
        
        # Admin users see all configurations
        if user.has_group('whatsapp_integration.group_whatsapp_admin'):
            configs = self.search([('active', '=', True)])
            return configs.ids
        
        # Regular users: Check configurations assigned to user directly
        configs = self.search([
            ('active', '=', True),
            ('user_ids', 'in', [user_id])
        ])
        
        # Check configurations assigned to user's groups
        if not configs:
            user_groups = user.groups_id.ids
            configs = self.search([
                ('active', '=', True),
                ('group_ids', 'in', user_groups)
            ])
        
        return configs.ids

    def name_get(self):
        result = []
        for record in self:
            provider_name = dict(record._fields['provider'].selection).get(record.provider, record.provider)
            name = f"{record.name} ({provider_name})"
            result.append((record.id, name))
        return result
