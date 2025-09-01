from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import ValidationError
from datetime import datetime
import logging
from ..constants import PROVIDERS

_logger = logging.getLogger(__name__)

class WhatsAppGroup(models.Model):
    _name = 'whatsapp.group'
    _description = 'WhatsApp Group'
    _rec_name = 'name'

    # Core fields available in WHAPI
    group_id = fields.Char('Group ID', index=True, help='WHAPI Group ID (e.g., xxx@g.us)', copy=False)
    name = fields.Char('Group Name', required=True)
    description = fields.Text('Description')
    
    # WHAPI metadata stored as JSON
    metadata = fields.Text('Metadata', help='Additional WHAPI group metadata as JSON')
    
    # Status and control fields
    is_active = fields.Boolean('Active', default=True)
    synced_at = fields.Datetime('Synced At')
    created_at = fields.Datetime('Created At', default=fields.Datetime.now)
    updated_at = fields.Datetime('Updated At')
    provider = fields.Selection(PROVIDERS, string='Provider', default='whapi')
    
    # Configuration tracking for permission control
    configuration_id = fields.Many2one('whatsapp.configuration', string='Configuration', 
                                      help='WhatsApp configuration this group belongs to')
    
    # Legacy fields for backward compatibility
    wid = fields.Char('Legacy WID', help='Legacy Wassenger WID for backward compatibility')
    
    # Relationships - Updated for clean WHAPI schema
    participant_ids = fields.Many2many('whatsapp.contact', 'whatsapp_group_contact_rel',
                                     'group_id', 'contact_id', string='Participants')
    message_ids = fields.One2many('whatsapp.message', 'group_id', string='Messages')
    participant_count = fields.Integer('Participant Count', compute='_compute_participant_count')
    message_count = fields.Integer('Message Count', compute='_compute_message_count', store=True)
    latest_messages_count = fields.Integer('Latest Messages Count', compute='_compute_latest_messages_count', store=True)
    last_message_date = fields.Datetime('Last Message', compute='_compute_last_message_date')
    
    # Invite link fields
    invite_code = fields.Char('Invite Code', help='WhatsApp group invite code')
    invite_fetched_at = fields.Datetime('Invite Fetched At', help='When the invite code was last fetched')
    
    _sql_constraints = [
        ('group_id_unique', 'unique(group_id)', 'Group ID must be unique when specified!'),
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
    
    @api.constrains('group_id')
    def _check_group_id_after_create(self):
        """Ensure group_id is set after creation for active groups"""
        for record in self:
            # Only check if record exists, is active, and group_id is still empty
            if (record.id and record.is_active and not record.group_id and 
                not self.env.context.get('skip_group_id_check') and
                not self.env.context.get('from_api_sync')):
                # This is a soft warning - the group creation might be in progress
                _logger.warning(f"Group '{record.name}' was created without a group_id. API creation might have failed.")
    
    @api.depends('participant_ids')
    def _compute_participant_count(self):
        for group in self:
            group.participant_count = len(group.participant_ids)
    
    @api.depends('message_ids')
    def _compute_message_count(self):
        for group in self:
            group.message_count = len(group.message_ids)
    
    @api.depends('message_ids.created_at')
    def _compute_latest_messages_count(self):
        """Compute count of messages from last 30 days"""
        from datetime import datetime, timedelta
        last_month = datetime.now() - timedelta(days=30)
        
        for group in self:
            try:
                # Filter messages created in the last 30 days
                recent_messages = group.message_ids.filtered(
                    lambda m: m.created_at and m.created_at >= last_month
                )
                group.latest_messages_count = len(recent_messages)
            except Exception as e:
                # Log the error and set to 0 to avoid breaking the UI
                _logger.warning(f"Error computing latest messages count for group {group.name}: {e}")
                group.latest_messages_count = 0
    
    @api.depends('message_ids.created_at')
    def _compute_last_message_date(self):
        """Compute the date of the last message"""
        for group in self:
            if group.message_ids:
                try:
                    # Use created_at for last message date
                    latest_message = group.message_ids.sorted('created_at', reverse=True)[:1]
                    if latest_message and latest_message.created_at:
                        group.last_message_date = latest_message.created_at
                    else:
                        group.last_message_date = False
                except Exception as e:
                    # Log the error and set to False to avoid breaking the UI
                    _logger.warning(f"Error computing last message date for group {group.name}: {e}")
                    group.last_message_date = False
            else:
                group.last_message_date = False
    
    def send_message_to_group(self):
        """Open wizard to send message to this group"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Send Message to Group',
            'res_model': 'whatsapp.send.message.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_group_id': self.id,
                'default_phone': self.group_id,
            }
        }
    
    def generate_invite_code(self):
        """Generate invite code for WHAPI groups"""
        if self.provider != 'whapi':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Not Supported',
                    'message': 'Invite code generation is only supported for WHAPI provider',
                    'type': 'warning',
                }
            }
        
        if not self.group_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Group ID',
                    'message': 'Please sync the group first',
                    'type': 'warning',
                }
            }
        
        try:
            api_service = self.env['whapi.service']
            invite_code = api_service.get_group_invite_code(self.group_id)
            
            if invite_code:
                self.write({
                    'invite_code': invite_code,
                    'invite_fetched_at': fields.Datetime.now(),
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Invite Code Generated',
                        'message': f'Invite code: {invite_code}',
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Generation Failed',
                        'message': 'Could not generate invite code',
                        'type': 'danger',
                    }
                }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': str(e),
                    'type': 'danger',
                }
            }

    def copy_invite_code(self):
        """Open the WhatsApp invite link in a new browser tab"""
        if not self.invite_code:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Invite Code',
                    'message': 'This group does not have an invite code yet. Generate one first.',
                    'type': 'warning',
                }
            }
        
        invite_link = f"https://chat.whatsapp.com/{self.invite_code}"
        
        return {
            'type': 'ir.actions.act_url',
            'url': invite_link,
            'target': 'new',
        }

    def action_view_latest_messages(self):
        """Action to view latest month messages for this group"""
        # Get last 30 days
        from datetime import datetime, timedelta
        last_month = datetime.now() - timedelta(days=30)
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Latest Messages - {self.name}',
            'res_model': 'whatsapp.message',
            'view_mode': 'tree,form',
            'domain': [
                ('group_id', '=', self.id),
                ('created_at', '>=', last_month)
            ],
            'context': {
                'default_group_id': self.id,
                'search_default_latest_first': 1
            }
        }
    
    @api.model
    def create(self, vals):
        """Override create to handle real WhatsApp group creation via API"""
        _logger.info(f"Creating WhatsApp group with vals: {vals}")
        
        # Get configuration for the current user if not specified
        if 'configuration_id' not in vals:
            config = self.env['whatsapp.configuration'].get_user_configuration()
            if config:
                vals['configuration_id'] = config.id
            else:
                raise ValidationError("No accessible WhatsApp configuration found for current user")
        
        # Check if this is a direct create attempt (not from API sync)
        if not self.env.context.get('from_api_sync') and not vals.get('group_id'):
            _logger.info("Direct group creation detected - will create via API")
            
            # This is a manual create attempt - redirect to wizard or create via API
            group_name = vals.get('name', '')
            description = vals.get('description', '')
            
            if not group_name:
                raise ValidationError("Group name is required to create a WhatsApp group.")
            
            # Get participants if provided
            participant_ids = vals.get('participant_ids', [])
            participants = []
            
            _logger.info(f"Raw participant_ids: {participant_ids}")
            
            # Handle many2many field format - multiple possible formats
            if participant_ids:
                contact_ids = []
                
                if isinstance(participant_ids, list) and len(participant_ids) > 0:
                    for item in participant_ids:
                        if isinstance(item, tuple) or isinstance(item, list):
                            if item[0] == 6 and len(item) >= 3:
                                # Format: [(6, 0, [id1, id2, ...])] or [[6, False, [id1, id2, ...]]]
                                # The second element can be 0, False, or other values - we just need the third element
                                contact_ids.extend(item[2])
                            elif item[0] == 4:
                                # Format: [(4, id)] - link existing record
                                contact_ids.append(item[1])
                        elif isinstance(item, int):
                            # Format: [id1, id2, ...]
                            contact_ids.append(item)
                
                _logger.info(f"Extracted contact_ids: {contact_ids}")
                
                if contact_ids:
                    contacts = self.env['whatsapp.contact'].browse(contact_ids)
                    _logger.info(f"Found {len(contacts)} contacts")
                    
                    # Extract phone numbers from contacts
                    for contact in contacts:
                        _logger.info(f"Processing contact: {contact.display_name}, contact_id: '{contact.contact_id}', phone: '{contact.phone}', isWAContact: {contact.isWAContact}")
                        
                        phone_number = None
                        
                        # Try to extract from contact_id first
                        if contact.contact_id:
                            cleaned_contact_id = contact.contact_id.replace('@s.whatsapp.net', '').replace('@c.us', '').strip()
                            if cleaned_contact_id and cleaned_contact_id.isdigit():
                                phone_number = cleaned_contact_id
                                _logger.info(f"✓ Added participant from contact_id: {phone_number}")
                        
                        # If no valid contact_id, try phone field
                        if not phone_number and contact.phone:
                            cleaned_phone = contact.phone.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '').strip()
                            if cleaned_phone and cleaned_phone.isdigit():
                                phone_number = cleaned_phone
                                _logger.info(f"✓ Added participant from phone: {phone_number}")
                        
                        # Add to participants if we found a valid number
                        if phone_number:
                            participants.append(phone_number)
                        else:
                            _logger.warning(f"✗ Contact {contact.display_name} has no valid phone number. contact_id='{contact.contact_id}', phone='{contact.phone}'")
            
            _logger.info(f"Final participants list: {participants}")
            
            # If no participants found, provide detailed error information
            if not participants:
                # Check if we have participant_ids but failed to extract phone numbers
                if participant_ids and contact_ids:
                    # We found contacts but couldn't extract valid phone numbers
                    contacts = self.env['whatsapp.contact'].browse(contact_ids)
                    contact_details = []
                    for contact in contacts:
                        contact_details.append(f"• {contact.display_name}: phone='{contact.phone}', contact_id='{contact.contact_id}'")
                    
                    error_msg = (
                        f"Selected {len(contacts)} participants but none have valid phone numbers.\n\n"
                        f"Contact details:\n" + "\n".join(contact_details) + "\n\n"
                        "Please ensure contacts have either:\n"
                        "• A 'phone' field with digits only (e.g., '201234567890')\n"
                        "• A 'contact_id' field with WhatsApp format (e.g., '201234567890@s.whatsapp.net')\n\n"
                        "Phone numbers should contain only digits after cleaning."
                    )
                else:
                    error_msg = (
                        "At least one participant is required to create a WhatsApp group.\n\n"
                        "To add participants:\n"
                        "1. Go to the 'Participants' tab\n"
                        "2. Select contacts from the list\n"
                        "3. If no contacts appear, sync your WhatsApp contacts first\n\n"
                        "Alternatively, use the 'Create Group' wizard from the menu which allows manual phone number entry."
                    )
                raise ValidationError(error_msg)
            
            try:
                # Get API service
                config = self.env['whatsapp.configuration'].get_user_configuration()
                if not config or config.provider != 'whapi':
                    raise ValidationError(
                        "Group creation is only supported with WHAPI provider. "
                        "Please configure WHAPI in WhatsApp Configuration."
                    )
                
                api_service = self.env['whapi.service']
                
                # Create group via API (without automatic invite link fetching)
                _logger.info(f"Creating WhatsApp group '{group_name}' with participants: {participants}")
                result = api_service.create_group(group_name, participants)
                
                if not result.get('group_id') and not result.get('id'):
                    error_msg = result.get('message', 'Unknown error occurred while creating group')
                    raise ValidationError(f"Failed to create group: {error_msg}")
                
                # Extract group information from API response
                group_id = result.get('group_id') or result.get('id')
                created_at_timestamp = result.get('created_at')
                participants_data = result.get('participants', [])
                
                _logger.info(f"Group created successfully via API: {group_id}")
                
                # Update vals with API response data
                vals.update({
                    'group_id': group_id,
                    'name': result.get('name', group_name),
                    'description': description,
                    'provider': 'whapi',
                    'is_active': True,
                    'synced_at': fields.Datetime.now(),
                    'metadata': str(result),
                    'configuration_id': config.id,  # Link to configuration
                })
                
                if created_at_timestamp:
                    try:
                        from datetime import datetime
                        vals['created_at'] = datetime.fromtimestamp(created_at_timestamp)
                    except:
                        pass
                
                # Set context to avoid recursion
                group = super(WhatsAppGroup, self.with_context(from_api_sync=True)).create(vals)
                
                # Process participants and create/link contacts
                if participants_data:
                    participant_contact_ids = []
                    
                    for participant in participants_data:
                        participant_id = participant.get('id', '')
                        participant_rank = participant.get('rank', 'member')
                        
                        if participant_id:
                            # Find or create contact
                            contact = self.env['whatsapp.contact'].search([
                                ('contact_id', '=', participant_id)
                            ], limit=1)
                            
                            if not contact:
                                # Create new contact
                                contact_vals = {
                                    'contact_id': participant_id,
                                    'name': participant.get('name', ''),
                                    'phone': participant_id.replace('@s.whatsapp.net', '').replace('@c.us', ''),
                                    'provider': 'whapi',
                                    'is_chat_contact': True,
                                    'isWAContact': True,
                                    'synced_at': fields.Datetime.now(),
                                }
                                contact = self.env['whatsapp.contact'].create(contact_vals)
                            
                            if contact:
                                participant_contact_ids.append(contact.id)
                    
                    # Link participants to group
                    if participant_contact_ids:
                        group.write({'participant_ids': [(6, 0, participant_contact_ids)]})
                
                return group
                
            except Exception as e:
                _logger.error(f"Error creating WhatsApp group via API: {e}")
                raise ValidationError(f"Failed to create WhatsApp group: {str(e)}")
        
        # Normal create (from API sync or with group_id already set)
        _logger.info("Normal group creation (from API sync or with group_id)")
        vals['updated_at'] = fields.Datetime.now()
        return super().create(vals)

    def write(self, vals):
        """Override write to update timestamp"""
        vals['updated_at'] = fields.Datetime.now()
        return super().write(vals)
    
    @api.model
    def create_from_api_response(self, api_response, provider='whapi'):
        """Create group from API response data (for new groups created via API)"""
        try:
            group_id = api_response.get('group_id') or api_response.get('id')
            name = api_response.get('name', '')
            
            if not group_id or not name:
                _logger.warning(f"Skipping group creation due to missing group_id or name: {api_response}")
                return False

            # Check for existing group
            existing = self.search([('group_id', '=', group_id)], limit=1)
            if existing:
                _logger.info(f"Group {group_id} already exists, returning existing record")
                return existing

            # Create new group
            vals = {
                'group_id': group_id,
                'name': name,
                'description': '',  # Will be set separately if needed
                'synced_at': fields.Datetime.now(),
                'provider': provider,
                'metadata': str(api_response),
                'is_active': True,
            }
            
            # Handle timestamp conversion
            created_at_timestamp = api_response.get('created_at')
            if created_at_timestamp:
                try:
                    from datetime import datetime
                    vals['created_at'] = datetime.fromtimestamp(created_at_timestamp)
                except Exception as e:
                    _logger.warning(f"Could not parse timestamp {created_at_timestamp}: {e}")
            
            group = self.create(vals)
            _logger.info(f"Created new group: {group.name} ({group.group_id})")
            return group
            
        except Exception as e:
            _logger.error(f"Failed to create group from API response: {e}")
            return False

    @api.model
    def create_from_api_data(self, api_data, provider='whapi'):
        """Create group from API data with clean field mapping"""
        # Get configuration for the current user
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if not config:
            _logger.warning("No accessible WhatsApp configuration found for current user")
            return False
            
        if provider == 'whapi':
            # WHAPI format - clean mapping
            group_id = api_data.get('id', '')
            name = api_data.get('name', '')
            description = api_data.get('description', '')
            metadata = str(api_data) if api_data else ''
        else:
            # Wassenger format - for backward compatibility
            group_id = api_data.get('id', '')
            name = api_data.get('name', '')
            description = api_data.get('description', '')
            metadata = str(api_data) if api_data else ''
        
        if not group_id or not name:
            _logger.warning(f"Skipping group creation due to missing group_id or name: {api_data}")
            return False

        # Check for existing group
        existing = self.search([('group_id', '=', group_id)], limit=1)
        if existing:
            # Update existing group
            update_vals = {
                'name': name,
                'description': description,
                'synced_at': fields.Datetime.now(),
                'provider': provider,
                'metadata': metadata,
            }
            
            if provider == 'wassenger':
                update_vals.update({
                    'wid': api_data.get('wid', existing.wid),
                })
            
            existing.write(update_vals)
            return existing

        # Create new group
        vals = {
            'group_id': group_id,
            'name': name,
            'description': description,
            'synced_at': fields.Datetime.now(),
            'provider': provider,
            'metadata': metadata,
            'configuration_id': config.id,  # Link to configuration
        }
        
        if provider == 'wassenger':
            vals.update({
                'wid': api_data.get('wid', group_id),
            })
        
        try:
            return self.create(vals)
        except Exception as e:
            _logger.error(f"Failed to create group {group_id}: {e}")
            return False
    
    def sync_group_info(self):
        """Sync group info from API and fetch invite link if using WHAPI"""
        # Determine which service to use based on configuration
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if config and config.provider == 'whapi':
            api_service = self.env['whapi.service']
        else:
            api_service = self.env['wassenger.api']
        
        try:
            # Use appropriate ID based on provider
            group_identifier = self.group_id if config and config.provider == 'whapi' else self.wid
            group_info = api_service.get_group_info(group_identifier)
            
            if group_info:
                update_vals = {
                    'synced_at': fields.Datetime.now(),
                }
                
                # Handle different response formats
                if config and config.provider == 'whapi':
                    # WHAPI format
                    update_vals.update({
                        'name': group_info.get('name', self.name),
                        'description': group_info.get('description', self.description),
                        'metadata': str(group_info),
                    })
                        
                else:
                    # Wassenger format
                    update_vals.update({
                        'name': group_info.get('name', self.name),
                        'description': group_info.get('description', self.description),
                    })
                
                self.write(update_vals)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync Complete',
                    'message': 'Group information synced successfully',
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
    
    def action_view_participants(self):
        """Action to view group participants"""
        return {
            'type': 'ir.actions.act_window',
            'name': f'Participants - {self.name}',
            'res_model': 'whatsapp.contact',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.participant_ids.ids)],
        }
    
    @api.model
    def sync_all_groups_from_api(self, provider=None):
        """Sync all groups from API with provider detection"""
        # Get configuration for the current user
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if not config:
            _logger.warning("No accessible WhatsApp configuration found for current user")
            return 0
            
        # Determine which service to use based on configuration or parameter
        if not provider:
            provider = config.provider if config else 'whapi'
        
        if provider == 'whapi':
            api_service = self.env['whapi.service']
        else:
            api_service = self.env['wassenger.api']
        
        try:
            if provider == 'whapi':
                # WHAPI pagination
                all_groups = []
                offset = 0
                count = 100
                
                while True:
                    result = api_service.get_groups(count=count, offset=offset)
                    api_groups = result.get('groups', [])
                    
                    if not api_groups:
                        break
                    
                    all_groups.extend(api_groups)
                    
                    if len(api_groups) < count:
                        break
                    
                    offset += count
            else:
                # Wassenger method
                all_groups = api_service.get_groups()
            
            synced_count = 0
            
            for api_group in all_groups:
                group_id = api_group.get('id', '')
                if not group_id:
                    continue
                
                existing = self.search([('group_id', '=', group_id)], limit=1)
                
                if not existing:
                    group = self.create_from_api_data(api_group, provider=provider)
                    if group:
                        synced_count += 1
                else:
                    # Update existing group
                    update_vals = {
                        'name': api_group.get('name', existing.name),
                        'description': api_group.get('description', existing.description),
                        'synced_at': fields.Datetime.now(),
                        'provider': provider,
                        'metadata': str(api_group),
                    }
                    
                    if provider == 'wassenger':
                        update_vals.update({
                            'wid': api_group.get('wid', existing.wid),
                        })
                    
                    existing.write(update_vals)
            
            return synced_count
        except Exception as e:
            _logger.error(f"Error syncing groups: {e}")
            return 0

    @api.model
    def sync_all_group_members_from_api(self):
        """Sync all group members from WHAPI API"""
        try:
            # Determine which service to use based on configuration
            config = self.env['whatsapp.configuration'].get_user_configuration()
            provider = 'whapi'
            if config and config.provider == 'whapi':
                api_service = self.env['whapi.service']
            else:
                api_service = self.env['wassenger.api']
                provider = 'wassenger'
            
            # Get all groups that need member sync
            groups = self.search([('is_active', '=', True)])
            
            synced_count = 0
            error_count = 0
            
            for group in groups:
                try:
                    if not group.group_id:
                        continue
                        
                    # Get group info including participants
                    group_info = api_service.get_group_info(group.group_id)
                    
                    if group_info and 'participants' in group_info:
                        participants = group_info.get('participants', [])
                        
                        # Create or update participant contacts
                        participant_contacts = []
                        for participant in participants:
                            contact_id = participant.get('id', '')
                            if not contact_id:
                                continue
                                
                            # Find or create contact
                            contact = self.env['whatsapp.contact'].search([
                                ('contact_id', '=', contact_id)
                            ], limit=1)
                            
                            if not contact:
                                # Create new contact - group participants are chat contacts
                                contact_data = {
                                    'contact_id': contact_id,
                                    'name': participant.get('name', ''),
                                    'pushname': participant.get('pushname', ''),
                                    'phone': participant.get('phone', ''),
                                    'provider': provider,
                                    'synced_at': fields.Datetime.now(),
                                    'is_chat_contact': True,  # Group participants are chat contacts
                                    'is_phone_contact': False,  # Unless we sync from phone contacts
                                }
                                contact = self.env['whatsapp.contact'].create(contact_data)
                            
                            if contact:
                                participant_contacts.append(contact.id)
                        
                        # Update group participants
                        if participant_contacts:
                            group.write({
                                'participant_ids': [(6, 0, participant_contacts)],
                                'synced_at': fields.Datetime.now(),
                            })
                            synced_count += 1
                            
                except Exception as e:
                    _logger.error(f"Failed to sync members for group {group.name}: {e}")
                    error_count += 1
            
            return {
                'synced_count': synced_count,
                'error_count': error_count,
                'message': f'Synced {synced_count} groups with {error_count} errors'
            }
            
        except Exception as e:
            _logger.error(f"Group members sync failed: {e}")
            return {
                'synced_count': 0,
                'error_count': 1,
                'message': f'Sync failed: {str(e)}'
            }
