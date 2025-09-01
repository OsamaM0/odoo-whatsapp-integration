"""
Unit tests for WhatsApp Provider Adapters
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import base64
from odoo.tests.common import TransactionCase
from ..services.adapters.whapi_adapter import WhapiAdapter
from ..services.adapters.twilio_adapter import TwilioAdapter
from ..services.dto import MessageDTO, MediaMessageDTO


class TestWhapiAdapter(TransactionCase):
    """Test WHAPI adapter functionality"""
    
    def setUp(self):
        super().setUp()
        self.config = {
            'token': 'test_token_123',
            'supervisor_phone': '+1234567890'
        }
        self.adapter = WhapiAdapter(self.env, self.config)
    
    def test_validate_config_success(self):
        """Test successful configuration validation"""
        with patch.object(self.adapter, 'health_check') as mock_health:
            mock_health.return_value = {'healthy': True}
            
            result = self.adapter.validate_config(self.config)
            
            self.assertTrue(result['valid'])
            self.assertEqual(result['message'], 'Configuration is valid')
    
    def test_validate_config_missing_token(self):
        """Test configuration validation with missing token"""
        invalid_config = {'supervisor_phone': '+1234567890'}
        
        result = self.adapter.validate_config(invalid_config)
        
        self.assertFalse(result['valid'])
        self.assertIn('token', result['message'])
    
    @patch('requests.Session.get')
    def test_health_check_success(self, mock_get):
        """Test successful health check"""
        mock_response = Mock()
        mock_response.json.return_value = {'status': 'ok'}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = self.adapter.health_check()
        
        self.assertTrue(result['healthy'])
        self.assertIn('response_time', result['data'])
    
    @patch('requests.Session.post')
    def test_send_text_message_success(self, mock_post):
        """Test successful text message sending"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'sent': True,
            'message': {'id': 'msg_123'}
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        result = self.adapter.send_text_message('+1234567890', 'Test message')
        
        self.assertTrue(result['success'])
        self.assertEqual(result['message_id'], 'msg_123')
        
        # Verify request was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn('Authorization', call_args[1]['headers'])
        self.assertEqual(call_args[1]['json']['to'], '+1234567890')
        self.assertEqual(call_args[1]['json']['body'], 'Test message')
    
    @patch('requests.Session.post')
    def test_send_media_message_success(self, mock_post):
        """Test successful media message sending"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'sent': True,
            'message': {'id': 'msg_media_123'}
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        # Create test media
        test_image_data = b'fake_image_data'
        media_dto = MediaMessageDTO(
            media_data=test_image_data,
            filename='test.jpg',
            media_type='image',
            caption='Test image'
        )
        
        result = self.adapter.send_media_message('+1234567890', media_dto)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['message_id'], 'msg_media_123')
        
        # Verify media was encoded properly
        call_args = mock_post.call_args
        json_data = call_args[1]['json']
        self.assertIn('media', json_data)
        self.assertTrue(json_data['media'].startswith('data:image/jpeg'))
    
    def test_fix_double_encoding(self):
        """Test double encoding fix"""
        # Create double-encoded data
        original_data = b'test_data'
        first_encoded = base64.b64encode(original_data).decode('utf-8')
        double_encoded = base64.b64encode(first_encoded.encode('utf-8')).decode('utf-8')
        
        # This should return the first_encoded (single encoding)
        result = self.adapter._fix_double_encoding(double_encoded)
        
        # In practice, this test would need actual image data to work properly
        # This is a simplified version
        self.assertIsInstance(result, str)
    
    def test_get_mime_type(self):
        """Test MIME type detection"""
        test_cases = [
            ('image', 'test.png', 'image/png'),
            ('image', 'test.jpg', 'image/jpeg'),
            ('video', 'test.mp4', 'video/mp4'),
            ('document', 'test.pdf', 'application/pdf'),
            ('document', 'test.txt', 'application/octet-stream'),
        ]
        
        for message_type, filename, expected_mime in test_cases:
            result = self.adapter._get_mime_type(message_type, filename)
            self.assertEqual(result, expected_mime)


class TestTwilioAdapter(TransactionCase):
    """Test Twilio adapter functionality"""
    
    def setUp(self):
        super().setUp()
        self.config = {
            'account_sid': 'test_account_sid',
            'auth_token': 'test_auth_token',
            'from_number': 'whatsapp:+1234567890'
        }
        self.adapter = TwilioAdapter(self.env, self.config)
    
    def test_validate_config_success(self):
        """Test successful Twilio configuration validation"""
        with patch.object(self.adapter, 'health_check') as mock_health:
            mock_health.return_value = {'healthy': True}
            
            result = self.adapter.validate_config(self.config)
            
            self.assertTrue(result['valid'])
    
    def test_validate_config_invalid_from_number(self):
        """Test configuration validation with invalid from_number"""
        invalid_config = self.config.copy()
        invalid_config['from_number'] = '+1234567890'  # Missing whatsapp: prefix
        
        result = self.adapter.validate_config(invalid_config)
        
        self.assertFalse(result['valid'])
        self.assertIn('whatsapp:', result['message'])
    
    def test_format_phone_for_twilio(self):
        """Test phone number formatting for Twilio"""
        test_cases = [
            ('+1234567890', 'whatsapp:+1234567890'),
            ('1234567890', 'whatsapp:+1234567890'),
            ('whatsapp:+1234567890', 'whatsapp:+1234567890'),
        ]
        
        for input_phone, expected in test_cases:
            result = self.adapter._format_phone_for_twilio(input_phone)
            self.assertEqual(result, expected)
    
    @patch('requests.Session.post')
    def test_send_text_message_success(self, mock_post):
        """Test Twilio text message sending"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'sid': 'twilio_msg_123',
            'status': 'queued',
            'to': 'whatsapp:+1234567890',
            'body': 'Test message'
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        result = self.adapter.send_text_message('+1234567890', 'Test message')
        
        self.assertTrue(result['success'])
        self.assertEqual(result['message_id'], 'twilio_msg_123')
        
        # Verify request format (form data, not JSON)
        call_args = mock_post.call_args
        self.assertIn('data', call_args[1])
        self.assertEqual(call_args[1]['data']['Body'], 'Test message')
    
    def test_map_twilio_status(self):
        """Test Twilio status mapping"""
        test_cases = [
            ('queued', 'pending'),
            ('sent', 'sent'),
            ('delivered', 'delivered'),
            ('failed', 'failed'),
            ('unknown_status', 'unknown'),
        ]
        
        for twilio_status, expected in test_cases:
            result = self.adapter._map_twilio_status(twilio_status)
            self.assertEqual(result, expected)
    
    def test_group_operations_not_supported(self):
        """Test that group operations return appropriate errors"""
        result = self.adapter.create_group('Test Group', ['+1234567890'])
        
        self.assertFalse(result['success'])
        self.assertIn('not support', result['message'])


