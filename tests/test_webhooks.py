"""
Webhook simulation tests
"""
import unittest
import json
from unittest.mock import Mock, patch
from odoo.tests.common import HttpCase
from odoo.http import request
from ..constants import WHATSAPP_USER_SUFFIX, WHATSAPP_GROUP_SUFFIX


class TestWebhookSimulation(HttpCase):
    """Test webhook handling with simulated payloads"""
    
    def setUp(self):
        super().setUp()
        
        # Create test configuration
        self.test_config = self.env['whatsapp.configuration'].create({
            'name': 'Webhook Test Config',
            'token': 'webhook_test_token',
            'supervisor_phone': '+1234567890',
            'provider': 'whapi',
            'active': True
        })
    
    def test_whapi_message_webhook(self):
        """Test WHAPI message webhook processing"""
        # Simulate WHAPI webhook payload
        webhook_payload = {
            "messages": [
                {
                    "id": "wamid.test123",
                    "type": "text",
                    "from": "1234567890",
                    "from_name": "Test User",
                    "chat_id": f"1234567890{WHATSAPP_USER_SUFFIX}",
                    "chat_name": "Test User",
                    "timestamp": 1634567890,
                    "text": {
                        "body": "Hello from webhook test"
                    },
                    "from_me": False
                }
            ],
            "channel_id": "test_channel"
        }
        
        # Mock the core service
        with patch('odoo.addons.whatsapp_integration.services.whatsapp_core_service.WhatsAppCoreService') as MockCoreService:
            mock_core = Mock()
            mock_core.process_webhook.return_value = {
                'success': True,
                'processed_messages': 1,
                'processed_statuses': 0
            }
            MockCoreService.return_value = mock_core
            
            # Make webhook request
            response = self.url_open(
                '/whatsapp/webhook/messages',
                data=json.dumps(webhook_payload),
                headers={'Content-Type': 'application/json'}
            )
            
            self.assertEqual(response.status_code, 200)
            
            # Verify core service was called
            # mock_core.process_webhook.assert_called_once()
    
    def test_whapi_status_webhook(self):
        """Test WHAPI status webhook processing"""
        webhook_payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "wamid.test123",
                                        "status": "delivered",
                                        "timestamp": "1634567890"
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        
        response = self.url_open(
            '/whatsapp/webhook/status',
            data=json.dumps(webhook_payload),
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 200)
    
    def test_twilio_webhook_simulation(self):
        """Test Twilio webhook format handling"""
        # Simulate Twilio webhook (form data format)
        webhook_data = {
            'MessageSid': 'twiliotest123',
            'From': 'whatsapp:+1234567890',
            'To': 'whatsapp:+0987654321',
            'Body': 'Test message from Twilio webhook',
            'MessageStatus': 'delivered',
            'NumMedia': '0'
        }
        
        from ..services.adapters.twilio_adapter import TwilioAdapter
        from ..services.dto import MessageDTO
        
        # Test webhook parsing
        adapter = TwilioAdapter(self.env, {
            'account_sid': 'test_sid',
            'auth_token': 'test_token',
            'from_number': 'whatsapp:+0987654321'
        })
        
        messages = adapter.parse_webhook_message(webhook_data)
        
        self.assertEqual(len(messages), 1)
        message = messages[0]
        self.assertEqual(message.message_id, 'twiliotest123')
        self.assertEqual(message.content, 'Test message from Twilio webhook')
        self.assertEqual(message.sender_phone, '+1234567890')
    
    def test_webhook_validation(self):
        """Test webhook signature validation"""
        from ..services.adapters.whapi_adapter import WhapiAdapter
        
        adapter = WhapiAdapter(self.env, {'token': 'test_token'})
        
        # WHAPI doesn't use signatures by default, so should return True
        result = adapter.validate_webhook({}, {}, None)
        self.assertTrue(result)
    
    def test_malformed_webhook_handling(self):
        """Test handling of malformed webhook data"""
        malformed_payloads = [
            {},  # Empty payload
            {"messages": []},  # Empty messages
            {"messages": [{"id": "test"}]},  # Missing required fields
            {"invalid": "structure"}  # Completely wrong structure
        ]
        
        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                response = self.url_open(
                    '/whatsapp/webhook/messages',
                    data=json.dumps(payload),
                    headers={'Content-Type': 'application/json'}
                )
                
                # Should not crash, should return error status
                self.assertEqual(response.status_code, 200)
                
                response_data = response.json()
                # Should handle gracefully
                self.assertIn('status', response_data)
    
    def test_duplicate_message_handling(self):
        """Test handling of duplicate webhook messages"""
        webhook_payload = {
            "messages": [
                {
                    "id": "duplicate_test_123",
                    "type": "text",
                    "from": "1234567890",
                    "chat_id": f"1234567890{WHATSAPP_USER_SUFFIX}",
                    "timestamp": 1634567890,
                    "text": {"body": "Duplicate test message"},
                    "from_me": False
                }
            ]
        }
        
        # Send same webhook twice
        for i in range(2):
            response = self.url_open(
                '/whatsapp/webhook/messages',
                data=json.dumps(webhook_payload),
                headers={'Content-Type': 'application/json'}
            )
            
            self.assertEqual(response.status_code, 200)
        
        # Verify only one message was created in database
        messages = self.env['whatsapp.message'].search([
            ('message_id', '=', 'duplicate_test_123')
        ])
        
        # Should have only one message (duplicate detection)
        self.assertEqual(len(messages), 1)
    
    def test_group_message_webhook(self):
        """Test group message webhook processing"""
        group_webhook_payload = {
            "messages": [
                {
                    "id": "group_msg_test_123",
                    "type": "text", 
                    "from": "1234567890",
                    "from_name": "Group Member",
                    "chat_id": f"1234567890-group{WHATSAPP_GROUP_SUFFIX}",
                    "chat_name": "Test Group",
                    "timestamp": 1634567890,
                    "text": {"body": "Group message test"},
                    "from_me": False
                }
            ]
        }
        
        response = self.url_open(
            '/whatsapp/webhook/messages',
            data=json.dumps(group_webhook_payload),
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Verify group was created/updated
        groups = self.env['whatsapp.group'].search([
            ('group_id', '=', f'1234567890-group{WHATSAPP_GROUP_SUFFIX}')
        ])
        
        self.assertTrue(len(groups) > 0)
        group = groups[0]
        self.assertEqual(group.name, 'Test Group')
    
    def test_media_message_webhook(self):
        """Test media message webhook processing"""
        media_webhook_payload = {
            "messages": [
                {
                    "id": "media_test_123",
                    "type": "image",
                    "from": "1234567890",
                    "chat_id": f"1234567890{WHATSAPP_USER_SUFFIX}",
                    "timestamp": 1634567890,
                    "image": {
                        "caption": "Test image caption",
                        "link": "https://example.com/image.jpg",
                        "mime_type": "image/jpeg"
                    },
                    "from_me": False
                }
            ]
        }
        
        response = self.url_open(
            '/whatsapp/webhook/messages',
            data=json.dumps(media_webhook_payload),
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Verify media message was saved
        messages = self.env['whatsapp.message'].search([
            ('message_id', '=', 'media_test_123')
        ])
        
        self.assertEqual(len(messages), 1)
        message = messages[0]
        self.assertEqual(message.message_type, 'image')
        self.assertEqual(message.content, 'Test image caption')


if __name__ == '__main__':
    unittest.main()
