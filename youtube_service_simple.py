import httpx
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
        self.client = httpx.Client(
            timeout=10.0,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        )
    
    def get_video_info(self, video_id: str, stream_type: str = "video") -> Optional[Dict[str, Any]]:
        """Get video information from external API - real data only"""
        try:
            endpoint = YTMP4_ENDPOINT if stream_type == "video" else YTMP3_ENDPOINT
            
            # Build request
            params = {"url": f"https://youtube.com/watch?v={video_id}"}
            
            logger.info(f"Requesting {stream_type} for video_id: {video_id}")
            
            response = self.client.get(endpoint, params=params)
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == True or data.get("status") == "success":
                    return data
                else:
                    logger.error(f"API returned error: {data}")
                    return None
            else:
                logger.error(f"HTTP error {response.status_code}: {response.text}")
                return None
                    
        except httpx.TimeoutException:
            logger.error(f"Timeout while requesting {stream_type} for video_id: {video_id}")
            return None
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None
    
    
    def get_video_stream(self, video_id: str, quality: str = "720p") -> Optional[Dict[str, Any]]:
        """Get video stream URL"""
        return self.get_video_info(video_id, "video")
    
    def get_audio_stream(self, video_id: str, quality: str = "128") -> Optional[Dict[str, Any]]:
        """Get audio stream URL"""  
        return self.get_video_info(video_id, "audio")
    
    def stream_content(self, url: str, chunk_size: int = 1024*1024):
        """Stream content from URL in chunks"""
        try:
            with self.client.stream('GET', url) as response:
                if response.status_code == 200:
                    for chunk in response.iter_bytes(chunk_size):
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