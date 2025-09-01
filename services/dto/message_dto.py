"""
Message Data Transfer Objects
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class MessageDTO:
    """Data Transfer Object for WhatsApp messages"""
    message_id: str
    content: str
    message_type: str = 'text'
    chat_id: str = ''
    from_me: bool = False
    timestamp: int = 0
    status: str = 'pending'
    sender_phone: Optional[str] = None
    sender_name: Optional[str] = None
    recipient_phone: Optional[str] = None
    group_id: Optional[str] = None
    reply_to_message_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MessageDTO':
        """Create DTO from dictionary"""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class MediaMessageDTO:
    """Data Transfer Object for media messages"""
    media_data: bytes
    filename: str
    media_type: str  # image, video, audio, document
    caption: str = ''
    mime_type: Optional[str] = None
    media_id: Optional[str] = None  # Provider-specific media ID
    media_url: Optional[str] = None  # Direct media URL
    file_size: Optional[int] = None
    duration: Optional[int] = None  # For audio/video
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to dictionary (excluding binary data)"""
        result = asdict(self)
        # Convert bytes to base64 for serialization
        if self.media_data:
            import base64
            result['media_data'] = base64.b64encode(self.media_data).decode('utf-8')
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MediaMessageDTO':
        """Create DTO from dictionary"""
        # Convert base64 back to bytes if needed
        if 'media_data' in data and isinstance(data['media_data'], str):
            import base64
            data['media_data'] = base64.b64decode(data['media_data'])
        
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
