from odoo import http
from odoo.http import request
import logging
import json
from datetime import datetime
from ..constants import PROVIDER_WHAPI, STATUS_DELIVERED, STATUS_READ, STATUS_SENT, STATUS_FAILED

_logger = logging.getLogger(__name__)

class WhatsappController(http.Controller):

    @http.route('/whatsapp/webhook/whapi/messages', type='json', auth='none', methods=['POST'], csrf=False)
    def whatsapp_messages_webhook(self):
        """Handle incoming WhatsApp messages from WHAPI webhook"""
        try:
            data = request.jsonrequest
            _logger.info(f"Received messages webhook: {data}")
            
            # Extract messages from webhook data
            messages = data.get('messages', [])
            channel_id = data.get('channel_id', '')

            # Resolve configuration by channel_id (if provided)
            config = None
            if channel_id:
                config = request.env['whatsapp.configuration'].sudo().get_by_channel_id(channel_id)
                if not config:
                    _logger.warning(f"No configuration found for channel_id={channel_id}; incoming data will be processed without configuration linkage")
            
            processed_count = 0
            error_count = 0

            # Handle updates/patches (message edits)
            for update in data.get('messages_updates', []) or []:
                try:
                    if self._process_message_update(update, config):
                        processed_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    _logger.error(f"Error processing message update {update.get('id','')}: {e}")
                    error_count += 1

            # Handle deletes list (silent event)
            for removed_id in data.get('messages_removed', []) or []:
                try:
                    if self._process_message_remove(removed_id):
                        processed_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    _logger.error(f"Error processing message removal {removed_id}: {e}")
                    error_count += 1
            
            for message_data in messages:
                try:
                    # Only process group messages (chat_id ends with @g.us)
                    chat_id = message_data.get('chat_id', '')
                    if not chat_id.endswith('@g.us'):
                        _logger.info(f"Skipping non-group message from chat: {chat_id}")
                        continue
                    
                    # Only process messages not from us (from_me = false)
                    from_me = message_data.get('from_me', False)
                    # if from_me:
                    #     _logger.info(f"Skipping outgoing message: {message_data.get('id', '')}")
                    #     continue
                    
                    # Process the message
                    success = self._process_group_message(message_data, channel_id, config)
                    if success:
                        processed_count += 1
                    else:
                        error_count += 1
                        
                except Exception as e:
                    _logger.error(f"Error processing message {message_data.get('id', 'unknown')}: {e}")
                    error_count += 1
            
            return {
                'status': 'success',
                'processed_count': processed_count,
                'error_count': error_count
            }
            
        except Exception as e:
            _logger.error(f"Webhook error: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _process_group_message(self, message_data, channel_id, config=None):
        """Process a single group message"""
        try:
            # Extract message information
            message_id = message_data.get('id', '')
            chat_id = message_data.get('chat_id', '')
            message_type = message_data.get('type', 'text')
            timestamp = message_data.get('timestamp', 0)
            source = message_data.get('source', 'mobile')
            chat_name = message_data.get('chat_name', '')
            from_name = message_data.get('from_name', '')
            
            # Handle different message types
            if message_type == 'action':
                return self._process_action_message(message_data, channel_id, config)
            
            # Regular message processing
            from_contact_id = message_data.get('from', '')
            
            # Extract message content based on type
            body = ''
            if message_type == 'text':
                text_data = message_data.get('text', {})
                body = text_data.get('body', '') if isinstance(text_data, dict) else str(text_data)
            elif message_type == 'image':
                image_data = message_data.get('image', {})
                body = image_data.get('caption', 'Image') if isinstance(image_data, dict) else 'Image'
            elif message_type == 'video':
                video_data = message_data.get('video', {})
                body = video_data.get('caption', 'Video') if isinstance(video_data, dict) else 'Video'
            elif message_type == 'audio':
                body = 'Audio message'
            elif message_type == 'document':
                document_data = message_data.get('document', {})
                filename = document_data.get('filename', 'Document') if isinstance(document_data, dict) else 'Document'
                body = f"Document: {filename}"
            else:
                body = f"{message_type.title()} message"
            
            if not message_id or not chat_id or not from_contact_id:
                _logger.warning(f"Missing required fields in message data: {message_data}")
                return False
            
            # Find or create the group
            group = self._find_or_create_group(chat_id, chat_name, config)
            if not group:
                _logger.error(f"Failed to find or create group for chat_id: {chat_id}")
                return False
            
            # Find or create the contact
            contact = self._find_or_create_contact(from_contact_id, from_name, config)
            if not contact:
                _logger.error(f"Failed to find or create contact for contact_id: {from_contact_id}")
                return False
            
            # Add contact to group participants if not already added
            if contact not in group.participant_ids:
                group.participant_ids = [(4, contact.id)]
                _logger.info(f"Added contact {contact.display_name} to group {group.name}")
            
            # Check if message already exists
            existing_message = request.env['whatsapp.message'].sudo().with_context(skip_config_filter=True).search([
                ('message_id', '=', message_id)
            ], limit=1)
            
            if existing_message:
                _logger.info(f"Message {message_id} already exists, updating...")
                existing_message.write({
                    'synced_at': datetime.now(),
                    'metadata': json.dumps(message_data),
                })
                return True
            
            # Create new message record
            message_vals = {
                'message_id': message_id,
                'body': body,
                'message_type': message_type,
                'chat_id': chat_id,
                'from_me': message_data.get('from_me', False),
                'timestamp': timestamp,
                'status': STATUS_DELIVERED,  # Incoming messages are delivered
                'contact_id': contact.id,
                'group_id': group.id,
                'provider': PROVIDER_WHAPI,
                'synced_at': datetime.now(),
                'metadata': json.dumps(message_data),
            }

            if config:
                message_vals['configuration_id'] = config.id
            
            # Handle media content
            if message_type in ['image', 'video', 'audio', 'document']:
                media_data = message_data.get(message_type, {})
                if isinstance(media_data, dict):
                    message_vals.update({
                        'media_url': media_data.get('link', ''),
                        'media_type': message_type,
                        'caption': media_data.get('caption', ''),
                    })
            
            message = request.env['whatsapp.message'].sudo().with_context(skip_config_filter=True).create(message_vals)
            _logger.info(f"Created message {message_id} from {contact.display_name} in group {group.name}")
            
            return True
            
        except Exception as e:
            _logger.error(f"Error processing group message: {e}")
            return False
    
    def _process_action_message(self, message_data, channel_id, config=None):
        """Process action messages (edit, delete, etc.)"""
        try:
            message_id = message_data.get('id', '')
            chat_id = message_data.get('chat_id', '')
            timestamp = message_data.get('timestamp', 0)
            chat_name = message_data.get('chat_name', '')
            from_name = message_data.get('from_name', '')
            action_data = message_data.get('action', {})
            
            if not message_id or not chat_id or not action_data:
                _logger.warning(f"Missing required fields in action message: {message_data}")
                return False
            
            action_type = action_data.get('type', '')
            target_message_id = action_data.get('target', '')
            
            if not action_type or not target_message_id:
                _logger.warning(f"Missing action type or target in action message: {message_data}")
                return False
            
            # Find or create the group (for logging purposes)
            group = self._find_or_create_group(chat_id, chat_name, config)
            
            if action_type == 'edit':
                return self._handle_message_edit(message_data, target_message_id, action_data)
            elif action_type == 'delete':
                return self._handle_message_delete(message_data, target_message_id, action_data)
            else:
                _logger.info(f"Unhandled action type: {action_type} for message {message_id}")
                return True  # Don't fail for unknown action types
            
        except Exception as e:
            _logger.error(f"Error processing action message: {e}")
            return False
    
    def _handle_message_edit(self, message_data, target_message_id, action_data):
        """Handle message edit action"""
        try:
            # Find the original message to edit
            target_message = request.env['whatsapp.message'].sudo().with_context(skip_config_filter=True).search([
                ('message_id', '=', target_message_id)
            ], limit=1)
            
            if not target_message:
                _logger.warning(f"Target message {target_message_id} not found for edit action")
                # Create a new message record for the edit action itself
                return self._create_action_message(message_data, 'Message Edit')
            
            # Get the new content
            edited_content = action_data.get('edited_content', {})
            new_body = edited_content.get('body', target_message.body)
            
            # Update the original message
            target_message.sudo().with_context(skip_config_filter=True).write({
                'body': new_body,
                'synced_at': datetime.now(),
                'metadata': json.dumps({
                    'original_metadata': target_message.metadata,
                    'edit_action': message_data
                }),
            })
            
            _logger.info(f"Updated message {target_message_id} with new content: {new_body}")
            
            # Also create a system message for the edit action
            self._create_action_message(message_data, f'Message edited: {new_body}')
            
            return True
            
        except Exception as e:
            _logger.error(f"Error handling message edit: {e}")
            return False
    
    def _handle_message_delete(self, message_data, target_message_id, action_data):
        """Handle message delete action"""
        try:
            # Find the original message to delete
            target_message = request.env['whatsapp.message'].sudo().with_context(skip_config_filter=True).search([
                ('message_id', '=', target_message_id)
            ], limit=1)
            
            if target_message:
                # Mark as deleted instead of actually deleting
                target_message.sudo().with_context(skip_config_filter=True).write({
                    'body': '[This message was deleted]',
                    'status': 'deleted',
                    'synced_at': datetime.now(),
                    'metadata': json.dumps({
                        'original_metadata': target_message.metadata,
                        'delete_action': message_data
                    }),
                })
                _logger.info(f"Marked message {target_message_id} as deleted")
            else:
                _logger.warning(f"Target message {target_message_id} not found for delete action")
            
            # Create a system message for the delete action
            self._create_action_message(message_data, 'Message deleted')
            
            return True
            
        except Exception as e:
            _logger.error(f"Error handling message delete: {e}")
            return False

    def _process_message_update(self, update_data, config=None):
        """Process WHAPI messages_updates (patch) event to edit a message in place."""
        try:
            msg_id = (update_data or {}).get('id')
            after = (update_data or {}).get('after_update', {})
            if not msg_id:
                return False

            # Try to find existing message
            target = request.env['whatsapp.message'].sudo().with_context(skip_config_filter=True).search([
                ('message_id', '=', msg_id)
            ], limit=1)

            # Derive new content
            new_type = after.get('type') or (update_data.get('trigger', {}).get('action', {}).get('edited_type'))
            new_body = ''
            if new_type == 'text':
                new_body = (after.get('text', {}) or {}).get('body', '')
            elif new_type in ('image', 'video', 'audio', 'document'):
                # Keep caption if provided
                new_body = (after.get(new_type, {}) or {}).get('caption', '') or f'{new_type.title()} message'
            else:
                new_body = (after.get('text', {}) or {}).get('body', '') or f'{(new_type or "text").title()} message'

            if target:
                vals = {
                    'body': new_body,
                    'message_type': new_type or target.message_type,
                    'synced_at': datetime.now(),
                    'metadata': json.dumps(update_data),
                }
                target.sudo().with_context(skip_config_filter=True).write(vals)
                return True

            # If not found, create it from after_update
            if after:
                # Reuse the normal message path to ensure relations are created
                after_copy = dict(after)
                after_copy['id'] = msg_id
                # Ensure text body for text type
                if new_type == 'text' and 'text' not in after_copy:
                    after_copy['text'] = {'body': new_body}
                return self._process_group_message(after_copy, update_data.get('channel_id', ''), config)

            return False
        except Exception as e:
            _logger.error(f"Error processing message update (patch): {e}")
            return False

    def _process_message_remove(self, message_id: str) -> bool:
        """Process WHAPI messages_removed (delete list) to mark messages deleted."""
        try:
            if not message_id:
                return False
            target = request.env['whatsapp.message'].sudo().with_context(skip_config_filter=True).search([
                ('message_id', '=', message_id)
            ], limit=1)
            if not target:
                _logger.warning(f"Message {message_id} not found for removal event")
                return False
            target.sudo().with_context(skip_config_filter=True).write({
                'body': '[This message was deleted]',
                'status': 'deleted',
                'synced_at': datetime.now(),
            })
            return True
        except Exception as e:
            _logger.error(f"Error processing message removal: {e}")
            return False
    
    def _create_action_message(self, message_data, action_description):
        """Create a system message for actions"""
        try:
            message_id = message_data.get('id', '')
            chat_id = message_data.get('chat_id', '')
            timestamp = message_data.get('timestamp', 0)
            chat_name = message_data.get('chat_name', '')
            from_name = message_data.get('from_name', 'System')
            
            # Find or create the group
            group = self._find_or_create_group(chat_id, chat_name)
            if not group:
                return False
            
            # Check if action message already exists
            existing_message = request.env['whatsapp.message'].sudo().search([
                ('message_id', '=', message_id)
            ], limit=1)
            
            if existing_message:
                _logger.info(f"Action message {message_id} already exists")
                return True
            
            # Create system message for the action
            message_vals = {
                'message_id': message_id,
                'body': f"[System] {action_description} by {from_name}",
                'message_type': 'system',
                'chat_id': chat_id,
                'from_me': False,
                'timestamp': timestamp,
                'status': STATUS_DELIVERED,
                'group_id': group.id,
                'provider': 'whapi',
                'synced_at': datetime.now(),
                'metadata': json.dumps(message_data),
            }

            if getattr(group, 'configuration_id', False):
                message_vals['configuration_id'] = group.configuration_id.id
            
            message = request.env['whatsapp.message'].sudo().create(message_vals)
            _logger.info(f"Created action message: {action_description}")
            
            return True
            
        except Exception as e:
            _logger.error(f"Error creating action message: {e}")
            return False
    
    def _find_or_create_group(self, group_id, group_name, config=None):
        """Find or create a WhatsApp group"""
        try:
            # Search for existing group
            group = request.env['whatsapp.group'].sudo().with_context(skip_config_filter=True).search([
                ('group_id', '=', group_id)
            ], limit=1)
            
            if group:
                # Update group name if it has changed
                if group_name and group.name != group_name:
                    update_vals = {
                        'name': group_name,
                        'synced_at': datetime.now(),
                    }
                    # backfill configuration if missing and we know it from webhook
                    if config and not group.configuration_id:
                        update_vals['configuration_id'] = config.id
                    group.sudo().with_context(skip_config_filter=True).write(update_vals)
                return group
            
            # Create new group
            group_vals = {
                'group_id': group_id,
                'name': group_name or f"Group {group_id}",
                'provider': 'whapi',
                'synced_at': datetime.now(),
                'is_active': True,
            }

            if config:
                group_vals['configuration_id'] = config.id
            
            group = request.env['whatsapp.group'].sudo().with_context(skip_config_filter=True).create(group_vals)
            _logger.info(f"Created new group: {group.name} ({group_id})")
            
            return group
            
        except Exception as e:
            _logger.error(f"Error finding/creating group {group_id}: {e}")
            return None
    
    def _find_or_create_contact(self, contact_id, contact_name, config=None):
        """Find or create a WhatsApp contact"""
        try:
            # Search for existing contact
            contact = request.env['whatsapp.contact'].sudo().with_context(skip_config_filter=True).search([
                ('contact_id', '=', contact_id)
            ], limit=1)
            
            if contact:
                # Update contact name if it has changed and we have a name
                if contact_name and contact_name != contact.pushname:
                    update_vals = {
                        'pushname': contact_name,
                        'synced_at': datetime.now(),
                        'is_chat_contact': True,  # Mark as chat contact since they messaged
                    }
                    if config and not contact.configuration_id:
                        update_vals['configuration_id'] = config.id
                    contact.sudo().with_context(skip_config_filter=True).write(update_vals)
                return contact
            
            # Create new contact
            contact_vals = {
                'contact_id': contact_id,
                'pushname': contact_name or '',
                'name': contact_name or '',
                'phone': contact_id if contact_id.isdigit() else '',
                'provider': 'whapi',
                'synced_at': datetime.now(),
                'isWAContact': True,
                'is_chat_contact': True,  # This is a chat contact since they sent a message
                'is_phone_contact': False,
            }

            if config:
                contact_vals['configuration_id'] = config.id
            
            contact = request.env['whatsapp.contact'].sudo().with_context(skip_config_filter=True).create(contact_vals)
            _logger.info(f"Created new contact: {contact.display_name} ({contact_id})")
            
            return contact
            
        except Exception as e:
            _logger.error(f"Error finding/creating contact {contact_id}: {e}")
            return None

    @http.route('/whatsapp/webhook/whapi/statuses', type='json', auth='none', methods=['POST', 'PUT'], csrf=False)
    def whatsapp_status_webhook(self):
        """Handle WhatsApp delivery status updates"""
        try:
            data = request.jsonrequest
            _logger.info(f"Received status webhook: {data}")
            
            # Extract status information
            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    
                    # Handle message status updates
                    for status in value.get('statuses', []):
                        message_id = status.get('id')
                        status_type = status.get('status')  # sent, delivered, read, failed
                        
                        if message_id:
                            # Find and update message record
                            message = request.env['whatsapp.message'].sudo().search([
                                ('message_id', '=', message_id)
                            ], limit=1)
                            
                            if message:
                                if status_type == 'delivered':
                                    message.status = STATUS_DELIVERED
                                elif status_type == 'read':
                                    message.status = STATUS_READ
                                elif status_type == 'failed':
                                    message.status = STATUS_FAILED
                                    error_info = status.get('errors', [])
                                    if error_info:
                                        # TODO: Uncomment after adding error_message field via module upgrade
                                        # message.error_message = error_info[0].get('title', 'Delivery failed')
                                        pass
            
            return {'status': 'success'}
            
        except Exception as e:
            _logger.error(f"Webhook error: {e}")
            return {'status': 'error', 'message': str(e)}