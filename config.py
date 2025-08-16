import os

# API Constants
API_VERSION = "1.0.0"
DEFAULT_ADMIN_KEY = "JAYDIP"
DEFAULT_API_KEY = "jaydip"

# Flask Configuration
DEBUG = os.environ.get("DEBUG", "True").lower() == "true"
SECRET_KEY = os.environ.get("SESSION_SECRET", "youtube_api_secure_key_change_in_production")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 5000))

# MongoDB Configuration
MONGO_DB_URI = os.environ.get("MONGO_DB_URI", "mongodb+srv://jaydipmore74:xCpTm5OPAfRKYnif@cluster0.5jo18.mongodb.net/?retryWrites=true&w=majority")

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

# External API Configuration
EXTERNAL_API_BASE = "https://jerrycoder.oggyapi.workers.dev"

# Cache and Rate Limiting
CACHE_TIMEOUT = int(os.environ.get("CACHE_TIMEOUT", 60 * 60))  # 1 hour in seconds
DEFAULT_RATE_LIMIT = os.environ.get("DEFAULT_RATE_LIMIT", "100 per minute")
API_RATE_LIMIT = os.environ.get("API_RATE_LIMIT", "500 per hour")

# Request Settings
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", 30))  # seconds
MAX_CONCURRENT_REQUESTS = int(os.environ.get("MAX_CONCURRENT_REQUESTS", 10))

# Stream Settings
STREAM_CHUNK_SIZE = int(os.environ.get("STREAM_CHUNK_SIZE", 1024 * 1024))  # 1MB
