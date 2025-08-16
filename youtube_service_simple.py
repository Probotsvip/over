import httpx
import asyncio
import logging
from typing import Optional, Dict, Any, List
from models import VideoInfo

logger = logging.getLogger(__name__)

# External API endpoints
EXTERNAL_API_BASE = "https://jerrycoder.oggyapi.workers.dev"
YTMP4_ENDPOINT = f"{EXTERNAL_API_BASE}/ytmp4"
YTMP3_ENDPOINT = f"{EXTERNAL_API_BASE}/ytmp3"

class YouTubeService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def get_video_info(self, video_id: str, stream_type: str = "video") -> Optional[Dict[str, Any]]:
        """Get video information from external API"""
        try:
            endpoint = YTMP4_ENDPOINT if stream_type == "video" else YTMP3_ENDPOINT
            
            # Build request
            params = {"url": f"https://youtube.com/watch?v={video_id}"}
            
            logger.info(f"Requesting {stream_type} for video_id: {video_id}")
            
            response = await self.client.get(endpoint, params=params)
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "success":
                    return data
                else:
                    logger.error(f"API returned error: {data}")
                    return None
            else:
                logger.error(f"HTTP error {response.status_code}: {response.text}")
                return None
                    
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None
    
    async def get_video_stream(self, video_id: str, quality: str = "720p") -> Optional[Dict[str, Any]]:
        """Get video stream URL"""
        return await self.get_video_info(video_id, "video")
    
    async def get_audio_stream(self, video_id: str, quality: str = "128") -> Optional[Dict[str, Any]]:
        """Get audio stream URL"""  
        return await self.get_video_info(video_id, "audio")
    
    async def stream_content(self, url: str, chunk_size: int = 1024*1024):
        """Stream content from URL in chunks"""
        try:
            async with self.client.stream('GET', url) as response:
                if response.status_code == 200:
                    async for chunk in response.aiter_bytes(chunk_size):
                        yield chunk
                else:
                    logger.error(f"Failed to stream content: {response.status_code}")
        except Exception as e:
            logger.error(f"Error streaming content: {e}")
    
    def parse_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from YouTube URL"""
        import re
        
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]+)',
            r'youtube\.com/v/([a-zA-Z0-9_-]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        # If no pattern matches, assume it's already a video ID
        if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
            return url
            
        return None

# Create global instance
youtube_service = YouTubeService()