from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class InviteController(http.Controller):
    
    @http.route('/whatsapp/group/invite/<int:group_id>', type='http', auth='user', website=True)
    def group_invite_page(self, group_id, **kwargs):
        """Display a nice page with the group invite link"""
        try:
            group = request.env['whatsapp.group'].browse(group_id)
            
            if not group.exists():
                return request.render('whatsapp_integration.invite_error', {
                    'error_message': 'Group not found'
                })
            
            # Check if user has access to this group
            if not group.check_access_rights('read', raise_exception=False):
                return request.render('whatsapp_integration.invite_error', {
                    'error_message': 'Access denied'
                })
            
            # If no invite link exists, try to fetch it
            if not group.invite_link and group.provider == 'whapi':
                try:
                    group.fetch_invite_link()
                except Exception as e:
                    _logger.error(f"Failed to fetch invite link: {e}")
            
            return request.render('whatsapp_integration.group_invite_page', {
                'group': group,
            })
            
        except Exception as e:
            _logger.error(f"Error displaying invite page: {e}")
            return request.render('whatsapp_integration.invite_error', {
                'error_message': str(e)
            })
