# WhatsApp Sync Service and Cron Job Setup Script
# 
# Run this in Odoo Python Console or Developer Mode
# 
# HOW TO RUN:
# 1. Go to Settings > Activate Developer Mode
# 2. Go to Settings > Technical > Database Structure > Models
# 3. Search for and click on "whatsapp.sync.service"
# 4. Click "Create" or find existing records
# 5. Copy and paste the code below in Python console or Execute action

# Method 1: Create sync service record and cron jobs
try:
    # Create or get sync service record
    sync_service = env['whatsapp.sync.service'].search([], limit=1)
    if not sync_service:
        sync_service = env['whatsapp.sync.service'].create({
            'name': 'WhatsApp Auto Sync Service'
        })
        print(f"Created sync service record: {sync_service.name}")
    else:
        print(f"Found existing sync service: {sync_service.name}")
    
    # Create cron jobs
    cron_jobs = env['whatsapp.sync.service'].init_cron_jobs()
    if cron_jobs:
        print(f"Successfully created {len(cron_jobs)} cron jobs:")
        for job in cron_jobs:
            print(f"  - {job.name} (Active: {job.active})")
    else:
        print("Cron jobs may already exist or creation failed")
        
    # Check all WhatsApp cron jobs
    all_crons = env['ir.cron'].search([('name', 'ilike', 'WhatsApp')])
    print(f"\nAll WhatsApp cron jobs ({len(all_crons)}):")
    for cron in all_crons:
        status = "ACTIVE" if cron.active else "INACTIVE"
        print(f"  - {cron.name} [{status}] - Next: {cron.nextcall}")
        
    print("\n✅ Setup completed!")
    print("Now go to WhatsApp > Sync Service to see the buttons")
    
except Exception as e:
    print(f"❌ Error: {str(e)}")

# Method 2: Alternative direct cron creation (if above fails)
# Uncomment and run this if Method 1 doesn't work:

"""
try:
    # Direct cron job creation
    model_id = env['ir.model'].search([('model', '=', 'whatsapp.sync.service')], limit=1)
    if model_id:
        cron_data = [
            {
                'name': 'WhatsApp Data Sync',
                'model_id': model_id.id,
                'state': 'code',
                'code': 'model.cron_sync_all_data()',
                'interval_number': 1,
                'interval_type': 'hours',
                'numbercall': -1,
                'active': True,
                'user_id': env.ref('base.user_root').id,
                'doall': False,
            },
            {
                'name': 'WhatsApp Data Sync (Frequent)',
                'model_id': model_id.id,
                'state': 'code',
                'code': 'model.cron_sync_all_data()',
                'interval_number': 30,
                'interval_type': 'minutes',
                'numbercall': -1,
                'active': False,
                'user_id': env.ref('base.user_root').id,
                'doall': False,
            }
        ]
        
        for data in cron_data:
            existing = env['ir.cron'].search([('name', '=', data['name'])], limit=1)
            if not existing:
                cron = env['ir.cron'].create(data)
                print(f"Created cron: {cron.name}")
            else:
                print(f"Cron already exists: {existing.name}")
                
    print("Direct cron creation completed!")
except Exception as e:
    print(f"Direct creation error: {str(e)}")
"""
