{
    'name': 'WhatsApp Integration',
    'version': '14.0.4.2.0',
    'category': 'Communications',
    'summary': 'WhatsApp group and message management using WHAPI Cloud API by Osama Mohamed',
    'description': '''
        This module provides WhatsApp integration using WHAPI Cloud API (https://gate.whapi.cloud) for:
        - Group management with invite links
        - Message sending and receiving
        - Contact management
        - Media sharing
        - Webhooks for real-time group message processing
        - Comprehensive sync functionality (includes automatic invite link fetching)
        - Bulk operations wizard
        - Multi-provider support (WHAPI + Wassenger compatibility)
        - Clean database schema with provider-specific fields
        - Permission-based access control with configuration-specific data isolation
        - User and group-based WhatsApp configuration access
        - Automatic configuration assignment for seamless user experience
        - Multi-tenant support for different teams using different WhatsApp accounts
    ''',
    'author': 'Osama Mohamed',
    'website': 'https://www.linkedin.com/in/osamam0',
    'depends': ['base', 'web'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/whatsapp_cron.xml',
        'views/whatsapp_configuration_views.xml',
        'wizard/whatsapp_send_message_wizard_views.xml',
        'wizard/whatsapp_sync_wizard_views.xml',
        'wizard/whatsapp_remove_member_wizard_views.xml',
        'wizard/group_member_debug_wizard_views.xml',
        'views/whatsapp_contact_views.xml',
        'views/whatsapp_group_views.xml',
        'views/whatsapp_message_views.xml',
        'views/whatsapp_sync_service_views.xml',
        'views/whatsapp_menu.xml',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
