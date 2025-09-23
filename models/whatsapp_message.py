from odoo import models, fields, api, SUPERUSER_ID
import logging
import json
from ..constants import MESSAGE_TYPES, MESSAGE_STATUS, PROVIDERS, WHATSAPP_GROUP_SUFFIX
from ..services.transformers.message_transformer import MessageTransformer

_logger = logging.getLogger(__name__)

class WhatsAppMessage(models.Model):
    _name = 'whatsapp.message'
    _description = 'WhatsApp Message'
    _order = 'created_at desc'
    _rec_name = 'body'

    # Core message fields available in WHAPI
    message_id = fields.Char('Message ID', index=True, help='WHAPI Message ID')
    body = fields.Text('Body', help='Message text content')
    message_type = fields.Selection(
        MESSAGE_TYPES, 
        string='Message Type', 
        default='text'
    )
    
    # WHAPI specific fields
    chat_id = fields.Char('Chat ID', required=True, index=True, help='WHAPI Chat ID')
    from_me = fields.Boolean('From Me', help='True if message was sent by us')
    timestamp = fields.Integer('Timestamp', default=0, help='Unix timestamp from WHAPI')
    
    # Status and timing
    status = fields.Selection(
        MESSAGE_STATUS,
        string='Status', 
        default='pending'
    )
    
    # Error handling  
    error_message = fields.Text('Error Message', help='Error message if delivery failed')
    
    # Timestamps
    created_at = fields.Datetime('Created At', default=fields.Datetime.now)
    updated_at = fields.Datetime('Updated At')
    synced_at = fields.Datetime('Synced At')
    
    # Media fields (simplified)
    media_url = fields.Char('Media URL')
    media_type = fields.Char('Media Type')
    caption = fields.Text('Caption')
    
    # WHAPI metadata stored as JSON
    metadata = fields.Text('Metadata', help='Additional WHAPI message metadata as JSON')
    
    # Relationships - simplified for WHAPI
    contact_id = fields.Many2one('whatsapp.contact', string='Contact')
    group_id = fields.Many2one('whatsapp.group', string='Group')
    
    # Configuration tracking for permission control
    configuration_id = fields.Many2one('whatsapp.configuration', string='Configuration', 
                                      help='WhatsApp configuration this message belongs to')
    
    # Provider tracking
    provider = fields.Selection(
        PROVIDERS,
        string='Provider', 
        default='whapi'
    )
    
    # Legacy fields for backward compatibility
    wid = fields.Char('Legacy WID', help='Legacy Wassenger WID')
    
    # Computed fields for embedded links
    sender_link = fields.Html('Sender Link', compute='_compute_sender_link', store=False,
                             help='Embedded link to sender contact or WhatsApp web link')
    
    _sql_constraints = [
        ('message_id_unique', 'unique(message_id)', 'Message ID must be unique!'),
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
    
    @api.depends('chat_id', 'from_me', 'contact_id', 'metadata')
    def _compute_sender_link(self):
        """Compute embedded link for message sender"""
        for record in self:
            if record.from_me:
                record.sender_link = '<span class="text-success">Me</span>'
                continue
                
            # Extract sender phone from metadata or chat_id
            sender_phone = None
            if record.metadata:
                try:
                    meta = json.loads(record.metadata) if isinstance(record.metadata, str) else record.metadata
                    if isinstance(meta, dict):
                        sender_phone = meta.get('from', '')
                except Exception:
                    pass
            
            # Fallback to chat_id if it's individual chat
            if not sender_phone and not record.chat_id.endswith(WHATSAPP_GROUP_SUFFIX):
                sender_phone = record.chat_id.replace('@s.whatsapp.net', '')
            
            if not sender_phone:
                record.sender_link = '<span class="text-muted">Unknown</span>'
                continue
                
            # Try to find contact by phone
            contact = self.env['whatsapp.contact'].search([
                '|', ('phone', '=', sender_phone), ('contact_id', '=', sender_phone)
            ], limit=1)
            
            if contact:
                # Link to existing contact
                record.sender_link = f'<a href="#" data-oe-model="whatsapp.contact" data-oe-id="{contact.id}" class="o_form_uri">{contact.name or contact.phone}</a>'
            else:
                # Create WhatsApp web link for unknown contact
                clean_phone = sender_phone.replace('@s.whatsapp.net', '')
                if clean_phone.isdigit():
                    record.sender_link = f'<a href="https://wa.me/{clean_phone}" target="_blank" title="Open in WhatsApp Web">{clean_phone}</a>'
                else:
                    record.sender_link = f'<span title="Sender: {sender_phone}">{sender_phone}</span>'
    
    def write(self, vals):
        """Override write to update timestamp"""
        vals['updated_at'] = fields.Datetime.now()
        return super().write(vals)
    
    @api.model
    def create_from_api_data(self, api_data, provider='whapi'):
        """Create or update a message from provider API data (supports WHAPI list endpoint)."""
        # Get configuration for the current user with error handling
        try:
            config = self.env['whatsapp.configuration'].get_user_configuration()
        except Exception as config_error:
            _logger.error(f"Failed to get user configuration: {config_error}")
            # Try to rollback and continue
            try:
                self.env.cr.rollback()
            except:
                pass
            return False
            
        if not config:
            _logger.warning("No accessible WhatsApp configuration found for current user")
            return False
            
        if provider == 'whapi':
            # WHAPI list format
            message_id = api_data.get('id', '')
            chat_id = api_data.get('chat_id', '')
            from_me = api_data.get('from_me', False)
            timestamp = api_data.get('timestamp', 0)
            message_type = api_data.get('type', 'text')
            # Extract a meaningful body using transformer
            try:
                body = MessageTransformer._extract_content_from_whapi(api_data, message_type)
            except Exception:
                body = ''
            metadata = str(api_data) if api_data else ''
        else:
            # Wassenger format - for backward compatibility
            message_id = api_data.get('id', '')
            body = api_data.get('content', '')
            chat_id = api_data.get('chat_id', '')
            from_me = api_data.get('direction', 'outbound') == 'outbound'
            timestamp = 0
            message_type = api_data.get('type', 'text')
            metadata = str(api_data) if api_data else ''
        
        if not message_id or not chat_id:
            _logger.warning(f"Skipping message creation due to missing message_id or chat_id: {api_data}")
            return False

        # Check for existing message
        existing = self.search([('message_id', '=', message_id)], limit=1)
        if existing:
            # Update existing message
            update_vals = {
                'body': body,
                'synced_at': fields.Datetime.now(),
                'provider': provider,
                'metadata': metadata,
            }
            try:
                existing.write(update_vals)
                return existing
            except Exception as update_error:
                _logger.error(f"Failed to update existing message {message_id}: {update_error}")
                try:
                    self.env.cr.rollback()
                except:
                    pass
                return False

        # Create new message
        vals = {
            'message_id': message_id,
            'body': body,
            'chat_id': chat_id,
            'from_me': from_me,
            'timestamp': timestamp,
            'message_type': message_type,
            'synced_at': fields.Datetime.now(),
            'provider': provider,
            'metadata': metadata,
            'status': 'sent',
            'configuration_id': config.id,  # Link to configuration
        }
        
        # Link to contact/group based on chat_id
        if chat_id.endswith(WHATSAPP_GROUP_SUFFIX):
            # Group message - find or create group
            group = self.env['whatsapp.group'].search([('group_id', '=', chat_id)], limit=1)
            if group:
                vals['group_id'] = group.id
        else:
            # Individual message - find or create contact
            phone = chat_id.replace('@s.whatsapp.net', '')
            contact = self.env['whatsapp.contact'].search([
                '|', ('contact_id', '=', chat_id), ('phone', '=', phone)
            ], limit=1)
            if contact:
                vals['contact_id'] = contact.id
        
        # For incoming messages, also try to link sender contact
        if not from_me and provider == 'whapi':
            sender_phone = api_data.get('from', '')
            if sender_phone and sender_phone != chat_id:  # Avoid duplicate linking for individual chats
                sender_contact = self.env['whatsapp.contact'].search([
                    '|', ('contact_id', '=', sender_phone), ('phone', '=', sender_phone)
                ], limit=1)
                if not sender_contact and sender_phone.replace('@s.whatsapp.net', '').isdigit():
                    # Create new contact for unknown sender
                    try:
                        clean_phone = sender_phone.replace('@s.whatsapp.net', '')
                        sender_contact = self.env['whatsapp.contact'].create({
                            'contact_id': sender_phone,
                            'phone': clean_phone,
                            'name': clean_phone,  # Will be updated when contact sync runs
                            'provider': provider,
                            'isWAContact': True,
                        })
                    except Exception as e:
                        _logger.warning(f"Failed to create contact for sender {sender_phone}: {e}")
                
                # Link sender contact if we have it and it's different from chat contact
                if sender_contact and not vals.get('contact_id'):
                    vals['contact_id'] = sender_contact.id
        
        # Handle media-like types from WHAPI response structures
        if provider == 'whapi':
            # Known media containers: text, image, video, document, audio, voice, gif
            media_container = None
            if message_type in ['image', 'video', 'document', 'audio', 'voice', 'gif']:
                media_container = api_data.get(message_type, {})
            if isinstance(media_container, dict) and media_container:
                vals.update({
                    'media_type': media_container.get('mime_type') or message_type,
                    'caption': media_container.get('caption', '')
                })
        else:
            # Legacy
            if api_data.get('media_url'):
                vals.update({
                    'media_url': api_data.get('media_url'),
                    'media_type': api_data.get('media_type'),
                    'caption': api_data.get('caption', ''),
                })
        
        try:
            return self.create(vals)
        except Exception as e:
            _logger.error(f"Failed to create message {message_id}: {e}")
            # If transaction is aborted, try to rollback and continue
            try:
                self.env.cr.rollback()
                _logger.warning(f"Rolled back transaction for message {message_id}")
            except:
                pass
            return False
    
    def sync_message_status(self):
        """Sync message status from API"""
        # Determine which service to use based on configuration
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if config and config.provider == 'whapi':
            api_service = self.env['whapi.service']
        else:
            api_service = self.env['wassenger.api']
        
        if not self.message_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync Failed',
                    'message': 'Message ID is missing',
                    'type': 'warning',
                }
            }
            
        try:
            status_info = api_service.get_message_status(self.message_id)
            
            if status_info:
                update_vals = {
                    'synced_at': fields.Datetime.now(),
                    'status': status_info.get('status', self.status),
                }
                
                self.write(update_vals)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync Complete',
                    'message': 'Message status synced successfully',
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

    @api.model
    def sync_all_messages_from_api(self, count=100, time_from=None, time_to=None, from_me=None, normal_types=False, sort='desc'):
        """Sync messages directly from WHAPI /messages/list with pagination.
        
        Fetches both incoming (from_me=false) and outgoing (from_me=true) messages
        to get complete conversation history.

        Returns a dict: { success, synced_count, error_count, total }
        """
        try:
            api_service = self.env['whapi.service']

            total_synced = 0
            total_errors = 0
            total_messages = 0

            # Sync both incoming and outgoing messages
            for from_me_value in [False, True]:  # Get messages from others, then my messages
                _logger.info(f"Syncing messages with from_me={from_me_value}")
                
                offset = 0
                synced_count = 0
                error_count = 0

                while True:
                    page = api_service.get_messages(
                        count=count,
                        offset=offset,
                        time_from=time_from,
                        time_to=time_to,
                        from_me=from_me_value,
                        normal_types=normal_types,
                        sort=sort,
                    )
                    messages = page.get('messages', [])
                    page_count = page.get('count', len(messages))
                    page_total = page.get('total', 0)
                    
                    if from_me_value == False:  # Only count total once
                        total_messages += page_total

                    allowed_types = {'text', 'image', 'video', 'gif', 'audio', 'voice', 'document'}
                    batch_messages = []
                    
                    # Collect messages in batch
                    for msg in messages:
                        try:
                            if msg.get('type') not in allowed_types:
                                continue
                            batch_messages.append(msg)
                        except Exception as e:
                            _logger.error(f"Error filtering message {msg.get('id')}: {e}")
                            error_count += 1
                    
                    # Process messages in smaller batches to avoid transaction issues
                    batch_size = 50  # Process 50 messages at a time
                    for i in range(0, len(batch_messages), batch_size):
                        batch = batch_messages[i:i + batch_size]
                        _logger.info(f"Processing message batch {i//batch_size + 1}: {i+1}-{min(i+batch_size, len(batch_messages))} of {len(batch_messages)}")
                        
                        batch_success = 0
                        batch_errors = 0
                        
                        for msg in batch:
                            try:
                                created = self.create_from_api_data(msg, 'whapi')
                                if created:
                                    batch_success += 1
                            except Exception as e:
                                _logger.error(f"Failed to create message {msg.get('id')}: {e}")
                                batch_errors += 1
                                # Try to continue with next message
                                try:
                                    self.env.cr.rollback()
                                except:
                                    pass
                        
                        # Commit this batch
                        try:
                            if batch_success > 0:
                                self.env.cr.commit()
                                _logger.info(f"✅ Committed batch: {batch_success} messages created")
                        except Exception as commit_error:
                            _logger.error(f"Failed to commit batch: {commit_error}")
                            batch_errors += len(batch)
                            try:
                                self.env.cr.rollback()
                            except:
                                pass
                        
                        synced_count += batch_success
                        error_count += batch_errors

                    # Advance pagination
                    if not messages:
                        break
                    offset += page_count or len(messages)
                    if page_total is not None and offset >= page_total:
                        break

                total_synced += synced_count
                total_errors += error_count
                _logger.info(f"Synced {synced_count} messages with from_me={from_me_value}")

            # Final commit to ensure all data is saved
            try:
                self.env.cr.commit()
                _logger.info(f"✅ Final commit: Total {total_synced} messages synced")
            except Exception as final_commit_error:
                _logger.error(f"Failed final commit: {final_commit_error}")

            return {
                'success': True,
                'synced_count': total_synced,
                'count': total_synced,
                'error_count': total_errors,
                'total': total_messages,
                'message': f'Synced {total_synced} messages (incoming + outgoing) with {total_errors} errors'
            }

        except Exception as e:
            _logger.error(f"Message sync failed: {e}")
            return {
                'success': False,
                'synced_count': 0,
                'error_count': 1,
                'message': f'Sync failed: {str(e)}'
            }
