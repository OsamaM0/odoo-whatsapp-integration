"""
Group Data Transfer Objects  
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class GroupParticipantDTO:
    """Data Transfer Object for group participants"""
    contact_id: str
    phone: str
    name: str = ''
    role: str = 'member'  # admin, member
    joined_at: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to dictionary"""
        return asdict(self)


@dataclass
class GroupDTO:
    """Data Transfer Object for WhatsApp groups"""
    group_id: str  # Provider-specific group ID
    name: str
    description: str = ''
    participants: List[GroupParticipantDTO] = None
    admin_phones: List[str] = None
    invite_link: Optional[str] = None
    profile_picture_url: Optional[str] = None
    created_at: Optional[int] = None
    participant_count: int = 0
    is_announcement: bool = False
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Initialize default values"""
        if self.participants is None:
            self.participants = []
        if self.admin_phones is None:
            self.admin_phones = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert DTO to dictionary"""
        result = asdict(self)
        # Convert participant DTOs to dictionaries
        result['participants'] = [p.to_dict() for p in self.participants]
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GroupDTO':
        """Create DTO from dictionary"""
        # Convert participant dictionaries to DTOs
        if 'participants' in data and data['participants']:
            data['participants'] = [
                GroupParticipantDTO.from_dict(p) if isinstance(p, dict) else p 
                for p in data['participants']
            ]
        
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
