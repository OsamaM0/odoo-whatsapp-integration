from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class WhatsAppSyncWizard(models.TransientModel):
    _name = 'whatsapp.sync.wizard'
    _description = 'WhatsApp Sync Wizard'
    
    sync_type = fields.Selection([
        ('contacts', 'Sync Contacts'),
        ('groups', 'Sync Groups'),
        ('messages', 'Sync Messages'),
        ('group_members', 'Sync Group Members'),
        ('all', 'Sync All'),
        ('custom', 'Custom Sync'),
    ], string='Sync Type', default='all', required=True)
    
    # Custom sync options
    sync_contacts = fields.Boolean('Sync Contacts', default=True)
    sync_groups = fields.Boolean('Sync Groups', default=True)
    sync_messages = fields.Boolean('Sync Messages', default=True)
    sync_group_members = fields.Boolean('Sync Group Members', default=True)
    auto_fetch_invite_links = fields.Boolean('Auto-fetch Group Invite Links', default=True,
                                            help='Automatically fetch invite links for WHAPI groups during sync')
    
    # Progress tracking fields
    is_syncing = fields.Boolean('Is Syncing', default=False)
    progress = fields.Float('Progress', default=0.0)
    current_operation = fields.Char('Current Operation')
    
    # Batch processing configuration
    batch_size = fields.Integer('Batch Size', default=100, help='Number of records to process in each batch')
    enable_bulk_operations = fields.Boolean('Enable Bulk Operations', default=True, 
                                           help='Use optimized bulk operations for better performance')
    
    # Async processing configuration
    enable_async_processing = fields.Boolean('Enable Async Processing', default=False,
                                            help='Process large datasets asynchronously to prevent timeouts')
    max_memory_usage = fields.Integer('Max Memory Usage (MB)', default=500, 
                                     help='Maximum memory usage before forcing garbage collection')
    
    # Additional settings
    skip_existing_check = fields.Boolean('Skip Existing Check', default=False,
                                        help='Skip checking for existing records (faster but may create duplicates)')
    timeout_per_group = fields.Integer('Timeout Per Group (seconds)', default=30,
                                      help='Maximum time to spend syncing each group members')
    
    # Results
    contacts_synced = fields.Integer('Contacts Synced', default=0)
    groups_synced = fields.Integer('Groups Synced', default=0)
    messages_synced = fields.Integer('Messages Synced', default=0)
    group_members_synced = fields.Integer('Group Members Synced', default=0)
    errors_count = fields.Integer('Errors Count', default=0)
    error_messages = fields.Text('Error Messages')
    
    def action_start_sync(self):
        """Start the sync process"""
        self.write({
            'is_syncing': True,
            'progress': 0.0,
            'current_operation': 'Starting sync...',
            'contacts_synced': 0,
            'groups_synced': 0,
            'messages_synced': 0,
            'group_members_synced': 0,
            'errors_count': 0,
            'error_messages': '',
        })
        
        # Call the actual sync method
        return self.sync_data()
    
    def sync_data(self):
        """Perform sync based on selected type with optimized bulk operations"""
        # Check if user has access to any configuration
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if not config:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Access Denied',
                    'message': 'You do not have access to any WhatsApp configuration. Please contact your administrator.',
                    'type': 'danger',
                }
            }
        
        errors = []
        
        # Track results locally to avoid frequent database writes
        contacts_synced = 0
        groups_synced = 0
        messages_synced = 0
        group_members_synced = 0
        errors_count = 0
        
        try:
            total_steps = 0
            current_step = 0
            
            # Calculate total steps
            if self.sync_type in ['contacts', 'all'] or (self.sync_type == 'custom' and self.sync_contacts):
                total_steps += 1
            if self.sync_type in ['groups', 'all'] or (self.sync_type == 'custom' and self.sync_groups):
                total_steps += 1
            if self.sync_type in ['messages', 'all'] or (self.sync_type == 'custom' and self.sync_messages):
                total_steps += 1
            if self.sync_type in ['group_members', 'all'] or (self.sync_type == 'custom' and self.sync_group_members):
                total_steps += 1
            
            # Sync contacts with bulk optimization
            if self.sync_type in ['contacts', 'all'] or (self.sync_type == 'custom' and self.sync_contacts):
                current_step += 1
                self._update_progress(current_step, total_steps, 'Syncing contacts...')
                _logger.info(f"Syncing contacts with bulk optimization... ({current_step}/{total_steps})")
                
                try:
                    # Use direct method call without savepoint for bulk operations
                    if self.enable_bulk_operations:
                        result = self._sync_contacts_bulk()
                    else:
                        # Use savepoint only for the original method
                        with self.env.cr.savepoint():
                            result = self.env['whatsapp.contact'].sync_all_contacts_from_api()
                    
                    if result.get('success'):
                        contacts_synced = result.get('count', 0)
                    else:
                        errors.append(f"Contacts sync: {result.get('message', 'Unknown error')}")
                        errors_count += 1
                except Exception as e:
                    # Log error and continue with next sync
                    _logger.error(f"Contacts sync error: {str(e)}")
                    errors.append(f"Contacts sync error: {str(e)}")
                    errors_count += 1
            
            # Sync groups with bulk optimization
            if self.sync_type in ['groups', 'all'] or (self.sync_type == 'custom' and self.sync_groups):
                current_step += 1
                self._update_progress(current_step, total_steps, 'Syncing groups...')
                _logger.info(f"Syncing groups with bulk optimization... ({current_step}/{total_steps})")
                
                try:
                    if self.enable_bulk_operations:
                        result = self._sync_groups_bulk()
                    else:
                        with self.env.cr.savepoint():
                            result = self.env['whatsapp.group'].sync_all_groups_from_api()
                    
                    if result.get('success'):
                        groups_synced = result.get('count', 0)
                        if result.get('error_count', 0) > 0:
                            errors.append(f"Groups sync completed with {result.get('error_count', 0)} errors")
                    else:
                        errors.append(f"Groups sync: {result.get('message', 'Unknown error')}")
                        errors_count += 1
                except Exception as e:
                    _logger.error(f"Groups sync error: {str(e)}")
                    errors.append(f"Groups sync error: {str(e)}")
                    errors_count += 1
            
            # Sync messages with bulk optimization
            if self.sync_type in ['messages', 'all'] or (self.sync_type == 'custom' and self.sync_messages):
                current_step += 1
                self._update_progress(current_step, total_steps, 'Syncing messages...')
                _logger.info(f"Syncing messages with bulk optimization... ({current_step}/{total_steps})")
                
                try:
                    if self.enable_bulk_operations:
                        result = self._sync_messages_bulk()
                    else:
                        with self.env.cr.savepoint():
                            result = self.env['whatsapp.message'].sync_all_messages_from_api(count=30)  # Reduced batch size
                    
                    if result.get('success'):
                        messages_synced = result.get('count', 0)
                        if result.get('error_count', 0) > 0:
                            errors.append(f"Messages sync completed with {result.get('error_count', 0)} errors")
                    else:
                        errors.append(f"Messages sync: {result.get('message', 'Unknown error')}")
                        errors_count += 1
                except Exception as e:
                    _logger.error(f"Messages sync error: {str(e)}")
                    errors.append(f"Messages sync error: {str(e)}")
                    errors_count += 1
            
            # Sync group members with bulk optimization
            if self.sync_type in ['group_members', 'all'] or (self.sync_type == 'custom' and self.sync_group_members):
                current_step += 1
                self._update_progress(current_step, total_steps, 'Syncing group members...')
                _logger.info(f"Syncing group members with bulk optimization... ({current_step}/{total_steps})")
                
                try:
                    if self.enable_bulk_operations:
                        result = self._sync_group_members_bulk()
                    else:
                        with self.env.cr.savepoint():
                            result = self.env['whatsapp.group'].sync_all_group_members_from_api()
                    
                    if result.get('success'):
                        group_members_synced = result.get('count', 0)
                        if result.get('error_count', 0) > 0:
                            errors.append(f"Group members sync completed with {result.get('error_count', 0)} errors")
                    else:
                        errors.append(f"Group members sync: {result.get('message', 'Unknown error')}")
                        errors_count += 1
                except Exception as e:
                    _logger.error(f"Group members sync error: {str(e)}")
                    errors.append(f"Group members sync error: {str(e)}")
                    errors_count += 1
            
            # Complete sync - update wizard record once at the end with transaction recovery
            def _update_final_state():
                self.write({
                    'is_syncing': False,
                    'progress': 100.0,
                    'current_operation': 'Sync completed',
                    'contacts_synced': contacts_synced,
                    'groups_synced': groups_synced,
                    'messages_synced': messages_synced,
                    'group_members_synced': group_members_synced,
                    'errors_count': errors_count,
                    'error_messages': '\n'.join(errors) if errors else False,
                })
                self._safe_commit()
                return True
            
            try:
                self._safe_execute(_update_final_state)
            except Exception as write_error:
                _logger.error(f"Failed to update final wizard state: {write_error}")
            
            if not errors:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Sync Complete',
                        'message': f'Synced {contacts_synced} contacts, {groups_synced} groups, {messages_synced} messages, {group_members_synced} group members',
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Sync Complete with Errors',
                        'message': f'Completed with {len(errors)} errors. Check the wizard for details.',
                        'type': 'warning',
                    }
                }
                
        except Exception as e:
            _logger.error(f"Sync wizard error: {str(e)}")
            try:
                self.write({
                    'is_syncing': False,
                    'error_messages': str(e),
                    'errors_count': 1,
                })
            except Exception as write_error:
                _logger.error(f"Failed to update wizard with error: {str(write_error)}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync Failed',
                    'message': str(e),
                    'type': 'danger',
                }
            }
    
    
    def _is_in_transaction(self):
        """Check if we're currently in a transaction or savepoint"""
        try:
            return hasattr(self.env.cr, '_savepoint_seq') and self.env.cr._savepoint_seq > 0
        except:
            return False
    
    def _safe_commit(self):
        """Safely commit only if not in a savepoint with transaction recovery"""
        try:
            # First recover transaction if needed
            if not self._recover_transaction():
                _logger.warning("Could not recover transaction for commit")
                return False
            
            if not self._is_in_transaction():
                self.env.cr.commit()
                return True
            else:
                _logger.debug("Skipping commit - currently in savepoint")
                return True
        except Exception as e:
            _logger.warning(f"Safe commit failed: {e}")
            # Try to recover from aborted transaction
            if "current transaction is aborted" in str(e):
                try:
                    self.env.cr.rollback()
                    _logger.info("Rolled back aborted transaction during commit")
                    return True
                except Exception as rollback_error:
                    _logger.error(f"Failed to rollback during commit: {rollback_error}")
            return False
    
    def _recover_transaction(self):
        """Recover from an aborted transaction state"""
        try:
            # Check if transaction is in aborted state
            self.env.cr.execute("SELECT 1")
            return True  # Transaction is healthy
        except Exception as e:
            if "current transaction is aborted" in str(e):
                _logger.warning("Transaction is aborted, attempting recovery...")
                try:
                    # Rollback the entire transaction
                    self.env.cr.rollback()
                    _logger.info("Transaction successfully rolled back")
                    return True
                except Exception as rollback_error:
                    _logger.error(f"Failed to rollback transaction: {rollback_error}")
                    # Last resort: close and reopen the cursor
                    try:
                        old_cr = self.env.cr
                        # Create a new cursor from the database
                        new_cr = self.env.registry.cursor()
                        # Replace the cursor in environment
                        self.env = self.env(cr=new_cr)
                        # Close the old cursor
                        old_cr.close()
                        _logger.info("Transaction recovered with new cursor")
                        return True
                    except Exception as cursor_error:
                        _logger.error(f"Failed to create new cursor: {cursor_error}")
                        return False
            else:
                _logger.error(f"Transaction check failed with non-abort error: {e}")
                return False
    
    def _safe_execute(self, operation_func, *args, **kwargs):
        """Safely execute an operation with transaction recovery"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Check and recover transaction if needed
                if not self._recover_transaction():
                    raise Exception("Failed to recover transaction state")
                
                # Execute the operation
                return operation_func(*args, **kwargs)
                
            except Exception as e:
                retry_count += 1
                _logger.warning(f"Operation failed (attempt {retry_count}/{max_retries}): {e}")
                
                if retry_count >= max_retries:
                    _logger.error(f"Operation failed after {max_retries} attempts")
                    raise e
                
                # Wait before retry
                import time
                time.sleep(1)
        
        return None
    
    def _check_timeout(self, start_time, timeout_seconds):
        """Check if operation has exceeded timeout"""
        import time
        return (time.time() - start_time) > timeout_seconds
    
    def _check_memory_usage(self):
        """Check memory usage and force garbage collection if needed"""
        import gc
        
        try:
            # Try to use psutil if available
            try:
                import psutil
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
            except ImportError:
                # Fallback to basic memory tracking
                import sys
                memory_mb = sys.getsizeof(self) / 1024 / 1024
                _logger.info("psutil not available, using basic memory tracking")
            
            if memory_mb > self.max_memory_usage:
                _logger.info(f"Memory usage ({memory_mb:.1f}MB) exceeds limit ({self.max_memory_usage}MB), forcing garbage collection")
                gc.collect()
                return True
            return False
        except Exception as e:
            _logger.warning(f"Could not check memory usage: {e}")
            return False
    
    def _update_progress(self, step, total_steps, operation):
        """Update progress tracking with transaction recovery"""
        progress = (step / total_steps) * 100 if total_steps > 0 else 0
        
        def _do_update():
            self.write({
                'progress': progress,
                'current_operation': operation,
            })
            self._safe_commit()
            return True
        
        try:
            self._safe_execute(_do_update)
        except Exception as e:
            _logger.warning(f"Failed to update progress: {e}")
            # Continue without failing the sync
    
    def _sync_contacts_bulk(self):
        """Bulk sync contacts with set operations for efficiency"""
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if not config:
            return {'success': False, 'message': 'No accessible WhatsApp configuration found', 'count': 0}
        
        try:
            # Get API service
            if config.provider == 'whapi':
                api_service = self.env['whapi.service']
            else:
                api_service = self.env['wassenger.api']
            
            # Get all contacts from API with memory-efficient batching
            all_api_contacts = []
            
            if config.provider == 'whapi':
                # Get phone contacts
                offset = 0
                count = min(self.batch_size, 500)
                
                self._update_progress(0, 100, 'Fetching phone contacts from API...')
                while True:
                    result = api_service.get_contacts(count=count, offset=offset)
                    api_contacts = result.get('contacts', [])
                    if not api_contacts:
                        break
                    for contact in api_contacts:
                        contact['is_phone_contact'] = True
                        contact['is_chat_contact'] = False
                    all_api_contacts.extend(api_contacts)
                    
                    # Check memory usage
                    self._check_memory_usage()
                    
                    if len(api_contacts) < count:
                        break
                    offset += count
                    
                    # Update progress
                    self._update_progress(25, 100, f'Fetched {offset} phone contacts...')
                
                # Get chat contacts
                offset = 0
                self._update_progress(30, 100, 'Fetching chat contacts from API...')
                while True:
                    result = api_service.get_chats(count=count, offset=offset)
                    api_chats = result.get('chats', [])
                    if not api_chats:
                        break
                    for chat in api_chats:
                        if chat.get('type') == 'chat':
                            contact = {
                                'id': chat.get('id', ''),
                                'name': chat.get('name', ''),
                                'pushname': chat.get('pushname', ''),
                                'is_phone_contact': False,
                                'is_chat_contact': True
                            }
                            all_api_contacts.append(contact)
                    
                    # Check memory usage
                    self._check_memory_usage()
                    
                    if len(api_chats) < count:
                        break
                    offset += count
                    
                    # Update progress
                    self._update_progress(50, 100, f'Fetched {len(all_api_contacts)} total contacts...')
            else:
                # Wassenger
                all_api_contacts = api_service.get_contacts()
                for contact in all_api_contacts:
                    contact['is_phone_contact'] = True
                    contact['is_chat_contact'] = False
            
            # Extract unique contact IDs from API
            self._update_progress(60, 100, 'Processing contact data...')
            api_contact_ids = set()
            api_contacts_dict = {}
            for contact in all_api_contacts:
                contact_id = contact.get('id') if config.provider == 'whapi' else contact.get('phone')
                if contact_id:
                    api_contact_ids.add(contact_id)
                    api_contacts_dict[contact_id] = contact
            
            # Get existing contact IDs from database efficiently
            self._update_progress(70, 100, 'Checking existing contacts in database...')
            if self.skip_existing_check:
                # Skip check for maximum speed
                existing_contact_ids = set()
                contacts_to_create = api_contact_ids
                contacts_to_update = set()
            else:
                # Use direct SQL for better performance on large datasets
                try:
                    self.env.cr.execute("""
                        SELECT contact_id FROM whatsapp_contact 
                        WHERE configuration_id = %s AND contact_id = ANY(%s)
                    """, (config.id, list(api_contact_ids)))
                    existing_contact_ids = set(row[0] for row in self.env.cr.fetchall())
                except Exception as sql_error:
                    _logger.error(f"SQL query failed, falling back to ORM: {sql_error}")
                    # Fallback to ORM method
                    existing_contacts = self.env['whatsapp.contact'].search([
                        ('configuration_id', '=', config.id),
                        ('contact_id', 'in', list(api_contact_ids))
                    ])
                    existing_contact_ids = set(existing_contacts.mapped('contact_id'))
                
                # Find contacts to create (in API but not in DB)
                contacts_to_create = api_contact_ids - existing_contact_ids
                
                # Find contacts to update (in both API and DB)
                contacts_to_update = api_contact_ids & existing_contact_ids
            
            _logger.info(f"Contact sync analysis: API={len(api_contact_ids)}, DB={len(existing_contact_ids)}, "
                        f"Create={len(contacts_to_create)}, Update={len(contacts_to_update)}")
            
            synced_count = 0
            
            # Bulk create new contacts
            if contacts_to_create:
                self._update_progress(80, 100, f'Creating {len(contacts_to_create)} new contacts...')
                create_vals_list = []
                for contact_id in contacts_to_create:
                    api_data = api_contacts_dict[contact_id]
                    vals = self._prepare_contact_vals(api_data, config)
                    if vals:
                        create_vals_list.append(vals)
                
                if create_vals_list:
                    try:
                        # Use smaller batches for creation to avoid database timeouts
                        create_batch_size = min(self.batch_size, 50)
                        for i in range(0, len(create_vals_list), create_batch_size):
                            batch = create_vals_list[i:i + create_batch_size]
                            
                            # Use individual savepoint for each batch
                            try:
                                with self.env.cr.savepoint():
                                    created_contacts = self.env['whatsapp.contact'].create(batch)
                                    synced_count += len(created_contacts)
                            except Exception as batch_error:
                                _logger.error(f"Batch create failed, trying individual creates: {batch_error}")
                                # Fallback to individual creates for this batch
                                for vals in batch:
                                    try:
                                        with self.env.cr.savepoint():
                                            self.env['whatsapp.contact'].create(vals)
                                            synced_count += 1
                                    except Exception as create_error:
                                        _logger.error(f"Individual contact create failed: {create_error}")
                            
                            # Update progress
                            progress = 80 + (i / len(create_vals_list)) * 15
                            self._update_progress(progress, 100, f'Created {synced_count} contacts...')
                            
                            # Check memory periodically
                            if i % (create_batch_size * 5) == 0:
                                self._check_memory_usage()
                        
                        _logger.info(f"Bulk created {synced_count} contacts")
                    except Exception as e:
                        _logger.error(f"Bulk create contacts failed: {e}")
                        return {'success': False, 'count': 0, 'message': str(e)}
            
            # Bulk update existing contacts
            if contacts_to_update and not self.skip_existing_check:
                self._update_progress(95, 100, f'Updating {len(contacts_to_update)} existing contacts...')
                
                try:
                    # Use direct SQL for bulk update for better performance
                    contact_ids_list = list(contacts_to_update)
                    update_batch_size = min(self.batch_size, 100)
                    
                    for i in range(0, len(contact_ids_list), update_batch_size):
                        batch_ids = contact_ids_list[i:i + update_batch_size]
                        try:
                            self.env.cr.execute("""
                                UPDATE whatsapp_contact 
                                SET synced_at = %s, provider = %s, updated_at = %s
                                WHERE configuration_id = %s AND contact_id = ANY(%s)
                            """, (
                                fields.Datetime.now(),
                                config.provider, 
                                fields.Datetime.now(),
                                config.id,
                                batch_ids
                            ))
                        except Exception as update_error:
                            _logger.error(f"Batch update failed: {update_error}")
                            # Continue with next batch
                            continue
                    
                    _logger.info(f"Bulk updated {len(contacts_to_update)} contacts")
                except Exception as e:
                    _logger.error(f"Bulk update contacts failed: {e}")
                    # Don't fail the entire sync for update errors
            
            self._update_progress(100, 100, 'Contact sync completed')
            
            return {
                'success': True,
                'count': synced_count,
                'message': f'Bulk synced {synced_count} new contacts, updated {len(contacts_to_update)} existing'
            }
            
        except Exception as e:
            _logger.error(f"Bulk contact sync failed: {e}")
            return {'success': False, 'count': 0, 'message': str(e)}
    
    def _sync_groups_bulk(self):
        """Bulk sync groups with set operations for efficiency"""
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if not config:
            return {'success': False, 'message': 'No accessible WhatsApp configuration found', 'count': 0}
        
        try:
            # Get API service
            if config.provider == 'whapi':
                api_service = self.env['whapi.service']
            else:
                api_service = self.env['wassenger.api']
            
            # Get all groups from API
            all_api_groups = []
            
            if config.provider == 'whapi':
                offset = 0
                count = 100
                while True:
                    result = api_service.get_groups(count=count, offset=offset)
                    api_groups = result.get('groups', [])
                    if not api_groups:
                        break
                    all_api_groups.extend(api_groups)
                    if len(api_groups) < count:
                        break
                    offset += count
            else:
                all_api_groups = api_service.get_groups()
            
            # Extract unique group IDs from API
            api_group_ids = set()
            api_groups_dict = {}
            for group in all_api_groups:
                group_id = group.get('id', '')
                if group_id:
                    api_group_ids.add(group_id)
                    api_groups_dict[group_id] = group
            
            # Get existing group IDs from database
            existing_groups = self.env['whatsapp.group'].search([
                ('configuration_id', '=', config.id)
            ])
            existing_group_ids = set(existing_groups.mapped('group_id'))
            
            # Find groups to create (in API but not in DB)
            groups_to_create = api_group_ids - existing_group_ids
            
            # Find groups to update (in both API and DB)
            groups_to_update = api_group_ids & existing_group_ids
            
            _logger.info(f"Group sync analysis: API={len(api_group_ids)}, DB={len(existing_group_ids)}, "
                        f"Create={len(groups_to_create)}, Update={len(groups_to_update)}")
            
            synced_count = 0
            
            # Bulk create new groups
            if groups_to_create:
                create_vals_list = []
                for group_id in groups_to_create:
                    api_data = api_groups_dict[group_id]
                    vals = self._prepare_group_vals(api_data, config)
                    if vals:
                        create_vals_list.append(vals)
                
                if create_vals_list:
                    try:
                        created_groups = self.env['whatsapp.group'].create(create_vals_list)
                        synced_count += len(created_groups)
                        _logger.info(f"Bulk created {len(created_groups)} groups")
                    except Exception as e:
                        _logger.error(f"Bulk create groups failed: {e}")
                        # Fallback to individual creates
                        for vals in create_vals_list:
                            try:
                                self.env['whatsapp.group'].create(vals)
                                synced_count += 1
                            except Exception as create_error:
                                _logger.error(f"Individual group create failed: {create_error}")
            
            # Bulk update existing groups and fetch missing invite links
            if groups_to_update:
                groups_to_update_records = existing_groups.filtered(
                    lambda g: g.group_id in groups_to_update
                )
                
                # Prepare update values
                update_vals = {
                    'synced_at': fields.Datetime.now(),
                    'provider': config.provider,
                }
                
                try:
                    groups_to_update_records.write(update_vals)
                    _logger.info(f"Bulk updated {len(groups_to_update_records)} groups")
                    
                    # Auto-fetch missing invite links for WHAPI groups (if enabled)
                    if config.provider == 'whapi' and self.auto_fetch_invite_links:
                        groups_needing_invites = groups_to_update_records.filtered(
                            lambda g: not g.invite_code
                        )
                        
                        if groups_needing_invites:
                            _logger.info(f"Auto-fetching invite links for {len(groups_needing_invites)} groups without invite codes")
                            invite_fetched_count = 0
                            
                            for group in groups_needing_invites:
                                try:
                                    if group.fetch_invite_link():
                                        invite_fetched_count += 1
                                except Exception as e:
                                    _logger.warning(f"⚠️ Failed to auto-fetch invite for group {group.name}: {e}")
                                    # Continue with other groups
                            
                            _logger.info(f"✅ Auto-fetched invite links for {invite_fetched_count}/{len(groups_needing_invites)} groups")
                    
                except Exception as e:
                    _logger.error(f"Bulk update groups failed: {e}")
            
            return {
                'success': True,
                'count': synced_count,
                'message': f'Bulk synced {synced_count} new groups, updated {len(groups_to_update)} existing'
            }
            
        except Exception as e:
            _logger.error(f"Bulk group sync failed: {e}")
            return {'success': False, 'count': 0, 'message': str(e)}
    
    def _sync_messages_bulk(self):
        """Bulk sync messages with set operations for efficiency"""
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if not config:
            return {'success': False, 'message': 'No accessible WhatsApp configuration found', 'count': 0}
        
        try:
            api_service = self.env['whapi.service']
            total_synced = 0
            
            # Get messages from API (both incoming and outgoing)
            for from_me_value in [False, True]:
                _logger.info(f"Bulk syncing messages with from_me={from_me_value}")
                
                # Use smaller batches for memory efficiency
                batch_size = min(self.batch_size, 200)  # Limit message batch size
                offset = 0
                
                while True:
                    try:
                        page = api_service.get_messages(
                            count=batch_size,
                            offset=offset,
                            from_me=from_me_value,
                            normal_types=True,
                            sort='desc'
                        )
                    except Exception as api_error:
                        _logger.error(f"API error getting messages page: {api_error}")
                        break
                    
                    messages = page.get('messages', [])
                    if not messages:
                        break
                    
                    # Filter allowed message types
                    allowed_types = {'text', 'image', 'video', 'gif', 'audio', 'voice', 'document'}
                    filtered_messages = [msg for msg in messages if msg.get('type') in allowed_types]
                    
                    if not filtered_messages:
                        offset += len(messages)
                        continue
                    
                    # Extract unique message IDs from this batch
                    batch_message_ids = set()
                    batch_messages_dict = {}
                    for message in filtered_messages:
                        message_id = message.get('id', '')
                        if message_id:
                            batch_message_ids.add(message_id)
                            batch_messages_dict[message_id] = message
                    
                    # Check which messages already exist in database
                    existing_messages = self.env['whatsapp.message'].search([
                        ('message_id', 'in', list(batch_message_ids)),
                        ('configuration_id', '=', config.id)
                    ])
                    existing_message_ids = set(existing_messages.mapped('message_id'))
                    
                    # Find messages to create (in API but not in DB)
                    messages_to_create = batch_message_ids - existing_message_ids
                    
                    # Bulk create new messages from this batch
                    if messages_to_create:
                        create_vals_list = []
                        for message_id in messages_to_create:
                            api_data = batch_messages_dict[message_id]
                            vals = self._prepare_message_vals(api_data, config)
                            if vals:
                                create_vals_list.append(vals)
                        
                        if create_vals_list:
                            # Split into smaller sub-batches to avoid memory issues
                            sub_batch_size = 50
                            for i in range(0, len(create_vals_list), sub_batch_size):
                                sub_batch = create_vals_list[i:i + sub_batch_size]
                                try:
                                    created_messages = self.env['whatsapp.message'].create(sub_batch)
                                    total_synced += len(created_messages)
                                    _logger.info(f"Bulk created sub-batch of {len(created_messages)} messages")
                                except Exception as e:
                                    _logger.error(f"Bulk create messages sub-batch failed: {e}")
                                    # Fallback to individual creates for this sub-batch
                                    for vals in sub_batch:
                                        try:
                                            self.env['whatsapp.message'].create(vals)
                                            total_synced += 1
                                        except Exception as create_error:
                                            _logger.error(f"Individual message create failed: {create_error}")
                    
                    # Update progress
                    self._update_progress(
                        offset + len(messages), 
                        page.get('total', offset + len(messages)), 
                        f'Syncing messages (from_me={from_me_value}): {total_synced} synced'
                    )
                    
                    if len(messages) < batch_size:
                        break
                    offset += len(messages)
            
            return {
                'success': True,
                'count': total_synced,
                'message': f'Bulk synced {total_synced} new messages'
            }
            
        except Exception as e:
            _logger.error(f"Bulk message sync failed: {e}")
            return {'success': False, 'count': 0, 'message': str(e)}
    
    def _sync_group_members_bulk(self):
        """Bulk sync group members with set operations for efficiency"""
        config = self.env['whatsapp.configuration'].get_user_configuration()
        if not config:
            return {'success': False, 'message': 'No accessible WhatsApp configuration found', 'count': 0}
        
        try:
            api_service = self.env['whapi.service']
            
            # Get all active groups
            groups = self.env['whatsapp.group'].search([
                ('is_active', '=', True),
                ('configuration_id', '=', config.id)
            ])
            
            if not groups:
                return {'success': True, 'count': 0, 'message': 'No groups found to sync'}
            
            synced_count = 0
            total_groups = len(groups)
            processed_groups = 0
            
            _logger.info(f"Starting group member sync for {total_groups} groups")
            
            for group in groups:
                processed_groups += 1
                
                # Update progress
                self._update_progress(
                    processed_groups, 
                    total_groups, 
                    f'Syncing members for group {group.name} ({processed_groups}/{total_groups})'
                )
                
                if not group.group_id:
                    _logger.warning(f"Group {group.name} has no group_id, skipping")
                    continue
                
                try:
                    # Use safe execution with transaction recovery for each group
                    import time
                    group_start_time = time.time()
                    
                    def _sync_single_group():
                        # Get group participants from API
                        _logger.info(f"Fetching participants for group {group.name} ({group.group_id})")
                        
                        # Check timeout before API call
                        if self._check_timeout(group_start_time, self.timeout_per_group):
                            _logger.warning(f"Timeout exceeded for group {group.name}, skipping")
                            return False
                        
                        group_info = api_service.get_group_info(group.group_id)
                        
                        # Check timeout after API call
                        if self._check_timeout(group_start_time, self.timeout_per_group):
                            _logger.warning(f"Timeout exceeded after API call for group {group.name}, skipping")
                            return False
                        
                        if not group_info or 'participants' not in group_info:
                            _logger.warning(f"No participants data for group {group.name}")
                            return False
                        
                        participants = group_info.get('participants', [])
                        _logger.info(f"Found {len(participants)} participants for group {group.name}")
                        
                        if not participants:
                            # Clear participants if group has no members
                            group.write({
                                'participant_ids': [(6, 0, [])],
                                'synced_at': fields.Datetime.now(),
                            })
                            return True
                        
                        # Extract participant contact IDs
                        api_participant_ids = set()
                        api_participants_dict = {}
                        for participant in participants:
                            contact_id = participant.get('id', '')
                            if contact_id:
                                api_participant_ids.add(contact_id)
                                api_participants_dict[contact_id] = participant
                        
                        if not api_participant_ids:
                            _logger.warning(f"No valid participant IDs for group {group.name}")
                            return False
                        
                        # Get existing contacts for these participant IDs
                        existing_contacts = self.env['whatsapp.contact'].search([
                            ('contact_id', 'in', list(api_participant_ids)),
                            ('configuration_id', '=', config.id)
                        ])
                        existing_contact_ids = set(existing_contacts.mapped('contact_id'))
                        
                        # Find contacts to create
                        contacts_to_create = api_participant_ids - existing_contact_ids
                        
                        # Bulk create missing contacts
                        new_contacts_created = 0
                        if contacts_to_create:
                            _logger.info(f"Creating {len(contacts_to_create)} missing participant contacts for group {group.name}")
                            create_vals_list = []
                            for contact_id in contacts_to_create:
                                participant_data = api_participants_dict[contact_id]
                                vals = {
                                    'contact_id': contact_id,
                                    'name': participant_data.get('name', '') or contact_id,
                                    'pushname': participant_data.get('pushname', ''),
                                    'phone': participant_data.get('phone', ''),
                                    'provider': config.provider,
                                    'synced_at': fields.Datetime.now(),
                                    'is_chat_contact': True,
                                    'is_phone_contact': False,
                                    'configuration_id': config.id,
                                }
                                create_vals_list.append(vals)
                            
                            if create_vals_list:
                                # Create in smaller batches to avoid timeout
                                batch_size = 20
                                for i in range(0, len(create_vals_list), batch_size):
                                    batch = create_vals_list[i:i + batch_size]
                                    
                                    def _create_batch():
                                        created_contacts = self.env['whatsapp.contact'].create(batch)
                                        self._safe_commit()
                                        return len(created_contacts)
                                    
                                    try:
                                        batch_created = self._safe_execute(_create_batch)
                                        new_contacts_created += batch_created or 0
                                    except Exception as e:
                                        _logger.error(f"Batch create failed for group {group.name}: {e}")
                                        # Fallback to individual creates
                                        for vals in batch:
                                            def _create_individual():
                                                self.env['whatsapp.contact'].create(vals)
                                                self._safe_commit()
                                                return 1
                                            
                                            try:
                                                individual_created = self._safe_execute(_create_individual)
                                                new_contacts_created += individual_created or 0
                                            except Exception as create_error:
                                                _logger.error(f"Individual participant contact create failed: {create_error}")
                                
                                _logger.info(f"Successfully created {new_contacts_created} participant contacts for group {group.name}")
                        
                        # Get all relevant contact records (existing + newly created)
                        all_relevant_contacts = self.env['whatsapp.contact'].search([
                            ('contact_id', 'in', list(api_participant_ids)),
                            ('configuration_id', '=', config.id)
                        ])
                        
                        _logger.info(f"Found {len(all_relevant_contacts)} total participant contacts for group {group.name}")
                        
                        # Update group participants
                        if all_relevant_contacts:
                            def _link_participants():
                                group.write({
                                    'participant_ids': [(6, 0, all_relevant_contacts.ids)],
                                    'synced_at': fields.Datetime.now(),
                                })
                                self._safe_commit()
                                return True
                            
                            try:
                                result = self._safe_execute(_link_participants)
                                if result:
                                    _logger.info(f"Successfully linked {len(all_relevant_contacts)} participants to group {group.name}")
                                    return True
                                else:
                                    _logger.error(f"Failed to link participants to group {group.name}")
                                    return False
                            except Exception as link_error:
                                _logger.error(f"Failed to link participants to group {group.name}: {link_error}")
                                return False
                        else:
                            _logger.warning(f"No participant contacts found to link for group {group.name}")
                            return False
                    
                    # Execute the group sync with transaction recovery
                    result = self._safe_execute(_sync_single_group)
                    if result:
                        synced_count += 1
                    
                except Exception as e:
                    _logger.error(f"Failed to sync members for group {group.name}: {e}")
                    # Continue with next group instead of failing completely
                    continue
                
                # Check memory usage periodically
                if processed_groups % 5 == 0:
                    self._check_memory_usage()
            
            _logger.info(f"Group member sync completed: {synced_count}/{total_groups} groups synced successfully")
            
            return {
                'success': True,
                'count': synced_count,
                'message': f'Bulk synced members for {synced_count} out of {total_groups} groups'
            }
            
        except Exception as e:
            _logger.error(f"Bulk group members sync failed: {e}")
            return {'success': False, 'count': 0, 'message': str(e)}
    
    def _prepare_contact_vals(self, api_data, config):
        """Prepare contact values for bulk creation"""
        if config.provider == 'whapi':
            contact_id = api_data.get('id', '')
            pushname = api_data.get('pushname', '')
            name = api_data.get('name', '')
            phone = contact_id if contact_id.isdigit() else ''
            is_phone_contact = api_data.get('is_phone_contact', False)
            is_chat_contact = api_data.get('is_chat_contact', False)
        else:
            contact_id = api_data.get('phone', '')
            phone = api_data.get('phone', '')
            name = api_data.get('name', '')
            pushname = ''
            is_phone_contact = True
            is_chat_contact = False
        
        if not contact_id:
            return None
        
        return {
            'contact_id': contact_id,
            'name': name,
            'pushname': pushname,
            'phone': phone,
            'provider': config.provider,
            'synced_at': fields.Datetime.now(),
            'is_phone_contact': is_phone_contact,
            'is_chat_contact': is_chat_contact,
            'configuration_id': config.id,
        }
    
    def _prepare_group_vals(self, api_data, config):
        """Prepare group values for bulk creation"""
        group_id = api_data.get('id', '')
        name = api_data.get('name', '')
        
        if not group_id or not name:
            return None
        
        vals = {
            'group_id': group_id,
            'name': name,
            'description': api_data.get('description', ''),
            'provider': config.provider,
            'synced_at': fields.Datetime.now(),
            'metadata': str(api_data),
            'configuration_id': config.id,
        }
        
        # Auto-fetch invite link for WHAPI groups during sync (if enabled)
        if config.provider == 'whapi' and self.auto_fetch_invite_links:
            try:
                api_service = self.env['whapi.service']
                invite_code = api_service.get_group_invite_code(group_id)
                
                if invite_code:
                    vals.update({
                        'invite_code': invite_code,
                        'invite_fetched_at': fields.Datetime.now(),
                    })
                    _logger.info(f"✅ Auto-fetched invite code for new group {name}: {invite_code}")
                else:
                    _logger.info(f"ℹ️ No invite code available for group {name}")
            except Exception as e:
                _logger.warning(f"⚠️ Could not fetch invite code for group {name} during sync: {e}")
                # Don't fail group creation if invite fetch fails
        
        return vals
    
    def _prepare_message_vals(self, api_data, config):
        """Prepare message values for bulk creation"""
        from ..services.transformers.message_transformer import MessageTransformer
        from ..constants import WHATSAPP_GROUP_SUFFIX
        
        message_id = api_data.get('id', '')
        chat_id = api_data.get('chat_id', '')
        
        if not message_id or not chat_id:
            return None
        
        # Extract content
        message_type = api_data.get('type', 'text')
        try:
            body = MessageTransformer._extract_content_from_whapi(api_data, message_type)
        except Exception:
            body = ''
        
        vals = {
            'message_id': message_id,
            'body': body,
            'chat_id': chat_id,
            'from_me': api_data.get('from_me', False),
            'timestamp': api_data.get('timestamp', 0),
            'message_type': message_type,
            'synced_at': fields.Datetime.now(),
            'provider': config.provider,
            'metadata': str(api_data),
            'status': 'sent',
            'configuration_id': config.id,
        }
        
        # Quick contact/group linking (no creation during message sync)
        if chat_id.endswith(WHATSAPP_GROUP_SUFFIX):
            group = self.env['whatsapp.group'].search([
                ('group_id', '=', chat_id),
                ('configuration_id', '=', config.id)
            ], limit=1)
            if group:
                vals['group_id'] = group.id
        else:
            phone = chat_id.replace('@s.whatsapp.net', '')
            contact = self.env['whatsapp.contact'].search([
                '|', ('contact_id', '=', chat_id), ('phone', '=', phone),
                ('configuration_id', '=', config.id)
            ], limit=1)
            if contact:
                vals['contact_id'] = contact.id
        
        return vals

    def action_close(self):
        """Close the wizard"""
        return {'type': 'ir.actions.act_window_close'}
