"""
Quick database check script to verify group participants
Run this to see if the data is actually in the database or just not showing in the UI
"""

# SQL queries to check the actual database state:

CHECK_GROUPS_SQL = """
SELECT 
    g.id, 
    g.name, 
    g.group_id,
    g.synced_at,
    COUNT(r.whatsapp_contact_id) as participant_count
FROM whatsapp_group g
LEFT JOIN whatsapp_group_whatsapp_contact_rel r ON g.id = r.whatsapp_group_id
WHERE g.is_active = true
GROUP BY g.id, g.name, g.group_id, g.synced_at
ORDER BY g.name;
"""

CHECK_SPECIFIC_GROUP_SQL = """
SELECT 
    g.name as group_name,
    c.name as contact_name,
    c.phone,
    c.contact_id
FROM whatsapp_group g
JOIN whatsapp_group_whatsapp_contact_rel r ON g.id = r.whatsapp_group_id
JOIN whatsapp_contact c ON r.whatsapp_contact_id = c.id
WHERE g.name LIKE '%VIP%' OR g.name LIKE '%Margins%'
ORDER BY g.name, c.name;
"""

CHECK_RELATION_TABLE_SQL = """
SELECT 
    COUNT(*) as total_relations,
    COUNT(DISTINCT whatsapp_group_id) as groups_with_participants,
    COUNT(DISTINCT whatsapp_contact_id) as contacts_in_groups
FROM whatsapp_group_whatsapp_contact_rel;
"""

print("Use these SQL queries in your database to check the actual data:")
print("\n1. Check all groups and their participant counts:")
print(CHECK_GROUPS_SQL)
print("\n2. Check specific group participants:")
print(CHECK_SPECIFIC_GROUP_SQL)  
print("\n3. Check relation table stats:")
print(CHECK_RELATION_TABLE_SQL)
