"""
Integration tests for WhatsApp Core Service
"""
import unittest
from unittest.mock import Mock, patch
from odoo.tests.common import TransactionCase
from ..services.whatsapp_core_service import WhatsAppCoreService
from ..services.whatsapp_provider_factory import WhatsAppProviderFactory


class TestWhatsAppCoreService(TransactionCase):
    """Test core service integration"""
    
    def setUp(self):
        super().setUp()
        self.core_service = self.env['whatsapp.core.service']
        
        # Create test configuration
        self.test_config = self.env['whatsapp.configuration'].create({
            'name': 'Test Config',
            'token': 'test_token_123',
            'supervisor_phone': '+1234567890',
            'provider': 'whapi',
            'active': True,
            'user_ids': [(4, self.env.user.id)]
        })
    
    def test_send_text_message_integration(self):
        """Test end-to-end text message sending"""
        # Mock the provider
        mock_provider = Mock()
        mock_provider.provider_name = 'whapi'
        mock_provider.send_text_message.return_value = {
            'success': True,
            'message_id': 'test_msg_123'
        }
        
        with patch.object(self.core_service, '_get_provider_for_user', return_value=mock_provider):
            result = self.core_service.send_text_message(
                to='+1234567890',
                message='Test integration message'
            )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['message_id'], 'test_msg_123')
        
        # Verify provider was called correctly
        mock_provider.send_text_message.assert_called_once_with(
            '+1234567890', 'Test integration message'
        )
    
    def test_send_media_message_integration(self):
        """Test end-to-end media message sending"""
        mock_provider = Mock()
        mock_provider.provider_name = 'whapi'
        mock_provider.send_media_message.return_value = {
            'success': True,
            'message_id': 'test_media_123'
        }
        
        test_media = b'fake_image_data'
        
        with patch.object(self.core_service, '_get_provider_for_user', return_value=mock_provider):
            result = self.core_service.send_media_message(
                to='+1234567890',
                media_data=test_media,
                filename='test.jpg',
                media_type='image',
                caption='Test image'
            )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['message_id'], 'test_media_123')
        
        # Verify provider was called with MediaMessageDTO
        mock_provider.send_media_message.assert_called_once()
        call_args = mock_provider.send_media_message.call_args
        media_dto = call_args[0][1]  # Second argument should be MediaMessageDTO
        self.assertEqual(media_dto.filename, 'test.jpg')
        self.assertEqual(media_dto.media_type, 'image')
        self.assertEqual(media_dto.caption, 'Test image')
    
    def test_create_group_integration(self):
        """Test end-to-end group creation"""
        mock_provider = Mock()
        mock_provider.provider_name = 'whapi'
        mock_provider.create_group.return_value = {
            'success': True,
            'group_id': 'test_group_123',
            'invite_link': 'https://chat.whatsapp.com/invite123'
        }
        
        participants = ['+1234567890', '+0987654321']
        
        with patch.object(self.core_service, '_get_provider_for_user', return_value=mock_provider):
            result = self.core_service.create_group(
                name='Test Group',
                participants=participants,
                description='Test group description'
            )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['group_id'], 'test_group_123')
        
        # Verify provider was called correctly
        mock_provider.create_group.assert_called_once_with(
            'Test Group', participants, 'Test group description'
        )
    
    def test_webhook_processing_integration(self):
        """Test webhook processing integration"""
        # Mock provider
        mock_provider = Mock()
        mock_provider.provider_name = 'whapi'
        mock_provider.validate_webhook.return_value = True
        mock_provider.parse_webhook_message.return_value = [
            # Mock MessageDTO
            Mock(
                message_id='webhook_msg_123',
                content='Webhook test message',
                message_type='text',
                chat_id='+1234567890',
                from_me=False,
                timestamp=1234567890,
                sender_phone='+0987654321',
                sender_name='Test User',
                metadata={'test': 'data'}
            )
        ]
        mock_provider.parse_webhook_status.return_value = []
        
        webhook_data = {
            'messages': [{
                'id': 'webhook_msg_123',
                'body': 'Webhook test message',
                'from': '+0987654321'
            }]
        }
        
        with patch('odoo.addons.whatsapp_integration.services.whatsapp_provider_factory.WhatsAppProviderFactory.get_default_provider', return_value=mock_provider):
            with patch.object(self.core_service, '_save_incoming_message', return_value=True) as mock_save:
                result = self.core_service.process_webhook(
                    provider_name='whapi',
                    webhook_data=webhook_data
                )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['processed_messages'], 1)
        
        # Verify message was saved
        mock_save.assert_called_once()
    
    def test_sync_contacts_integration(self):
        """Test contact synchronization"""
        from ..services.dto import ContactDTO
        
        mock_provider = Mock()
        mock_provider.provider_name = 'whapi'
        mock_provider.get_contacts.return_value = {
            'contacts': [
                ContactDTO(
                    contact_id='+1234567890',
                    phone='+1234567890',
                    name='Test Contact',
                    is_whatsapp_user=True
                )
            ],
            'total': 1
        }
        
        with patch.object(self.core_service, '_get_provider_for_user', return_value=mock_provider):
            with patch.object(self.core_service, '_save_contact', return_value=True):
                result = self.core_service.sync_contacts()
        
        self.assertTrue(result['success'])
        self.assertEqual(result['synced_count'], 1)
        self.assertEqual(result['total_available'], 1)
    
    def test_error_handling_no_provider(self):
        """Test error handling when no provider is configured"""
        with patch.object(self.core_service, '_get_provider_for_user', return_value=None):
            result = self.core_service.send_text_message(
                to='+1234567890',
                message='Test message'
            )
        
        self.assertFalse(result['success'])
        self.assertIn('No WhatsApp provider configured', result['error'])
    
    def test_validation_errors(self):
        """Test input validation"""
        mock_provider = Mock()
        
        with patch.object(self.core_service, '_get_provider_for_user', return_value=mock_provider):
            # Test missing recipient
            result = self.core_service.send_text_message(to='', message='Test')
            self.assertFalse(result['success'])
            self.assertIn('required', result['error'])
            
            # Test missing message
            result = self.core_service.send_text_message(to='+1234567890', message='')
            self.assertFalse(result['success'])
            self.assertIn('required', result['error'])


