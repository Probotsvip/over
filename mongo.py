import logging
from config import MONGO_DB_URI

logger = logging.getLogger(__name__)

# Initialize MongoDB connections
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

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo import MongoClient
    
    logger.info("Connecting to MongoDB...")
    
    # Async client for async operations
    _mongo_async_ = AsyncIOMotorClient(MONGO_DB_URI)
    mongodb_async = _mongo_async_.youtube_api
    
    # Sync client for sync operations
    _mongo_sync_ = MongoClient(MONGO_DB_URI)
    mongodb_sync = _mongo_sync_.youtube_api
    
    # Collections
    videos_collection = mongodb_async.videos
    api_keys_collection = mongodb_async.api_keys
    logs_collection = mongodb_async.logs
    telegram_files_collection = mongodb_async.telegram_files
    
    # Sync collections for synchronous operations
    videos_collection_sync = mongodb_sync.videos
    api_keys_collection_sync = mongodb_sync.api_keys
    logs_collection_sync = mongodb_sync.logs
    telegram_files_collection_sync = mongodb_sync.telegram_files
    
    logger.info("Connected to MongoDB successfully.")
    
except ImportError as e:
    logger.error(f"MongoDB packages not available: {e}")
    logger.warning("Running without MongoDB - API will use external services only")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    logger.warning("Running without MongoDB - API will use external services only")
