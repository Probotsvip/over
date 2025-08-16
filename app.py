import os
import logging
import asyncio
import secrets
import uuid
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Any, Optional

from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

from config import *
from mongo import api_keys_collection_sync, logs_collection_sync, videos_collection
from models import APIKey, APILog
from youtube_service_simple import youtube_service

# Configure logging
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", SECRET_KEY)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Enable CORS
CORS(app)

# Initialize rate limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[DEFAULT_RATE_LIMIT],
    storage_uri="memory://",
    strategy="fixed-window",
)

# In-memory fallback for API keys when MongoDB is not available
fallback_api_keys = {}

# Initialize default API keys
def init_default_keys():
    """Initialize default API keys in MongoDB or fallback storage"""
    try:
        if api_keys_collection_sync is not None:
            # MongoDB is available
            # Check if admin key exists
            admin_exists = api_keys_collection_sync.find_one({"key": DEFAULT_ADMIN_KEY})
            if not admin_exists:
                admin_key = APIKey(
                    key=DEFAULT_ADMIN_KEY,
                    name="Admin Key",
                    is_admin=True,
                    daily_limit=10000
                )
                api_keys_collection_sync.insert_one(admin_key.to_dict())
                logger.info("Created admin API key in MongoDB")
            
            # Check if API request key exists
            api_exists = api_keys_collection_sync.find_one({"key": DEFAULT_API_KEY})
            if not api_exists:
                api_key = APIKey(
                    key=DEFAULT_API_KEY,
                    name="API Request Key",
                    daily_limit=5000,
                    created_by=DEFAULT_ADMIN_KEY
                )
                api_keys_collection_sync.insert_one(api_key.to_dict())
                logger.info("Created API request key in MongoDB")
        else:
            # Fallback to in-memory storage
            logger.warning("MongoDB not available, using in-memory API key storage")
            fallback_api_keys[DEFAULT_ADMIN_KEY] = APIKey(
                key=DEFAULT_ADMIN_KEY,
                name="Admin Key",
                is_admin=True,
                daily_limit=10000
            )
            fallback_api_keys[DEFAULT_API_KEY] = APIKey(
                key=DEFAULT_API_KEY,
                name="API Request Key",
                daily_limit=5000,
                created_by=DEFAULT_ADMIN_KEY
            )
            logger.info("Created fallback API keys in memory")
            
    except Exception as e:
        logger.error(f"Error initializing default keys: {e}")

# Initialize default keys
init_default_keys()

def validate_api_key(api_key: str) -> Optional[APIKey]:
    """Validate API key and return APIKey object if valid"""
    try:
        if api_keys_collection_sync is not None:
            # Use MongoDB
            key_doc = api_keys_collection_sync.find_one({"key": api_key})
            if not key_doc:
                return None
            
            api_key_obj = APIKey.from_dict(key_doc)
            
            # Check if expired
            if api_key_obj.is_expired():
                return None
            
            # Check rate limits
            if api_key_obj.remaining_requests() <= 0:
                return None
            
            # Reset count if needed
            if datetime.now() > api_key_obj.reset_at:
                api_key_obj.count = 0
                api_key_obj.reset_at = datetime.now() + timedelta(days=1)
                api_keys_collection_sync.update_one(
                    {"key": api_key},
                    {"$set": {"count": 0, "reset_at": api_key_obj.reset_at}}
                )
            
            return api_key_obj
        else:
            # Use fallback storage
            if api_key not in fallback_api_keys:
                return None
            
            api_key_obj = fallback_api_keys[api_key]
            
            # Check if expired
            if api_key_obj.is_expired():
                return None
            
            # Check rate limits
            if api_key_obj.remaining_requests() <= 0:
                return None
            
            # Reset count if needed
            if datetime.now() > api_key_obj.reset_at:
                api_key_obj.count = 0
                api_key_obj.reset_at = datetime.now() + timedelta(days=1)
            
            return api_key_obj
            
    except Exception as e:
        logger.error(f"Error validating API key: {e}")
        return None

