"""
WhatsApp Integration Constants
Centralized constants for better maintainability
"""

# API Timeouts
API_TIMEOUT_SHORT = 30  # seconds
API_TIMEOUT_LONG = 60   # seconds for file uploads

# Retry Configuration
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 1
RETRY_STATUS_CODES = [429, 500, 502, 503, 504]

# Message Types
MESSAGE_TYPES = [
    ('text', 'Text'),
    ('image', 'Image'), 
    ('video', 'Video'),
    ('audio', 'Audio'),
    ('voice', 'Voice'),
    ('document', 'Document'),
    ('gif', 'GIF'),
    ('sticker', 'Sticker'),
    ('location', 'Location'),
    ('contact', 'Contact'),
    ('poll', 'Poll'),
    ('interactive', 'Interactive'),
    ('system', 'System'),
    ('action', 'Action'),
]

# Message Status
MESSAGE_STATUS = [
    ('pending', 'Pending'),
    ('sent', 'Sent'),
    ('delivered', 'Delivered'),
    ('read', 'Read'),
    ('failed', 'Failed'),
    ('deleted', 'Deleted'),
]

# Status constants
STATUS_PENDING = 'pending'
STATUS_SENT = 'sent'
STATUS_DELIVERED = 'delivered'
STATUS_READ = 'read'
STATUS_FAILED = 'failed'
STATUS_DELETED = 'deleted'

# Providers
PROVIDERS = [
    ('wassenger', 'Wassenger'),
    ('whapi', 'WHAPI'),
    ('twilio', 'Twilio'),
]

# Provider constants
PROVIDER_WHAPI = 'whapi'
PROVIDER_WASSENGER = 'wassenger'
PROVIDER_TWILIO = 'twilio'

# MIME Types
MIME_TYPES = {
    'image': {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        'default': 'image/jpeg'
    },
    'video': {
        '.mp4': 'video/mp4',
        '.avi': 'video/avi',
        '.mov': 'video/quicktime',
        'default': 'video/mp4'
    },
    'audio': {
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.ogg': 'audio/ogg',
        'default': 'audio/mpeg'
    },
    'document': {
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'default': 'application/octet-stream'
    }
}

# Pagination Defaults
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500

# WhatsApp ID Patterns
WHATSAPP_GROUP_SUFFIX = '@g.us'
WHATSAPP_USER_SUFFIX = '@s.whatsapp.net'

# Image Headers for Double Encoding Detection
IMAGE_HEADERS = [
    'iVBORw0KGgo',  # PNG
    '/9j/',         # JPEG (standard)
    'R0lGOD',       # GIF87a and GIF89a
    'UklGR',        # WebP (RIFF)
    'Qk',           # BMP
    'SUkq',         # TIFF Little Endian
    'TU0A',         # TIFF Big Endian
    '/0//',         # JPEG2000
    'AAABAA',       # ICO
    'data:image/',  # Data URL format
]

# Error Messages
ERROR_MESSAGES = {
    'NO_PROVIDER': 'No WhatsApp provider configured',
    'INVALID_CONFIG': 'Invalid provider configuration',
    'MISSING_FIELDS': 'Required fields are missing',
    'API_ERROR': 'API request failed',
    'WEBHOOK_INVALID': 'Webhook validation failed',
    'PERMISSION_DENIED': 'Permission denied',
    'RATE_LIMIT': 'Rate limit exceeded',
}
