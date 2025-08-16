import re
import httpx
import asyncio
import logging
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any, Tuple
from config import EXTERNAL_API_BASE, REQUEST_TIMEOUT
from mongo import videos_collection
from models import VideoInfo
from telegram_service import telegram_service

logger = logging.getLogger(__name__)

class YouTubeService:
    def __init__(self):
        self.api_base = EXTERNAL_API_BASE
        self.timeout = REQUEST_TIMEOUT
    
    def extract_video_id(self, query: str) -> Optional[str]:
        """Extract YouTube video ID from URL or return query if it's already an ID"""
        # YouTube video ID patterns
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
            r'^[a-zA-Z0-9_-]{11}$'  # Direct video ID
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                return match.group(1) if len(match.groups()) > 0 else match.group(0)
        
        return None
    
    def build_youtube_url(self, video_id: str) -> str:
        """Build YouTube URL from video ID"""
        return f"https://www.youtube.com/watch?v={video_id}"
    
    async def get_from_cache(self, video_id: str, stream_type: str) -> Optional[Dict[str, Any]]:
        """Get video info from MongoDB cache"""
        try:
            # First check Telegram cache
            telegram_url = await telegram_service.check_file_exists(video_id, stream_type)
            if telegram_url:
                # Get additional info from MongoDB
                video_doc = await videos_collection.find_one({"video_id": video_id})
                if video_doc:
                    video_info = VideoInfo.from_dict(video_doc)
                    return {
                        "id": video_id,
                        "title": video_info.title,
                        "duration": video_info.duration,
                        "link": self.build_youtube_url(video_id),
                        "channel": video_info.channel,
                        "views": video_info.views,
                        "thumbnail": video_info.thumbnail,
                        "stream_url": telegram_url,
                        "stream_type": "Video" if stream_type == "video" else "Audio",
                        "cached": True,
                        "source": "telegram"
                    }
            
            # Check MongoDB for external URL cache
            video_doc = await videos_collection.find_one({
                "video_id": video_id,
                "stream_type": stream_type
            })
            
            if video_doc:
                video_info = VideoInfo.from_dict(video_doc)
                if video_info.external_url:
                    return {
                        "id": video_id,
                        "title": video_info.title,
                        "duration": video_info.duration,
                        "link": self.build_youtube_url(video_id),
                        "channel": video_info.channel,
                        "views": video_info.views,
                        "thumbnail": video_info.thumbnail,
                        "stream_url": video_info.external_url,
                        "stream_type": "Video" if stream_type == "video" else "Audio",
                        "cached": True,
                        "source": "mongodb"
                    }
            
            return None
        except Exception as e:
            logger.error(f"Error getting from cache: {e}")
            return None
    
    async def get_from_external_api(self, video_id: str, stream_type: str) -> Optional[Dict[str, Any]]:
        """Get video info from external API"""
        try:
            youtube_url = self.build_youtube_url(video_id)
            
            # Determine API endpoint
            if stream_type == "video":
                api_url = f"{self.api_base}/ytmp4"
            else:
                api_url = f"{self.api_base}/ytmp3"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(api_url, params={"url": youtube_url})
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("status") and data.get("result"):
                        result = data["result"]
                        
                        # Create video info object
                        video_info = VideoInfo(
                            video_id=video_id,
                            title=result.get("title", "Unknown Title"),
                            duration=result.get("duration", "Unknown"),
                            quality=result.get("quality", "Unknown"),
                            stream_type=stream_type
                        )
                        video_info.external_url = result.get("url")
                        
                        # Save to MongoDB
                        await videos_collection.update_one(
                            {"video_id": video_id, "stream_type": stream_type},
                            {"$set": video_info.to_dict()},
                            upsert=True
                        )
                        
                        # Schedule background upload to Telegram
                        if video_info.external_url:
                            telegram_service.schedule_background_upload(
                                video_id, stream_type, video_info.external_url, video_info.title
                            )
                        
                        return {
                            "id": video_id,
                            "title": video_info.title,
                            "duration": video_info.duration,
                            "link": youtube_url,
                            "channel": video_info.channel,
                            "views": video_info.views,
                            "thumbnail": video_info.thumbnail,
                            "stream_url": video_info.external_url,
                            "stream_type": "Video" if stream_type == "video" else "Audio",
                            "cached": False,
                            "source": "external_api"
                        }
                
                logger.error(f"External API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting from external API: {e}")
            return None
    
    async def get_video_info(self, query: str, video: bool = False) -> Optional[Dict[str, Any]]:
        """Main method to get video information"""
        try:
            # Extract video ID
            video_id = self.extract_video_id(query)
            if not video_id:
                return None
            
            stream_type = "video" if video else "audio"
            
            # Check cache first (Telegram and MongoDB)
            cached_result = await self.get_from_cache(video_id, stream_type)
            if cached_result:
                return cached_result
            
            # Fallback to external API
            external_result = await self.get_from_external_api(video_id, stream_type)
            return external_result
            
        except Exception as e:
            logger.error(f"Error in get_video_info: {e}")
            return None

# Global instance
youtube_service = YouTubeService()
