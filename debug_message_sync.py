"""
Debug script to test message sync in smaller batches
"""

def debug_message_sync():
    """Test message sync with smaller parameters to avoid overwhelming the system"""
    
    # Test parameters - start small
    test_params = {
        'count': 20,  # Only 20 messages per page
        'time_from': None,
        'time_to': None, 
        'from_me': None,  # Both incoming and outgoing
        'normal_types': True,  # Only normal message types
        'sort': 'desc'
    }
    
    print("Testing message sync with small batch size...")
    print(f"Parameters: {test_params}")
    
    # This would be run in Odoo context:
    # result = env['whatsapp.message'].sync_all_messages_from_api(**test_params)
    
    return test_params

# Expected workflow:
# 1. Start with count=20 to test small batches
# 2. If successful, gradually increase count=50, 100, etc.
# 3. Monitor logs for transaction errors
# 4. Use time filters to sync specific periods if needed

debug_message_sync()
