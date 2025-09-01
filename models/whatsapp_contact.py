from odoo import models, fields, api, SUPERUSER_ID
import logging
from ..constants import PROVIDERS

_logger = logging.getLogger(__name__)

class WhatsAppContact(models.Model):
    _name = 'whatsapp.contact'
    _description = 'WhatsApp Contact'
    _rec_name = 'display_name'

    # Core fields available in WHAPI
    contact_id = fields.Char('Contact ID', required=True, index=True, help='WHAPI Contact ID or Phone Number')
    phone = fields.Char('Phone Number', index=True, help='Phone number (may not always be available)')
    name = fields.Char('Name', help='Contact name')
    pushname = fields.Char('Push Name', help='Display name from WhatsApp')
    display_name = fields.Char('Display Name', compute='_compute_display_name', store=True)
    
    # Legacy fields for backward compatibility with Wassenger
    wid = fields.Char('Legacy WID', help='Legacy Wassenger ID for backward compatibility')
    
    # Status and control fields
    is_active = fields.Boolean('Active', default=True)
    synced_at = fields.Datetime('Synced At')
    created_at = fields.Datetime('Created At', default=fields.Datetime.now)
    updated_at = fields.Datetime('Updated At')
    provider = fields.Selection(
        PROVIDERS,
        string='Provider', 
        default='whapi'
    )
    
    # Only keep essential boolean fields that we can actually determine
    isWAContact = fields.Boolean('WhatsApp Contact', default=True, help='Always true for WHAPI contacts')
    is_phone_contact = fields.Boolean('Phone Contact', default=False, help='Contact from phone address book')
    is_chat_contact = fields.Boolean('Chat Contact', default=False, help='Contact from chat conversations')
    
    # Configuration tracking for permission control
    configuration_id = fields.Many2one('whatsapp.configuration', string='Configuration', 
                                      help='WhatsApp configuration this contact belongs to')
    
    # Relationships - updated for clean WHAPI schema
    group_ids = fields.Many2many('whatsapp.group', 'whatsapp_group_contact_rel', 
                                'contact_id', 'group_id', string='Groups')
    message_ids = fields.One2many('whatsapp.message', 'contact_id', string='Messages')
    
    # Computed fields
    sent_message_count = fields.Integer('Sent Messages', compute='_compute_message_counts')
    group_count = fields.Integer('Group Count', compute='_compute_group_count')
    
    _sql_constraints = [
        ('contact_id_unique', 'unique(contact_id)', 'Contact ID must be unique!'),
    ]
    
    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        """Override search to filter by user's accessible configurations"""
        # Skip filtering for superuser or when explicitly requested
        if self.env.user.id == SUPERUSER_ID or self.env.context.get('skip_config_filter'):
            return super().search(args, offset=offset, limit=limit, order=order, count=count)

        # Only apply filtering for non-admin users
        if not self.env.user.has_group('whatsapp_integration.group_whatsapp_admin'):
            config_ids = self.env['whatsapp.configuration'].get_user_accessible_config_ids()
            if config_ids:
                # Add configuration filter to the domain
                config_domain = [('configuration_id', 'in', config_ids)]
                args = args + config_domain if args else config_domain
            else:
                # User has no accessible configurations, return empty set
                args = [('id', '=', False)]
        
        return super().search(args, offset=offset, limit=limit, order=order, count=count)
    
    @api.depends('name', 'pushname', 'phone', 'contact_id')
    def _compute_display_name(self):
        for record in self:
            # Priority: pushname > name > phone > contact_id
            record.display_name = (
                record.pushname or 
                record.name or 
                record.phone or 
                record.contact_id or 
                'Unknown'
            )
    
    @api.depends('message_ids')
    def _compute_message_counts(self):
        for contact in self:
            # Count messages for this contact using clean WHAPI schema
            contact.sent_message_count = self.env['whatsapp.message'].search_count([
                ('contact_id', '=', contact.id)
            ])
    
    @api.depends('group_ids')
    def _compute_group_count(self):
        for contact in self:
            contact.group_count = len(contact.group_ids)
    
    def write(self, vals):
        """Override write to update timestamp"""
        vals['updated_at'] = fields.Datetime.now()
        return super().write(vals)
    
    @api.model
    def create_from_api_data(self, api_data, match_by_phone=True, provider='whapi'):
        """Create contact from API data with clean field mapping"""
        # Get the configuration for the current user
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if not config:
            _logger.warning("No accessible WhatsApp configuration found for current user")
            return False
            
        if provider == 'whapi':
            # WHAPI format - clean mapping
            contact_id = api_data.get('id', '')
            pushname = api_data.get('pushname', '')
            name = api_data.get('name', '')
            # In WHAPI, phone might not always be available, use contact_id as fallback
            phone = contact_id if contact_id.isdigit() else ''
            # Get contact type flags
            is_phone_contact = api_data.get('is_phone_contact', False)
            is_chat_contact = api_data.get('is_chat_contact', False)
        else:
            # Wassenger format - for backward compatibility
            contact_id = api_data.get('phone', '')
            phone = api_data.get('phone', '')
            name = api_data.get('name', '')
            pushname = ''
            is_phone_contact = True
            is_chat_contact = False
        
        if not contact_id:
            _logger.warning(f"Skipping contact creation due to missing contact_id: {api_data}")
            return False

        # Check for existing contact by contact_id
        existing = self.search([('contact_id', '=', contact_id)], limit=1)
        if existing:
            # Update existing contact with new data
            try:
                update_vals = {
                    'synced_at': fields.Datetime.now(),
                    'provider': provider,
                }
                
                if provider == 'whapi':
                    update_vals.update({
                        'pushname': pushname,
                        'name': name or existing.name,
                        'phone': phone or existing.phone,
                        'isWAContact': True,
                        'is_phone_contact': is_phone_contact or existing.is_phone_contact,
                        'is_chat_contact': is_chat_contact or existing.is_chat_contact,
                    })
                else:
                    update_vals.update({
                        'name': name or existing.name,
                        'wid': api_data.get('wid', existing.wid),
                        'is_phone_contact': is_phone_contact,
                        'is_chat_contact': is_chat_contact,
                    })
                
                existing.write(update_vals)
                return existing
            except Exception as e:
                _logger.error(f"Error updating existing contact {contact_id}: {e}")
                return existing

        # Create new contact
        try:
            vals = {
                'contact_id': contact_id,
                'synced_at': fields.Datetime.now(),
                'provider': provider,
                'isWAContact': True,
                'is_phone_contact': is_phone_contact,
                'is_chat_contact': is_chat_contact,
                'configuration_id': config.id,  # Link to configuration
            }
            
            if provider == 'whapi':
                # WHAPI specific fields - only what's actually available
                vals.update({
                    'pushname': pushname,
                    'name': name,
                    'phone': phone,
                })
            else:
                # Wassenger specific fields - for backward compatibility
                vals.update({
                    'name': name or contact_id,
                    'phone': phone,
                    'wid': api_data.get('wid', contact_id),
                })
            
            return self.create(vals)
            
        except Exception as e:
            _logger.error(f"Failed to create contact for contact_id {contact_id}: {e}")
            return False
    
    def action_view_sent_messages(self):
        """Action to view messages for this contact"""
        return {
            'type': 'ir.actions.act_window',
            'name': f'Messages - {self.display_name}',
            'res_model': 'whatsapp.message',
            'view_mode': 'tree,form',
            'domain': [('contact_id', '=', self.id)],
            'context': {'default_contact_id': self.id}
        }
    
    def action_view_groups(self):
        """Action to view contact groups"""
        return {
            'type': 'ir.actions.act_window',
            'name': f'Groups - {self.display_name}',
            'res_model': 'whatsapp.group',
            'view_mode': 'tree,form',
            'domain': [('participant_ids', 'in', [self.id])],
        }
    
    def sync_contact_info(self):
        """Sync contact info from API"""
        # Determine which service to use based on configuration
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if config and config.provider == 'whapi':
            api_service = self.env['whapi.service']
        else:
            api_service = self.env['wassenger.api']
        
        try:
            # Use appropriate ID based on provider
            contact_identifier = self.contact_id if config and config.provider == 'whapi' else self.wid
            contact_info = api_service.get_contact_info(contact_identifier)
            
            if contact_info:
                update_vals = {
                    'synced_at': fields.Datetime.now(),
                }
                
                # Handle different response formats - only use available fields
                if config and config.provider == 'whapi':
                    # WHAPI format - only available fields
                    update_vals.update({
                        'pushname': contact_info.get('pushname', self.pushname) or self.pushname,
                        'name': contact_info.get('name', self.name) or self.name,
                    })
                else:
                    # Wassenger format - legacy support
                    update_vals.update({
                        'name': contact_info.get('name', self.name),
                    })
                
                self.write(update_vals)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync Complete',
                    'message': 'Contact information synced successfully',
                    'type': 'success',
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync Failed',
                    'message': str(e),
                    'type': 'danger',
                }
            }
    
    def check_whatsapp_status(self):
        """Check if contact exists on WhatsApp"""
        # Determine which service to use based on configuration
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if config and config.provider == 'whapi':
            api_service = self.env['whapi.service']
        else:
            api_service = self.env['wassenger.api']
        
        try:
            if config and config.provider == 'whapi':
                # Use WHAPI contact validation with clean phone/contact_id
                phone_to_check = self.phone or self.contact_id
                if not phone_to_check:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Validation Failed',
                            'message': 'No phone number available to validate',
                            'type': 'warning',
                        }
                    }
                
                result = api_service.check_contacts_exist([phone_to_check])
                contacts = result.get('contacts', [])
                exists = False
                if contacts:
                    contact_result = contacts[0]
                    exists = contact_result.get('status') == 'valid'
            else:
                # Use Wassenger method
                exists = api_service.check_number_exists(self.phone or self.contact_id)
            
            self.isWAContact = exists
            message = 'Contact exists on WhatsApp' if exists else 'Contact not found on WhatsApp'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'WhatsApp Status',
                    'message': message,
                    'type': 'success' if exists else 'warning',
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Check Failed',
                    'message': str(e),
                    'type': 'danger',
                }
            }
    
    def send_message(self):
        """Open wizard to send message to this contact"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send Message',
            'res_model': 'whatsapp.send.message.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_recipient_id': self.id,
                'default_phone': self.phone or self.contact_id,
            }
        }
    
    @api.model
    def sync_all_contacts_from_api(self):
        """Sync all contacts from API with improved error handling"""
        # Get configuration for the current user
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if not config:
            return {
                'success': False,
                'message': 'No accessible WhatsApp configuration found for current user',
                'count': 0
            }
            
        # Determine which service to use based on configuration
        if config and config.provider == 'whapi':
            api_service = self.env['whapi.service']
        else:
            api_service = self.env['wassenger.api']
        
        try:
            # Get contacts from API
            if config and config.provider == 'whapi':
                # WHAPI: Get both phone contacts and chat contacts
                all_contacts = []
                
                # 1. Get phone contacts (real contacts from user's phone)
                offset = 0
                count = 500
                
                _logger.info("Syncing phone contacts from WHAPI...")
                while True:
                    result = api_service.get_contacts(count=count, offset=offset)
                    api_contacts = result.get('contacts', [])
                    
                    if not api_contacts:
                        break
                    
                    # Mark as phone contacts
                    for contact in api_contacts:
                        contact['is_phone_contact'] = True
                    
                    all_contacts.extend(api_contacts)
                    
                    if len(api_contacts) < count:
                        break
                    
                    offset += count
                
                # 2. Get chat contacts (people you've chatted with)
                offset = 0
                _logger.info("Syncing chat contacts from WHAPI...")
                while True:
                    result = api_service.get_chats(count=count, offset=offset)
                    api_chats = result.get('chats', [])
                    
                    if not api_chats:
                        break
                    
                    # Convert chats to contact format and mark as chat contacts
                    for chat in api_chats:
                        # Only process individual chats (not groups)
                        if chat.get('type') == 'chat':
                            contact = {
                                'id': chat.get('id', ''),
                                'name': chat.get('name', ''),
                                'pushname': chat.get('pushname', ''),
                                'is_phone_contact': False,
                                'is_chat_contact': True
                            }
                            all_contacts.append(contact)
                    
                    if len(api_chats) < count:
                        break
                    
                    offset += count
            else:
                # Wassenger method
                all_contacts = api_service.get_contacts()
                for contact in all_contacts:
                    contact['is_phone_contact'] = True
            
            synced_count = 0
            errors = []
            
            for api_contact in all_contacts:
                if config and config.provider == 'whapi':
                    # WHAPI format: clean field mapping
                    contact_id = api_contact.get('id', '')
                    name = api_contact.get('name', '')
                    pushname = api_contact.get('pushname', '')
                    is_phone_contact = api_contact.get('is_phone_contact', False)
                    is_chat_contact = api_contact.get('is_chat_contact', False)
                else:
                    # Wassenger format
                    contact_id = api_contact.get('phone', '')
                    name = api_contact.get('name', '')
                    pushname = ''
                    is_phone_contact = True
                    is_chat_contact = False
                
                if not contact_id:
                    continue
                
                try:
                    # Use savepoint for each contact to isolate errors
                    with self.env.cr.savepoint():
                        existing = self.search([('contact_id', '=', contact_id)], limit=1)
                        
                        if not existing:
                            # Create new contact with enhanced data
                            contact_data = api_contact.copy()
                            contact_data['is_phone_contact'] = is_phone_contact
                            contact_data['is_chat_contact'] = is_chat_contact
                            
                            contact = self.create_from_api_data(contact_data, provider=config.provider if config else 'whapi')
                            if contact:
                                synced_count += 1
                        else:
                            # Update existing contact with clean fields
                            update_vals = {
                                'synced_at': fields.Datetime.now(),
                                'provider': config.provider if config else 'whapi',
                            }
                            
                            if config and config.provider == 'whapi':
                                # WHAPI specific updates - only available fields
                                update_vals.update({
                                    'name': name or existing.name,
                                    'pushname': pushname or existing.pushname,
                                    'isWAContact': True,
                                })
                                
                                # Update contact type flags if available
                                if hasattr(existing, 'is_phone_contact'):
                                    update_vals['is_phone_contact'] = is_phone_contact or getattr(existing, 'is_phone_contact', False)
                                if hasattr(existing, 'is_chat_contact'):
                                    update_vals['is_chat_contact'] = is_chat_contact or getattr(existing, 'is_chat_contact', False)
                            else:
                                # Wassenger specific updates
                                update_vals.update({
                                    'name': name or existing.name,
                                })
                            
                            existing.write(update_vals)
                            
                except Exception as e:
                    error_msg = f"Error syncing contact {contact_id}: {str(e)}"
                    errors.append(error_msg)
                    _logger.error(error_msg)
                    continue
            
            if errors:
                return {
                    'success': False,
                    'message': f'Synced {synced_count} contacts with {len(errors)} errors',
                    'count': synced_count,
                    'errors': errors[:5]  # Return first 5 errors
                }
            else:
                return {
                    'success': True,
                    'message': f'Synced {synced_count} contacts',
                    'count': synced_count
                }
                
        except Exception as e:
            _logger.error(f"Contact sync failed: {str(e)}")
            return {
                'success': False,
                'message': str(e),
                'count': 0
            }
