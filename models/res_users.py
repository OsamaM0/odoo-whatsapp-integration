from odoo import api, fields, models

class ResUsers(models.Model):
    _inherit = 'res.users'
    
    @api.model
    def whatsapp_device_id(self):
        """Get the device ID for the current user's WhatsApp configuration"""
        config = self.env['whatsapp.configuration'].get_user_configuration(self.id)
        return config.device_id if config else False