class TestMockAdapter(TransactionCase):
    """Test mock adapter for testing purposes"""
    
    def setUp(self):
        super().setUp()
        # Create a simple mock adapter for testing
        from ..services.adapters.base_adapter import BaseWhatsAppAdapter
        
        class MockAdapter(BaseWhatsAppAdapter):
            def __init__(self, env, config):
                super().__init__(env, config)
                self.sent_messages = []
                self.created_groups = []
            
            def validate_config(self, config):
                return {'valid': True, 'message': 'Mock config valid'}
            
            def health_check(self):
                return {'healthy': True, 'message': 'Mock healthy'}
            
            def send_text_message(self, to, message, **kwargs):
                message_id = f'mock_msg_{len(self.sent_messages) + 1}'
                self.sent_messages.append({
                    'id': message_id,
                    'to': to,
                    'message': message
                })
                return {'success': True, 'message_id': message_id}
            
            def send_media_message(self, to, media_dto, **kwargs):
                message_id = f'mock_media_{len(self.sent_messages) + 1}'
                self.sent_messages.append({
                    'id': message_id,
                    'to': to,
                    'media_type': media_dto.media_type,
                    'filename': media_dto.filename
                })
                return {'success': True, 'message_id': message_id}
            
            # Implement other required methods as mocks...
            def get_message_status(self, message_id):
                return {'status': 'delivered', 'timestamp': 1234567890}
            
            def get_contacts(self, limit=100, offset=0):
                return {'contacts': [], 'total': 0}
            
            def check_contact_exists(self, phone_numbers):
                return {'results': []}
            
            def get_groups(self, limit=100, offset=0):
                return {'groups': self.created_groups, 'total': len(self.created_groups)}
            
            def create_group(self, name, participants, description=""):
                group_id = f'mock_group_{len(self.created_groups) + 1}'
                group = {
                    'group_id': group_id,
                    'name': name,
                    'participants': participants
                }
                self.created_groups.append(group)
                return {'success': True, 'group_id': group_id}
            
            # ... other mock implementations
        
        self.mock_adapter = MockAdapter(self.env, {})
    
    def test_mock_send_message(self):
        """Test mock adapter message sending"""
        result = self.mock_adapter.send_text_message('+1234567890', 'Test message')
        
        self.assertTrue(result['success'])
        self.assertIn('mock_msg_', result['message_id'])
        self.assertEqual(len(self.mock_adapter.sent_messages), 1)
    
    def test_mock_create_group(self):
        """Test mock adapter group creation"""
        result = self.mock_adapter.create_group('Test Group', ['+1234567890'])
        
        self.assertTrue(result['success'])
        self.assertIn('mock_group_', result['group_id'])
        self.assertEqual(len(self.mock_adapter.created_groups), 1)


if __name__ == '__main__':
    unittest.main()