def require_api_key(f):
    """Decorator to require valid API key"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.args.get('api_key') or request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({"error": "API key required"}), 401
        
        api_key_obj = validate_api_key(api_key)
        if not api_key_obj:
            return jsonify({"error": "Invalid or expired API key"}), 401
        
        # Increment usage count
        if api_keys_collection_sync is not None:
            api_keys_collection_sync.update_one(
                {"key": api_key},
                {"$inc": {"count": 1}}
            )
        else:
            # Update fallback storage
            if api_key in fallback_api_keys:
                fallback_api_keys[api_key].count += 1
        
        # Log API usage
        if logs_collection_sync is not None:
            log_entry = APILog(
                api_key=api_key,
                endpoint=request.endpoint or '',
                query=request.args.get('query', ''),
                ip_address=get_remote_address(),
                response_status=200
            )
            logs_collection_sync.insert_one(log_entry.to_dict())
        
        # Store API key in request context
        setattr(request, 'api_key', api_key_obj)
        return f(*args, **kwargs)
    
    return decorated_function

def require_admin_key(f):
    """Decorator to require admin API key"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.args.get('admin_key') or request.headers.get('X-Admin-Key')
        
        if not api_key:
            return jsonify({"error": "Admin key required"}), 401
        
        api_key_obj = validate_api_key(api_key)
        if not api_key_obj or not api_key_obj.is_admin:
            return jsonify({"error": "Invalid admin key"}), 401
        
        # Store admin key in request context
        setattr(request, 'admin_key', api_key_obj)
        return f(*args, **kwargs)
    
    return decorated_function

@app.route('/')
def index():
    """Home page with API documentation"""
    return render_template('index.html')