class TestProviderFactory(TransactionCase):
    """Test provider factory functionality"""
    
    def setUp(self):
        super().setUp()
        self.factory = self.env['whatsapp.provider.factory']
        
        # Create test configurations
        self.whapi_config = self.env['whatsapp.configuration'].create({
            'name': 'WHAPI Config',
            'token': 'whapi_token_123',
            'supervisor_phone': '+1234567890',
            'provider': 'whapi',
            'active': True,
            'user_ids': [(4, self.env.user.id)]
        })
    
    def test_provider_registration(self):
        """Test provider registration"""
        from ..services.adapters.base_adapter import BaseWhatsAppAdapter
        
        class TestAdapter(BaseWhatsAppAdapter):
            pass
        
        # Register test provider
        WhatsAppProviderFactory.register_provider('test', TestAdapter)
        
        # Verify registration
        providers = WhatsAppProviderFactory.get_available_providers()
        self.assertIn('test', providers)
        self.assertEqual(providers['test'], TestAdapter)
    
    def test_create_provider_success(self):
        """Test successful provider creation"""
        config = {
            'token': 'test_token',
            'supervisor_phone': '+1234567890'
        }
        
        # Mock the adapter to avoid actual API calls
        with patch('odoo.addons.whatsapp_integration.services.adapters.whapi_adapter.WhapiAdapter') as MockAdapter:
            mock_instance = Mock()
            mock_instance.validate_config.return_value = {'valid': True}
            MockAdapter.return_value = mock_instance
            
            # Register mock adapter
            WhatsAppProviderFactory.register_provider('mock_whapi', MockAdapter)
            
            provider = self.factory.create_provider('mock_whapi', config)
            
            self.assertIsNotNone(provider)
            MockAdapter.assert_called_once_with(self.env, config)
    
    def test_create_provider_invalid_config(self):
        """Test provider creation with invalid config"""
        config = {'invalid': 'config'}
        
        with patch('odoo.addons.whatsapp_integration.services.adapters.whapi_adapter.WhapiAdapter') as MockAdapter:
            mock_instance = Mock()
            mock_instance.validate_config.return_value = {
                'valid': False, 
                'message': 'Invalid config'
            }
            MockAdapter.return_value = mock_instance
            
            WhatsAppProviderFactory.register_provider('mock_whapi', MockAdapter)
            
            provider = self.factory.create_provider('mock_whapi', config)
            
            self.assertIsNone(provider)
    
    def test_get_provider_for_user(self):
        """Test getting provider for specific user"""
        with patch.object(self.factory, 'create_provider') as mock_create:
            mock_provider = Mock()
            mock_create.return_value = mock_provider
            
            provider = self.factory.get_provider_for_user(self.env.user.id)
            
            self.assertIsNotNone(provider)
            mock_create.assert_called_once()
            
            # Verify correct config was passed
            call_args = mock_create.call_args
            self.assertEqual(call_args[0][0], 'whapi')  # Provider name
            self.assertIn('token', call_args[0][1])     # Config dict


if __name__ == '__main__':
    unittest.main()
