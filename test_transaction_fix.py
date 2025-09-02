# WhatsApp Sync Test Script
# 
# Run this in Odoo Python Console to test the fixes
# Copy and paste each section one by one to test incrementally

# Test 1: Test individual sync methods to ensure they return proper format
print("=== Testing Individual Sync Methods ===")

# Test contacts sync
try:
    result = env['whatsapp.contact'].sync_all_contacts_from_api()
    print(f"Contacts sync result: {result}")
    print(f"Contacts success field: {result.get('success')}")
    print(f"Contacts count field: {result.get('count')}")
except Exception as e:
    print(f"Contacts sync error: {e}")

print("\n" + "="*50 + "\n")

# Test groups sync
try:
    result = env['whatsapp.group'].sync_all_groups_from_api()
    print(f"Groups sync result: {result}")
    print(f"Groups success field: {result.get('success')}")
    print(f"Groups count field: {result.get('count')}")
except Exception as e:
    print(f"Groups sync error: {e}")

print("\n" + "="*50 + "\n")

# Test messages sync (limited count for testing)
try:
    result = env['whatsapp.message'].sync_all_messages_from_api(count=10)
    print(f"Messages sync result: {result}")
    print(f"Messages success field: {result.get('success')}")
    print(f"Messages count field: {result.get('count')}")
except Exception as e:
    print(f"Messages sync error: {e}")

print("\n" + "="*50 + "\n")

# Test group members sync
try:
    result = env['whatsapp.group'].sync_all_group_members_from_api()
    print(f"Group members sync result: {result}")
    print(f"Group members success field: {result.get('success')}")
    print(f"Group members count field: {result.get('count')}")
except Exception as e:
    print(f"Group members sync error: {e}")

print("\n" + "="*70 + "\n")

# Test 2: Test the sync service (automated sync)
print("=== Testing Sync Service ===")

try:
    env['whatsapp.sync.service'].cron_sync_all_data()
    
    # Check sync service status
    sync_service = env['whatsapp.sync.service'].search([], limit=1)
    if sync_service:
        print(f"Sync status: {sync_service.sync_status}")
        print(f"Last sync message: {sync_service.last_sync_message}")
        print(f"Last sync time: {sync_service.last_sync_time}")
    else:
        print("No sync service record found")
        
except Exception as e:
    print(f"Sync service error: {e}")

print("\n" + "="*70 + "\n")

# Test 3: Test the sync wizard
print("=== Testing Sync Wizard ===")

try:
    # Create a wizard instance
    wizard = env['whatsapp.sync.wizard'].create({
        'sync_type': 'all'
    })
    
    # Test the sync
    result = wizard.sync_data()
    print(f"Wizard sync result: {result}")
    
    # Check wizard results
    print(f"Contacts synced: {wizard.contacts_synced}")
    print(f"Groups synced: {wizard.groups_synced}")
    print(f"Messages synced: {wizard.messages_synced}")
    print(f"Group members synced: {wizard.group_members_synced}")
    print(f"Errors count: {wizard.errors_count}")
    if wizard.error_messages:
        print(f"Error messages: {wizard.error_messages}")
        
except Exception as e:
    print(f"Wizard sync error: {e}")

print("\n" + "="*70 + "\n")

# Test 4: Test individual components that might fail
print("=== Testing Components That Previously Failed ===")

# Test message sync with very small count
try:
    result = env['whatsapp.message'].sync_all_messages_from_api(count=5)
    print(f"Small message sync - Success: {result.get('success')}, Count: {result.get('count')}")
except Exception as e:
    print(f"Small message sync error: {e}")

# Test group members sync
try:
    result = env['whatsapp.group'].sync_all_group_members_from_api()
    print(f"Group members sync - Success: {result.get('success')}, Count: {result.get('count')}")
except Exception as e:
    print(f"Group members sync error: {e}")

print("\n=== Test Complete ===")
print("If you see 'success': True for most operations and specific error messages")
print("instead of 'transaction aborted' errors, the fix is working!")
