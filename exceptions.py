"""
WhatsApp Integration Custom Exceptions
Specific exceptions for better error handling and debugging
"""


class WhatsAppError(Exception):
    """Base exception for WhatsApp integration errors"""
    def __init__(self, message, error_code=None, provider=None):
        self.message = message
        self.error_code = error_code
        self.provider = provider
        super().__init__(self.message)


class WhatsAppConfigurationError(WhatsAppError):
    """Raised when there's a configuration issue"""
    pass


class WhatsAppProviderError(WhatsAppError):
    """Raised when there's a provider-specific error"""
    pass


class WhatsAppAPIError(WhatsAppError):
    """Raised when API calls fail"""
    def __init__(self, message, status_code=None, response_data=None, **kwargs):
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(message, **kwargs)


class WhatsAppValidationError(WhatsAppError):
    """Raised when input validation fails"""
    def __init__(self, message, field=None, **kwargs):
        self.field = field
        super().__init__(message, **kwargs)


class WhatsAppPermissionError(WhatsAppError):
    """Raised when user lacks permission"""
    pass


class WhatsAppRateLimitError(WhatsAppError):
    """Raised when rate limit is exceeded"""
    def __init__(self, message, retry_after=None, **kwargs):
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


class WhatsAppWebhookError(WhatsAppError):
    """Raised when webhook processing fails"""
    pass


class WhatsAppMediaError(WhatsAppError):
    """Raised when media processing fails"""
    def __init__(self, message, media_type=None, file_size=None, **kwargs):
        self.media_type = media_type
        self.file_size = file_size
        super().__init__(message, **kwargs)
