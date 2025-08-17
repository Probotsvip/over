from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class APIKey:
    def __init__(self, key: str, name: str, is_admin: bool = False, 
                 daily_limit: int = 100, created_by: Optional[str] = None, 
                 expiry_days: int = 365):
        self.key = key
        self.name = name
        self.is_admin = is_admin
        self.created_at = datetime.now()
        self.expiry_days = expiry_days
        self.valid_until = datetime.now() + timedelta(days=expiry_days)
        self.daily_limit = daily_limit
        # Reset at midnight
        tomorrow = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        self.reset_at = tomorrow
        self.count = 0
        self.daily_requests = 0  # Current day requests
        self.total_requests = 0  # All time requests
        self.created_by = created_by
        self.status = "active"  # active, expired, suspended
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "is_admin": self.is_admin,
            "created_at": self.created_at,
            "expiry_days": self.expiry_days,
            "valid_until": self.valid_until,
            "daily_limit": self.daily_limit,
            "reset_at": self.reset_at,
            "count": self.count,
            "daily_requests": self.daily_requests,
            "total_requests": self.total_requests,
            "created_by": self.created_by,
            "status": self.status
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'APIKey':
        api_key = cls(
            key=data["key"],
            name=data["name"],
            is_admin=data.get("is_admin", False),
            daily_limit=data.get("daily_limit", 100),
            created_by=data.get("created_by"),
            expiry_days=data.get("expiry_days", 365)
        )
        api_key.created_at = data.get("created_at", datetime.now())
        api_key.valid_until = data.get("valid_until", datetime.now() + timedelta(days=365))
        tomorrow = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        api_key.reset_at = data.get("reset_at", tomorrow)
        api_key.count = data.get("count", 0)
        api_key.daily_requests = data.get("daily_requests", 0)
        api_key.total_requests = data.get("total_requests", 0)
        api_key.status = data.get("status", "active")
        return api_key
    
    def is_expired(self) -> bool:
        return datetime.now() > self.valid_until or self.status == "expired"
    
    def remaining_requests(self) -> int:
        if datetime.now() > self.reset_at:
            return self.daily_limit
        return max(0, self.daily_limit - self.daily_requests)
    
    def auto_reset_if_needed(self) -> bool:
        """Reset daily requests if past midnight. Returns True if reset occurred."""
        if datetime.now() > self.reset_at:
            self.daily_requests = 0
            tomorrow = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            self.reset_at = tomorrow
            return True
        return False
    
    def increment_requests(self) -> None:
        """Increment both daily and total request counters"""
        self.daily_requests += 1
        self.total_requests += 1
        self.count = self.daily_requests  # Keep backward compatibility
    
    def days_until_expiry(self) -> int:
        """Get days remaining until expiry"""
        delta = self.valid_until - datetime.now()
        return max(0, delta.days)
    
    def auto_expire_if_needed(self) -> bool:
        """Auto-expire key if past expiry date. Returns True if expired."""
        if self.is_expired() and self.status != "expired":
            self.status = "expired"
            return True
        return False

class VideoInfo:
    def __init__(self, video_id: str, title: str, duration: str, 
                 quality: str, stream_type: str):
        self.video_id = video_id
        self.title = title
        self.duration = duration
        self.quality = quality
        self.stream_type = stream_type  # 'video' or 'audio'
        self.created_at = datetime.now()
        self.telegram_file_id = None
        self.external_url = None
        self.thumbnail = None
        self.channel = None
        self.views = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "duration": self.duration,
            "quality": self.quality,
            "stream_type": self.stream_type,
            "created_at": self.created_at,
            "telegram_file_id": self.telegram_file_id,
            "external_url": self.external_url,
            "thumbnail": self.thumbnail,
            "channel": self.channel,
            "views": self.views
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VideoInfo':
        video = cls(
            video_id=data["video_id"],
            title=data["title"],
            duration=data["duration"],
            quality=data["quality"],
            stream_type=data["stream_type"]
        )
        video.created_at = data.get("created_at", datetime.now())
        video.telegram_file_id = data.get("telegram_file_id")
        video.external_url = data.get("external_url")
        video.thumbnail = data.get("thumbnail")
        video.channel = data.get("channel")
        video.views = data.get("views")
        return video

class APILog:
    def __init__(self, api_key: str, endpoint: str, query: str, 
                 ip_address: str, response_status: int = 200):
        self.api_key = api_key
        self.endpoint = endpoint
        self.query = query
        self.ip_address = ip_address
        self.timestamp = datetime.now()
        self.response_status = response_status
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "api_key": self.api_key,
            "endpoint": self.endpoint,
            "query": self.query,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp,
            "response_status": self.response_status
        }

class TelegramFile:
    def __init__(self, video_id: str, stream_type: str, file_id: str, 
                 file_unique_id: str, file_size: int):
        self.video_id = video_id
        self.stream_type = stream_type
        self.file_id = file_id
        self.file_unique_id = file_unique_id
        self.file_size = file_size
        self.uploaded_at = datetime.now()
        self.message_id = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "stream_type": self.stream_type,
            "file_id": self.file_id,
            "file_unique_id": self.file_unique_id,
            "file_size": self.file_size,
            "uploaded_at": self.uploaded_at,
            "message_id": self.message_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TelegramFile':
        tg_file = cls(
            video_id=data["video_id"],
            stream_type=data["stream_type"],
            file_id=data["file_id"],
            file_unique_id=data["file_unique_id"],
            file_size=data["file_size"]
        )
        tg_file.uploaded_at = data.get("uploaded_at", datetime.now())
        tg_file.message_id = data.get("message_id")
        return tg_file