@app.route('/youtube')
@require_api_key
@limiter.limit(API_RATE_LIMIT)
def youtube_endpoint():
    """Main YouTube API endpoint"""
    try:
        query = request.args.get('query')
        video = request.args.get('video', 'false').lower() == 'true'
        
        if not query:
            return jsonify({"error": "Query parameter is required"}), 400
        
        # Parse video ID from URL or use directly
        video_id = youtube_service.parse_video_id(query)
        if not video_id:
            return jsonify({"error": "Invalid YouTube URL or video ID"}), 400
        
        # Get video information
        stream_type = "video" if video else "audio"
        result = youtube_service.get_video_info(video_id, stream_type)
        
        if not result:
            return jsonify({"error": "Video not found or unavailable"}), 404
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in youtube endpoint: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/ytmp4')
@limiter.limit(API_RATE_LIMIT)
def ytmp4_endpoint():
    """YouTube MP4 video download endpoint"""
    try:
        url = request.args.get('url')
        key = request.args.get('key')
        
        if not url:
            return jsonify({"error": "URL parameter is required"}), 400
        
        if not key:
            return jsonify({"error": "API key required"}), 401
        
        # Validate API key
        api_key_obj = validate_api_key(key)
        if not api_key_obj:
            return jsonify({"error": "Invalid or expired API key"}), 401
        
        # Increment usage count
        if api_keys_collection_sync is not None:
            api_keys_collection_sync.update_one(
                {"key": key},
                {"$inc": {"count": 1}}
            )
        else:
            if key in fallback_api_keys:
                fallback_api_keys[key].count += 1
        
        # Log API usage
        if logs_collection_sync is not None:
            log_entry = APILog(
                api_key=key,
                endpoint="ytmp4_endpoint",
                query=url,
                ip_address=get_remote_address(),
                response_status=200
            )
            logs_collection_sync.insert_one(log_entry.to_dict())
        
        # Parse video ID from URL
        video_id = youtube_service.parse_video_id(url)
        if not video_id:
            return jsonify({"error": "Invalid YouTube URL"}), 400
        
        # Get video information
        result = youtube_service.get_video_info(video_id, "video")
        
        if not result:
            return jsonify({"error": "Video not found or unavailable"}), 404
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in ytmp4 endpoint: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/ytmp3')
@limiter.limit(API_RATE_LIMIT)
def ytmp3_endpoint():
    """YouTube MP3 audio download endpoint"""
    try:
        url = request.args.get('url')
        key = request.args.get('key')
        
        if not url:
            return jsonify({"error": "URL parameter is required"}), 400
        
        if not key:
            return jsonify({"error": "API key required"}), 401
        
        # Validate API key
        api_key_obj = validate_api_key(key)
        if not api_key_obj:
            return jsonify({"error": "Invalid or expired API key"}), 401
        
        # Increment usage count
        if api_keys_collection_sync is not None:
            api_keys_collection_sync.update_one(
                {"key": key},
                {"$inc": {"count": 1}}
            )
        else:
            if key in fallback_api_keys:
                fallback_api_keys[key].count += 1
        
        # Log API usage
        if logs_collection_sync is not None:
            log_entry = APILog(
                api_key=key,
                endpoint="ytmp3_endpoint",
                query=url,
                ip_address=get_remote_address(),
                response_status=200
            )
            logs_collection_sync.insert_one(log_entry.to_dict())
        
        # Parse video ID from URL
        video_id = youtube_service.parse_video_id(url)
        if not video_id:
            return jsonify({"error": "Invalid YouTube URL"}), 400
        
        # Get audio information
        result = youtube_service.get_video_info(video_id, "audio")
        
        if not result:
            return jsonify({"error": "Audio not found or unavailable"}), 404
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in ytmp3 endpoint: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/stream/<stream_id>')
def stream_endpoint(stream_id):
    """Stream endpoint for media delivery"""
    try:
        # This would be implemented based on your streaming requirements
        # For now, return a placeholder
        return jsonify({"error": "Stream endpoint not implemented"}), 501
        
    except Exception as e:
        logger.error(f"Error in stream endpoint: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/admin')
def admin_panel():
    """Admin panel for API key management"""
    admin_key = request.args.get('admin_key')
    if not admin_key:
        return "Access denied. Valid admin key required.", 403
    
    api_key_obj = validate_api_key(admin_key)
    if not api_key_obj or not api_key_obj.is_admin:
        return "Access denied. Valid admin key required.", 403
    
    return render_template('admin.html', admin_key=admin_key)

@app.route('/api/admin/keys')
@require_admin_key
def get_api_keys():
    """Get all API keys (admin only)"""
    try:
        if api_keys_collection_sync is not None:
            keys = list(api_keys_collection_sync.find({}, {"_id": 0}))
        else:
            keys = [key.to_dict() for key in fallback_api_keys.values()]
        return jsonify(keys)
    except Exception as e:
        logger.error(f"Error getting API keys: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/admin/keys', methods=['POST'])
@require_admin_key
def create_api_key():
    """Create new API key (admin only)"""
    try:
        data = request.get_json()
        name = data.get('name')
        daily_limit = data.get('daily_limit', 100)
        
        if not name:
            return jsonify({"error": "Name is required"}), 400
        
        # Generate new API key
        new_key = secrets.token_hex(32)
        
        api_key = APIKey(
            key=new_key,
            name=name,
            daily_limit=daily_limit,
            created_by=getattr(request, 'admin_key').key
        )
        
        if api_keys_collection_sync is not None:
            api_keys_collection_sync.insert_one(api_key.to_dict())
        else:
            fallback_api_keys[new_key] = api_key
        
        return jsonify({"key": new_key, "name": name, "daily_limit": daily_limit})
        
    except Exception as e:
        logger.error(f"Error creating API key: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/admin/keys/<key_id>', methods=['DELETE'])
@require_admin_key
def delete_api_key(key_id):
    """Delete API key (admin only)"""
    try:
        if api_keys_collection_sync is not None:
            result = api_keys_collection_sync.delete_one({"key": key_id})
            if result.deleted_count > 0:
                return jsonify({"message": "API key deleted successfully"})
            else:
                return jsonify({"error": "API key not found"}), 404
        else:
            if key_id in fallback_api_keys:
                del fallback_api_keys[key_id]
                return jsonify({"message": "API key deleted successfully"})
            else:
                return jsonify({"error": "API key not found"}), 404
    except Exception as e:
        logger.error(f"Error deleting API key: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/admin/stats')
@require_admin_key
def get_stats():
    """Get API usage statistics (admin only)"""
    try:
        if api_keys_collection_sync is not None and logs_collection_sync is not None:
            total_keys = api_keys_collection_sync.count_documents({})
            total_requests = logs_collection_sync.count_documents({})
            
            # Get recent logs
            recent_logs = list(logs_collection_sync.find({}, {"_id": 0}).sort("timestamp", -1).limit(10))
        else:
            total_keys = len(fallback_api_keys)
            total_requests = sum(key.count for key in fallback_api_keys.values())
            recent_logs = []  # No logging in fallback mode
        
        return jsonify({
            "total_keys": total_keys,
            "total_requests": total_requests,
            "recent_logs": recent_logs
        })
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "version": API_VERSION,
        "timestamp": datetime.now().isoformat()
    })

@app.errorhandler(429)
def ratelimit_handler(e):
    """Rate limit error handler"""
    return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429

@app.errorhandler(500)
def internal_error(e):
    """Internal error handler"""
    logger.error(f"Internal server error: {e}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
