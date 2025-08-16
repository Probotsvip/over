import logging
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_DB_URI

logger = logging.getLogger(__name__)

logger.info("Connecting to your Mongo Database...")
try:
    _mongo_async_ = AsyncIOMotorClient(MONGO_DB_URI)
    mongodb = _mongo_async_.youtube_api
    
    # Collections for the YouTube API
    videos_collection = mongodb.videos
    api_keys_collection = mongodb.api_keys
    logs_collection = mongodb.logs
    telegram_files_collection = mongodb.telegram_files
    
    # For compatibility with sync operations (using motor)
    mongodb_async = mongodb
    videos_collection_sync = None  # Will be handled by async only
    api_keys_collection_sync = None  # Will be handled by async only
    logs_collection_sync = None  # Will be handled by async only
    telegram_files_collection_sync = None  # Will be handled by async only
    
    logger.info("Connected to your Mongo Database.")
except Exception as e:
    logger.error(f"Failed to connect to your Mongo Database: {e}")
    # Initialize as None for fallback handling
    mongodb = None
    videos_collection = None
    api_keys_collection = None
    logs_collection = None
    telegram_files_collection = None
    mongodb_async = None
    videos_collection_sync = None
    api_keys_collection_sync = None
    logs_collection_sync = None
    telegram_files_collection_sync = None