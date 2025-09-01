"""
Debug utilities for image handling in WhatsApp integration
"""
import base64
import logging
from .constants import IMAGE_HEADERS

_logger = logging.getLogger(__name__)

def debug_image_data(data: str, filename: str = "unknown") -> dict:
    """
    Debug image data to understand encoding issues
    
    Args:
        data: Base64 encoded image data
        filename: Optional filename for context
        
    Returns:
        Dictionary with debug information
    """
    debug_info = {
        'filename': filename,
        'original_length': len(data),
        'is_valid_base64': False,
        'is_double_encoded': False,
        'detected_format': None,
        'binary_signature': None,
        'corrected_data': None,
        'errors': []
    }
    
    try:
        # Clean the data
        clean_data = data.replace('\n', '').replace('\r', '').replace(' ', '')
        debug_info['cleaned_length'] = len(clean_data)
        
        # Try to decode as base64
        try:
            first_decode = base64.b64decode(clean_data, validate=True)
            debug_info['is_valid_base64'] = True
            debug_info['decoded_size'] = len(first_decode)
            
            # Get binary signature
            if len(first_decode) >= 10:
                debug_info['binary_signature'] = first_decode[:10].hex().upper()
                
                # Check against known signatures
                signatures = {
                    '89504E470D0A1A0A': 'PNG',
                    'FFD8FFE0': 'JPEG (JFIF)',
                    'FFD8FFE1': 'JPEG (Exif)',
                    'FFD8FFDB': 'JPEG (Samsung)',
                    '474946383761': 'GIF87a',
                    '474946383961': 'GIF89a',
                    '52494646': 'WebP/RIFF',
                    '424D': 'BMP',
                    '49492A00': 'TIFF (Little Endian)',
                    '4D4D002A': 'TIFF (Big Endian)',
                }
                
                for sig, format_name in signatures.items():
                    if debug_info['binary_signature'].startswith(sig):
                        debug_info['detected_format'] = format_name
                        break
            
            # Check for double encoding
            try:
                potential_base64 = first_decode.decode('utf-8')
                
                # Check if it matches image headers
                for header in IMAGE_HEADERS:
                    if potential_base64.startswith(header):
                        try:
                            second_decode = base64.b64decode(potential_base64, validate=True)
                            debug_info['is_double_encoded'] = True
                            debug_info['corrected_data'] = potential_base64
                            debug_info['final_size'] = len(second_decode)
                            _logger.info(f"🔧 Double encoding detected for {filename}")
                            break
                        except Exception as e:
                            debug_info['errors'].append(f"Second decode failed: {e}")
                            
            except UnicodeDecodeError:
                # This is normal - means it's binary data, not double encoded
                debug_info['is_double_encoded'] = False
                
        except Exception as e:
            debug_info['errors'].append(f"Base64 decode failed: {e}")
            
    except Exception as e:
        debug_info['errors'].append(f"Debug failed: {e}")
        
    return debug_info

def log_image_debug_info(data: str, filename: str = "unknown", level: int = logging.INFO):
    """
    Log debug information about image data
    
    Args:
        data: Base64 encoded image data
        filename: Optional filename for context
        level: Logging level
    """
    debug_info = debug_image_data(data, filename)
    
    _logger.log(level, f"=== Image Debug Info for {filename} ===")
    _logger.log(level, f"Original length: {debug_info['original_length']}")
    _logger.log(level, f"Valid base64: {debug_info['is_valid_base64']}")
    _logger.log(level, f"Double encoded: {debug_info['is_double_encoded']}")
    _logger.log(level, f"Detected format: {debug_info['detected_format']}")
    _logger.log(level, f"Binary signature: {debug_info['binary_signature']}")
    
    if debug_info['errors']:
        for error in debug_info['errors']:
            _logger.log(level, f"Error: {error}")
            
def analyze_image_batch(images: list) -> dict:
    """
    Analyze a batch of images and provide summary
    
    Args:
        images: List of tuples (filename, base64_data)
        
    Returns:
        Dictionary with batch analysis results
    """
    summary = {
        'total_images': len(images),
        'valid_base64': 0,
        'double_encoded': 0,
        'formats_detected': {},
        'errors': 0,
        'details': []
    }
    
    for filename, data in images:
        debug_info = debug_image_data(data, filename)
        summary['details'].append(debug_info)
        
        if debug_info['is_valid_base64']:
            summary['valid_base64'] += 1
            
        if debug_info['is_double_encoded']:
            summary['double_encoded'] += 1
            
        if debug_info['detected_format']:
            format_name = debug_info['detected_format']
            summary['formats_detected'][format_name] = summary['formats_detected'].get(format_name, 0) + 1
            
        if debug_info['errors']:
            summary['errors'] += 1
            
    return summary