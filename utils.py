"""
WhatsApp Integration Utilities
Common utility functions used across the module
"""
import re
import base64
import mimetypes
from typing import Optional, Tuple
from .constants import (
    IMAGE_HEADERS, MIME_TYPES, WHATSAPP_GROUP_SUFFIX, 
    WHATSAPP_USER_SUFFIX, ERROR_MESSAGES
)


def validate_phone_number(phone: str) -> Tuple[bool, str]:
    """
    Validate and normalize phone number
    
    Args:
        phone: Phone number to validate
        
    Returns:
        Tuple of (is_valid, normalized_phone)
    """
    if not phone:
        return False, ""
    
    # Remove all non-digit characters
    clean_phone = re.sub(r'\D', '', phone)
    
    # Basic validation - must be at least 10 digits
    if len(clean_phone) < 10:
        return False, ""
    
    # Remove leading zeros but keep country code
    clean_phone = clean_phone.lstrip('0')
    
    # Add + prefix if not present
    if not phone.startswith('+'):
        clean_phone = f"+{clean_phone}"
    
    return True, clean_phone


def is_group_id(identifier: str) -> bool:
    """Check if identifier is a WhatsApp group ID"""
    return identifier.endswith(WHATSAPP_GROUP_SUFFIX)


def is_user_id(identifier: str) -> bool:
    """Check if identifier is a WhatsApp user ID"""
    return identifier.endswith(WHATSAPP_USER_SUFFIX)


def format_whatsapp_id(phone: str, is_group: bool = False) -> str:
    """
    Format phone number as WhatsApp ID
    
    Args:
        phone: Phone number
        is_group: Whether this is a group ID
        
    Returns:
        Formatted WhatsApp ID
    """
    clean_phone = re.sub(r'\D', '', phone)
    
    if is_group:
        return f"{clean_phone}{WHATSAPP_GROUP_SUFFIX}"
    else:
        return f"{clean_phone}{WHATSAPP_USER_SUFFIX}"


def fix_double_base64_encoding(data: str) -> str:
    """
    Fix double base64 encoding issue from Odoo binary fields
    
    Args:
        data: Base64 encoded string that might be double-encoded
        
    Returns:
        Corrected base64 string
    """
    try:
        # Clean the base64 data first
        clean_data = data.replace('\n', '').replace('\r', '').replace(' ', '')
        
        # Try to decode and check if it's double encoded
        try:
            first_decode = base64.b64decode(clean_data, validate=True)
            
            # Check if the first decode result is still base64 by trying to decode it as text
            try:
                potential_base64 = first_decode.decode('utf-8')
                
                # Check if this looks like base64 by checking for image headers
                header_match = False
                for header in IMAGE_HEADERS:
                    if potential_base64.startswith(header):
                        header_match = True
                        break
                
                if header_match:
                    # Validate this is actually valid base64 by decoding it
                    try:
                        base64.b64decode(potential_base64, validate=True)
                        return potential_base64  # Return the corrected base64
                    except Exception:
                        pass
                        
                # Additional check: if the decoded string is mostly base64 characters
                elif _looks_like_base64(potential_base64):
                    try:
                        base64.b64decode(potential_base64, validate=True)
                        return potential_base64
                    except Exception:
                        pass
                        
            except UnicodeDecodeError:
                # First decode is binary (correct), not double encoded
                pass
                
            # Not double encoded, return original cleaned data
            return clean_data
            
        except Exception:
            return clean_data
            
    except Exception:
        return data  # Return original data if anything fails


def _looks_like_base64(text: str) -> bool:
    """
    Check if text looks like base64 encoded data
    
    Args:
        text: Text to check
        
    Returns:
        True if text looks like base64
    """
    if not text or len(text) < 4:
        return False
    
    # Base64 should be mostly alphanumeric with +, /, and = characters
    import re
    base64_pattern = re.compile(r'^[A-Za-z0-9+/]*={0,2}$')
    
    # Check if it matches base64 pattern and has reasonable length
    return (base64_pattern.match(text) and 
            len(text) % 4 == 0 and  # Base64 padding requires length divisible by 4
            len(text) > 20)  # Reasonable minimum size for image data


def get_mime_type_from_filename(filename: str, media_type: str = None) -> str:
    """
    Get MIME type from filename and media type
    
    Args:
        filename: File name with extension
        media_type: Media type category (image, video, audio, document)
        
    Returns:
        MIME type string
    """
    if not filename:
        return 'application/octet-stream'
    
    # First try Python's mimetypes
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type:
        return mime_type
    
    # Fallback to our mapping
    if media_type and media_type in MIME_TYPES:
        type_map = MIME_TYPES[media_type]
        
        # Find by extension
        for ext, mime in type_map.items():
            if ext != 'default' and filename.lower().endswith(ext):
                return mime
        
        # Return default for this media type
        return type_map['default']
    
    return 'application/octet-stream'


def validate_base64(data: str) -> bool:
    """
    Validate if string is valid base64
    
    Args:
        data: String to validate
        
    Returns:
        True if valid base64, False otherwise
    """
    try:
        # Clean the data
        clean_data = data.replace('\n', '').replace('\r', '').replace(' ', '')
        
        # Try to decode
        decoded = base64.b64decode(clean_data, validate=True)
        
        # Re-encode and compare
        reencoded = base64.b64encode(decoded).decode('utf-8')
        
        return clean_data == reencoded
    except Exception:
        return False


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate string to maximum length
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add when truncated
        
    Returns:
        Truncated string
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe storage
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed_file"
    
    # Remove/replace dangerous characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(' .')
    
    # Ensure it's not empty
    if not sanitized:
        return "unnamed_file"
    
    return sanitized


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human readable format
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string
    """
    if size_bytes == 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    
    return f"{size:.1f} {units[unit_index]}"


def extract_error_message(error_data) -> str:
    """
    Extract meaningful error message from various error formats using constants
    
    Args:
        error_data: Error data (dict, exception, string)
        
    Returns:
        Formatted error message
    """
    if isinstance(error_data, dict):
        # Try different common error fields
        for field in ['message', 'error', 'detail', 'description']:
            if field in error_data:
                return str(error_data[field])
        
        # If no standard field, return string representation
        return str(error_data)
    
    elif isinstance(error_data, Exception):
        return str(error_data)
    
    else:
        return str(error_data)


def get_standard_error_message(error_key: str, default: str = None) -> str:
    """Get standardized error message from constants"""
    return ERROR_MESSAGES.get(error_key, default or ERROR_MESSAGES.get('API_ERROR', 'Unknown error'))
