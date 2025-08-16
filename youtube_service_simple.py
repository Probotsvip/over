import httpx
import logging
import asyncio
from typing import Optional, Dict, Any, List
from models import VideoInfo
from mongo import videos_collection_sync, videos_collection
from telegram_service import telegram_service

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
        """Get video information with MongoDB caching and Telegram integration"""
        try:
            # Step 1: Check if video exists in MongoDB cache
            if videos_collection_sync is not None:
                cached_video = videos_collection_sync.find_one({
                    "video_id": video_id,
                    "stream_type": stream_type
                })
                
                if cached_video:
                    logger.info(f"Found cached video in MongoDB for {video_id} ({stream_type})")
                    
                    # Step 2: Check if Telegram file exists and use it
                    if telegram_service.bot:
                        telegram_url = asyncio.run(telegram_service.check_file_exists(video_id, stream_type))
                        if telegram_url:
                            logger.info(f"Using Telegram file for {video_id} ({stream_type})")
                            cached_video['url'] = telegram_url
                            cached_video['telegram_cached'] = True
                    
                    # Return cached result (remove MongoDB _id)
                    cached_video.pop('_id', None)
                    return cached_video
            
            # Step 3: Not in cache, fetch from external API
            endpoint = YTMP4_ENDPOINT if stream_type == "video" else YTMP3_ENDPOINT
            params = {"url": f"https://youtube.com/watch?v={video_id}"}
            
            logger.info(f"Requesting {stream_type} for video_id: {video_id} from external API")
            
            response = self.client.get(endpoint, params=params)
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"Third party API response: {data}")
                
                if data.get("status") == True:
                    # Normalize response structure
                    if "result" in data:
                        # Nested structure 
                        result = data.get("result", {})
                        video_data = {
                            "video_id": video_id,
                            "stream_type": stream_type,
                            "status": data.get("status"),
                            "title": result.get("title"),
                            "duration": result.get("duration"),
                            "quality": result.get("quality"),
                            "url": result.get("url"),
                            "creator": data.get("creator"),
                            "telegram": data.get("telegram")
                        }
                    else:
                        # Flat structure - add required fields
                        video_data = data.copy()
                        video_data["video_id"] = video_id
                        video_data["stream_type"] = stream_type
                    
                    # Step 4: Save to MongoDB cache
                    if videos_collection_sync is not None:
                        try:
                            videos_collection_sync.insert_one(video_data.copy())
                            logger.info(f"Saved video {video_id} ({stream_type}) to MongoDB cache")
                        except Exception as e:
                            logger.warning(f"Could not save to MongoDB: {e}")
                    
                    # Step 5: Schedule background Telegram upload if bot is configured
                    if telegram_service.bot and video_data.get('url') and video_data.get('title'):
                        try:
                            # Create a new thread for async upload since Flask doesn't have event loop
                            import threading
                            
                            def upload_in_background():
                                try:
                                    asyncio.run(telegram_service.upload_file_background(
                                        video_id, 
                                        stream_type, 
                                        video_data['url'], 
                                        video_data['title']
                                    ))
                                except Exception as e:
                                    logger.error(f"Background Telegram upload failed: {e}")
                            
                            # Start background thread
                            upload_thread = threading.Thread(target=upload_in_background, daemon=True)
                            upload_thread.start()
                            logger.info(f"Started Telegram upload thread for {video_id} ({stream_type})")
                        except Exception as e:
                            logger.warning(f"Could not schedule Telegram upload: {e}")
                    
                    return video_data
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