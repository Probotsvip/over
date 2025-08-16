import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from config import MONGO_DB_URI

logger = logging.getLogger(__name__)

logger.info("Connecting to your Mongo Database...")
try:
    # Async client (Motor)
    _mongo_async_ = AsyncIOMotorClient(MONGO_DB_URI)
    mongodb_async = _mongo_async_.youtube_api
    
    # Sync client (PyMongo)  
    _mongo_sync_ = MongoClient(MONGO_DB_URI)
    mongodb_sync = _mongo_sync_.youtube_api
    
    # Async collections
    videos_collection = mongodb_async.videos
    api_keys_collection = mongodb_async.api_keys
    logs_collection = mongodb_async.logs
    telegram_files_collection = mongodb_async.telegram_files
    
    # Sync collections for Flask app
    videos_collection_sync = mongodb_sync.videos
    api_keys_collection_sync = mongodb_sync.api_keys
    logs_collection_sync = mongodb_sync.logs
    telegram_files_collection_sync = mongodb_sync.telegram_files
    
    # Legacy compatibility
    mongodb = mongodb_async
    
    logger.info("Connected to your Mongo Database (both sync and async).")
except Exception as e:
    logger.error(f"Failed to connect to your Mongo Database: {e}")
    # Initialize as None for fallback handling
    mongodb = None
    mongodb_async = None
    mongodb_sync = None
    videos_collection = None
    api_keys_collection = None
    logs_collection = None
    telegram_files_collection = None
    videos_collection_sync = None
    api_keys_collection_sync = None
    logs_collection_sync = None
    telegram_files_collection_sync = None