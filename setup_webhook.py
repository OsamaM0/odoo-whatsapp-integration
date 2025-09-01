#!/usr/bin/env python3
"""
WhatsApp Webhook Setup Helper

This script helps you set up the webhook endpoint in your WHAPI account.
"""

import json
import requests
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WhapiWebhookManager:
    def __init__(self, api_token, base_url="https://gate.whapi.cloud"):
        self.api_token = api_token
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
    
    def set_webhook(self, webhook_url, events=None):
        """Set webhook URL for WHAPI account"""
        if events is None:
            events = ["messages"]  # Default to messages only
        
        endpoint = f"{self.base_url}/settings/webhook"
        
        payload = {
            "url": webhook_url,
            "events": events
        }
        
        try:
            response = requests.post(endpoint, json=payload, headers=self.headers)
            
            if response.status_code == 200:
                logger.info("✅ Webhook set successfully!")
                return True, response.json()
            else:
                logger.error(f"❌ Failed to set webhook: {response.status_code} - {response.text}")
                return False, response.text
                
        except Exception as e:
            logger.error(f"❌ Error setting webhook: {e}")
            return False, str(e)
    
    def get_webhook_info(self):
        """Get current webhook configuration"""
        endpoint = f"{self.base_url}/settings/webhook"
        
        try:
            response = requests.get(endpoint, headers=self.headers)
            
            if response.status_code == 200:
                webhook_info = response.json()
                logger.info("Current webhook configuration:")
                logger.info(json.dumps(webhook_info, indent=2))
                return True, webhook_info
            else:
                logger.error(f"❌ Failed to get webhook info: {response.status_code} - {response.text}")
                return False, response.text
                
        except Exception as e:
            logger.error(f"❌ Error getting webhook info: {e}")
            return False, str(e)

def setup_webhook_interactive():
    """Interactive webhook setup"""
    print("🔧 WhatsApp Webhook Setup Helper")
    print("=" * 50)
    
    # Get WHAPI token
    api_token = input("Enter your WHAPI API token: ").strip()
    if not api_token:
        print("❌ API token is required!")
        return
    
    # Get webhook URL
    print("\n📡 Webhook URL Configuration")
    print("Your webhook URL should be in the format:")
    print("https://your-odoo-domain.com/whatsapp/webhook/whapi")
    
    webhook_url = input("Enter your webhook URL: ").strip()
    if not webhook_url:
        print("❌ Webhook URL is required!")
        return
    
    # Initialize manager
    manager = WhapiWebhookManager(api_token)
    
    # Get current webhook info
    print("\n📋 Current webhook configuration:")
    manager.get_webhook_info()
    
    # Set new webhook
    print(f"\n⚙️  Setting webhook URL: {webhook_url}")
    
    events = ["messages"]  # Default events
    custom_events = input("Enter events to monitor (default: messages): ").strip()
    if custom_events:
        events = [e.strip() for e in custom_events.split(",")]
    
    success, response = manager.set_webhook(webhook_url, events)
    
    if success:
        print("\n🎉 Webhook setup completed successfully!")
        print("\nNext steps:")
        print("1. Send a message to a WhatsApp group")
        print("2. Check your Odoo logs for webhook activity")
        print("3. Verify that messages appear in the WhatsApp Messages menu")
        
        # Verify setup
        verify = input("\n🔍 Would you like to verify the webhook configuration? (Y/n): ").strip().lower()
        if verify != 'n':
            print("\nVerifying webhook configuration...")
            manager.get_webhook_info()
    else:
        print("\n❌ Webhook setup failed!")
        print(f"Error: {response}")

def main():
    """Main function"""
    print("WhatsApp Group Messages Webhook Setup")
    print("=" * 50)
    
    print("\nThis tool helps you set up webhooks for receiving WhatsApp group messages.")
    print("Make sure you have:")
    print("✓ WHAPI API token")
    print("✓ Odoo server running and accessible")
    print("✓ Webhook module installed and configured")
    
    proceed = input("\nProceed with setup? (Y/n): ").strip().lower()
    if proceed == 'n':
        return
    
    try:
        setup_webhook_interactive()
    except KeyboardInterrupt:
        print("\n\n👋 Setup cancelled by user.")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()
