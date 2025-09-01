# WhatsApp Integration Cron Job Setup

## Overview
This module now includes automated synchronization of WhatsApp data using Odoo's cron job system. The system will automatically sync contacts, groups, messages, and group members at regular intervals.

## Cron Jobs Included

### 1. Hourly Sync (Active by default)
- **Name**: WhatsApp Data Sync
- **Frequency**: Every 1 hour
- **Status**: Active
- **Function**: Syncs recent data (50 messages per config)

### 2. Frequent Sync (Disabled by default)
- **Name**: WhatsApp Data Sync (Frequent)
- **Frequency**: Every 30 minutes
- **Status**: Inactive (you can enable if needed)
- **Function**: More frequent sync for high-activity environments

### 3. Daily Full Sync (Disabled by default)
- **Name**: WhatsApp Full Data Sync (Daily)
- **Frequency**: Every 24 hours
- **Status**: Inactive (you can enable if needed)
- **Function**: Full sync with more messages (200 per config)

## How to Monitor Sync

1. Go to **WhatsApp > Sync Service** menu
2. View the sync status and last sync information
3. Use the "Sync Now" button to trigger manual sync

## How to Enable/Disable Cron Jobs

1. Go to **Settings > Technical > Automation > Scheduled Actions**
2. Search for "WhatsApp"
3. Edit the cron jobs to:
   - Enable/disable them
   - Change frequency
   - Modify sync parameters

## Cron Job Configuration

### To change sync frequency:
1. Go to Settings > Technical > Automation > Scheduled Actions
2. Find "WhatsApp Data Sync"
3. Edit the "Execute Every" field

### To enable additional cron jobs:
1. Find "WhatsApp Data Sync (Frequent)" or "WhatsApp Full Data Sync (Daily)"
2. Check the "Active" checkbox
3. Save

## Manual Sync Options

### Via UI:
- **WhatsApp > Sync Service**: Click "Sync Now" button (available after creating a sync service record)
- **WhatsApp > Sync Wizard**: Use the detailed sync wizard

### Create Sync Service Record:
If you don't see the "Sync Now" button:
1. Go to **WhatsApp > Sync Service**
2. Click **"Create"** to create a new sync service record
3. Enter name: "WhatsApp Auto Sync Service" 
4. Save the record
5. Now you should see the "Sync Now" and "Create Cron Jobs" buttons

### Via Code/Terminal:
```python
# Manual sync all data
env['whatsapp.sync.service'].cron_sync_all_data()

# Or using the sync wizard
env['whatsapp.sync.wizard'].create({'sync_type': 'all'}).sync_data()
```

## Troubleshooting

### Check Sync Status:
1. Go to **WhatsApp > Sync Service**
2. Check the "Sync Status" and "Last Sync Message"

### Check Cron Logs:
1. Go to **Settings > Technical > Automation > Scheduled Actions**
2. Find the WhatsApp sync actions
3. Check the "Last Run" information

### Common Issues:
- **No active configurations**: Ensure you have active WhatsApp configurations
- **API errors**: Check your WHAPI/Wassenger API credentials
- **Permission errors**: Ensure users have proper WhatsApp groups assigned

## Security

- Only users with WhatsApp permissions can access sync data
- Each configuration syncs only its own data
- Sync service respects the same permission model as the rest of the module

## Performance Notes

- Hourly sync fetches 50 messages per configuration
- Daily sync fetches 200 messages per configuration
- Adjust message counts in cron job code if needed
- Monitor system performance and adjust frequency accordingly
