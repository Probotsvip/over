import asyncio
import logging
import httpx
from typing import Optional, Tuple
try:
    from telegram import Bot
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    # Fallback if telegram is not properly installed
    Bot = None
    TelegramError = Exception
    TELEGRAM_AVAILABLE = False
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
from mongo import telegram_files_collection, telegram_files_collection_sync
from models import TelegramFile

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.channel_id = TELEGRAM_CHANNEL_ID
        self.bot = None
        
        if TELEGRAM_AVAILABLE and Bot and self.bot_token and self.channel_id:
            try:
                self.bot = Bot(token=self.bot_token)
                logger.info("Telegram bot initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Telegram bot: {e}")
        else:
            if not TELEGRAM_AVAILABLE:
                logger.warning("Telegram library not available")
            elif not (self.bot_token and self.channel_id):
                logger.warning("Telegram bot token or channel ID not configured")
    
    def check_file_exists_sync(self, video_id: str, stream_type: str) -> Optional[str]:
        """Check if file exists in Telegram channel (sync version for Flask)"""
        try:
            if not self.bot or telegram_files_collection_sync is None:
                return None
                
            # Search in MongoDB for existing Telegram file using sync client
            file_doc = telegram_files_collection_sync.find_one({
                "video_id": video_id,
                "stream_type": stream_type
            })
            
            if file_doc:
                telegram_file = TelegramFile.from_dict(file_doc)
                logger.info(f"Found Telegram file for {video_id} ({stream_type}): {telegram_file.file_id}")
                
                # For Telegram files uploaded to channel, we need to get the file info first
                # But since we can't make async calls here, let's use a different approach
                # We'll create a direct link to the Telegram file using file_id
                try:
                    # Create a download link that will be handled by Telegram's getFile API
                    # This approach uses the file_id to create a streamable URL
                    telegram_url = f"https://api.telegram.org/bot{self.bot_token}/getFile?file_id={telegram_file.file_id}"
                    logger.info(f"Generated Telegram download URL for {video_id} ({stream_type})")
                    return telegram_url
                except Exception as e:
                    logger.error(f"Error generating Telegram URL: {e}")
                    return None
            
            logger.info(f"No Telegram file found for {video_id} ({stream_type})")
            return None
        except Exception as e:
            logger.error(f"Error checking Telegram file (sync): {e}")
            return None
    
    async def check_file_exists(self, video_id: str, stream_type: str) -> Optional[str]:
        """Check if file exists in Telegram channel"""
        try:
            if not self.bot:
                return None
                
            # Search in MongoDB for existing Telegram file
            file_doc = await telegram_files_collection.find_one({
                "video_id": video_id,
                "stream_type": stream_type
            })
            
            if file_doc:
                telegram_file = TelegramFile.from_dict(file_doc)
                # Verify file still exists in Telegram
                try:
                    if stream_type == "video":
                        file_info = await self.bot.get_file(telegram_file.file_id)
                    else:
                        file_info = await self.bot.get_file(telegram_file.file_id)
                    
                    if file_info:
                        return f"https://api.telegram.org/file/bot{self.bot_token}/{file_info.file_path}"
                except TelegramError:
                    # File no longer exists, remove from database
                    await telegram_files_collection.delete_one({"_id": file_doc["_id"]})
                    return None
            
            return None
        except Exception as e:
            logger.error(f"Error checking Telegram file: {e}")
            return None
    
    async def upload_file_background(self, video_id: str, stream_type: str, 
                                   file_url: str, title: str) -> None:
        """Upload file to Telegram channel in background"""
        try:
            if not self.bot:
                logger.warning("Telegram bot not configured, skipping upload")
                return
            
            # Check if already exists
            existing = await self.check_file_exists(video_id, stream_type)
            if existing:
                return
            
            # Download file and upload to Telegram
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.get(file_url)
                if response.status_code == 200:
                    file_data = response.content
                    
                    # Determine file extension
                    extension = "mp4" if stream_type == "video" else "mp3"
                    filename = f"{title[:50]}_{video_id}.{extension}"
                    
                    if stream_type == "video":
                        message = await self.bot.send_video(
                            chat_id=self.channel_id,
                            video=file_data,
                            filename=filename,
                            caption=f"{title}\nID: {video_id}"
                        )
                        file_id = message.video.file_id
                        file_unique_id = message.video.file_unique_id
                        file_size = message.video.file_size
                    else:
                        message = await self.bot.send_audio(
                            chat_id=self.channel_id,
                            audio=file_data,
                            filename=filename,
                            title=title,
                            caption=f"ID: {video_id}"
                        )
                        file_id = message.audio.file_id
                        file_unique_id = message.audio.file_unique_id
                        file_size = message.audio.file_size
                    
                    # Save to MongoDB
                    telegram_file = TelegramFile(
                        video_id=video_id,
                        stream_type=stream_type,
                        file_id=file_id,
                        file_unique_id=file_unique_id,
                        file_size=file_size
                    )
                    telegram_file.message_id = message.message_id
                    
                    await telegram_files_collection.insert_one(telegram_file.to_dict())
                    logger.info(f"Successfully uploaded {stream_type} for {video_id} to Telegram")
                
        except Exception as e:
            logger.error(f"Error uploading to Telegram: {e}")
    
    def schedule_background_upload(self, video_id: str, stream_type: str, 
                                 file_url: str, title: str) -> None:
        """Schedule background upload task"""
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(
                self.upload_file_background(video_id, stream_type, file_url, title)
            )
        except RuntimeError:
            # No event loop running, create new one for background task
            asyncio.create_task(
                self.upload_file_background(video_id, stream_type, file_url, title)
            )

# Global instance
telegram_service = TelegramService()
