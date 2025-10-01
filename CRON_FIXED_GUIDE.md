# WhatsApp Integration Cron Job Setup Guide

## Overview
Your WhatsApp Integration module now includes automatic cron jobs that will sync data every hour. This guide will help you verify and manage these cron jobs.

## What's Fixed
1. **Proper XML Cron Definition**: The cron jobs are now defined in `data/whatsapp_cron.xml` and will be installed automatically
2. **Post-Init Hook**: Added automatic initialization when the module is installed
3. **Simplified Management**: Removed complex programmatic creation and simplified the process

## Cron Jobs Included

### 1. WhatsApp Data Sync (Hourly - ACTIVE)
- **Name**: WhatsApp Data Sync
- **Frequency**: Every 1 hour
- **Status**: Active by default
- **Function**: Syncs contacts, groups, messages (50 latest), and group members

### 2. WhatsApp Data Sync (Frequent - INACTIVE)
- **Name**: WhatsApp Data Sync (Frequent)
- **Frequency**: Every 30 minutes
- **Status**: Inactive by default (you can enable if needed)
- **Function**: Same as hourly but more frequent

### 3. WhatsApp Full Data Sync (Daily - INACTIVE)
- **Name**: WhatsApp Full Data Sync (Daily)
- **Frequency**: Every 1 day
- **Status**: Inactive by default
- **Function**: Comprehensive sync with 200 messages per configuration

## Setup Instructions

### Step 1: Upgrade Your Module
1. Go to **Apps** in Odoo
2. Search for "WhatsApp Integration"
3. Click **Upgrade** (this will install the new cron jobs)

### Step 2: Verify Installation
1. Go to **WhatsApp > Sync Service**
2. Click **Check Cron Status** button
3. You should see 3 cron jobs listed

### Step 3: Check Cron Jobs Directly (Optional)
1. Enable **Developer Mode**: Settings > Activate Developer Mode
2. Go to **Settings > Technical > Automation > Scheduled Actions**
3. Search for "WhatsApp" to see all WhatsApp cron jobs
4. Verify that "WhatsApp Data Sync" is **Active**

### Step 4: Test Manual Sync
1. Go to **WhatsApp > Sync Service**
2. Click **Sync Now** button
3. Check the result notification and sync status

## Managing Cron Jobs

### Enable/Disable Cron Jobs
1. Go to **Settings > Technical > Automation > Scheduled Actions**
2. Find the WhatsApp cron job you want to modify
3. Check/uncheck the **Active** field
4. Save the record

### Modify Sync Frequency
1. Go to **Settings > Technical > Automation > Scheduled Actions**
2. Find the cron job you want to modify
3. Change **Execute Every** (number) and **Unit** (minutes/hours/days)
4. Save the record

### Recommended Settings
- **Production**: Keep "WhatsApp Data Sync" (hourly) active
- **Development**: Use "WhatsApp Data Sync (Frequent)" (30 minutes) for testing
- **Large Datasets**: Enable "WhatsApp Full Data Sync (Daily)" for comprehensive syncing

## Troubleshooting

### Cron Jobs Not Found
If you don't see any WhatsApp cron jobs:
1. Upgrade the module completely
2. Check the server logs for errors during installation
3. Verify the module is properly installed

### Sync Errors
1. Check **WhatsApp > Sync Service** for error messages
2. Verify your WhatsApp configurations are active and have valid tokens
3. Check server logs for detailed error information

### Performance Issues
If syncing is too slow or causes performance issues:
1. Disable frequent syncing (30-minute cron)
2. Reduce message count in daily sync
3. Monitor server resources during sync

## Verification Commands (Advanced)

If you have access to Odoo shell, you can run these commands to verify:

```python
# Check all WhatsApp cron jobs
crons = env['ir.cron'].search([('name', 'ilike', 'WhatsApp')])
for cron in crons:
    print(f"{cron.name}: {'ACTIVE' if cron.active else 'INACTIVE'} - Next: {cron.nextcall}")

# Manual sync test
env['whatsapp.sync.service'].cron_sync_all_data()

# Check sync service status
sync_service = env['whatsapp.sync.service'].search([], limit=1)
print(f"Last sync: {sync_service.last_sync_time}")
print(f"Status: {sync_service.sync_status}")
print(f"Message: {sync_service.last_sync_message}")
```

## Next Steps
1. Upgrade your module to apply these fixes
2. Verify the cron jobs are installed and the hourly sync is active
3. Monitor the sync service for successful operations
4. Adjust frequency settings based on your needs

Your cron job should now work automatically! The hourly sync will keep your WhatsApp data up to date without any manual intervention.