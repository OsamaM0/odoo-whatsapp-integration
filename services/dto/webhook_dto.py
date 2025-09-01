"""
Webhook and API Response Data Transfer Objects
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class WebhookEventDTO:
    """Data Transfer Object for webhook events"""
    event_type: str  # message, status, group_update, etc.
    provider: str
    timestamp: int
    raw_data: Dict[str, Any]
    processed: bool = False
    messages: List['MessageDTO'] = None
    status_updates: List[Dict[str, Any]] = None
    group_updates: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Initialize default values"""
        if self.messages is None:
            self.messages = []
        if self.status_updates is None:
            self.status_updates = []
        if self.group_updates is None:
            self.group_updates = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to dictionary"""
        result = asdict(self)
        # Convert message DTOs to dictionaries
        result['messages'] = [m.to_dict() for m in self.messages]
        return result


@dataclass
class ApiResponseDTO:
    """Standardized API response wrapper"""
    success: bool
    data: Optional[Any] = None
    message: str = ''
    error_code: Optional[str] = None
    provider: str = ''
    timestamp: Optional[datetime] = None
    request_id: Optional[str] = None
    
    def __post_init__(self):
        """Initialize timestamp if not provided"""
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to dictionary"""
        result = asdict(self)
        if self.timestamp:
            result['timestamp'] = self.timestamp.isoformat()
        return result
