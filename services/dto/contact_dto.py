"""
Contact Data Transfer Objects
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class ContactDTO:
    """Data Transfer Object for WhatsApp contacts"""
    contact_id: str  # Provider-specific contact ID
    phone: str
    name: str = ''
    pushname: str = ''  # WhatsApp push name
    profile_picture_url: Optional[str] = None
    is_whatsapp_user: bool = True
    is_business: bool = False
    last_seen: Optional[int] = None
    status: str = ''  # WhatsApp status
    labels: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContactDTO':
        """Create DTO from dictionary"""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
