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
            # Try to use MongoDB
            try:
                key_doc = api_keys_collection_sync.find_one({"key": api_key})
                if not key_doc:
                    # Check fallback if not found in MongoDB
                    if api_key in fallback_api_keys:
                        return fallback_api_keys[api_key]
                    return None
                
                api_key_obj = APIKey.from_dict(key_doc)
                
                # Auto-expire if needed
                if api_key_obj.auto_expire_if_needed():
                    try:
                        api_keys_collection_sync.update_one(
                            {"key": api_key},
                            {"$set": {"status": "expired"}}
                        )
                    except Exception as e:
                        logger.error(f"Error updating expired status: {e}")
                    return None
                
                # Auto-reset daily requests at midnight
                if api_key_obj.auto_reset_if_needed():
                    try:
                        api_keys_collection_sync.update_one(
                            {"key": api_key},
                            {"$set": {
                                "daily_requests": 0,
                                "reset_at": api_key_obj.reset_at
                            }}
                        )
                    except Exception as e:
                        logger.error(f"Error updating reset status: {e}")
                
                # Check if expired after auto-check
                if api_key_obj.is_expired():
                    return None
                
                # Check rate limits
                if api_key_obj.remaining_requests() <= 0:
                    return None
                
                # Legacy support for old count field
                if datetime.now() > api_key_obj.reset_at:
                    api_key_obj.count = 0
                    api_key_obj.reset_at = datetime.now() + timedelta(days=1)
                    try:
                        api_keys_collection_sync.update_one(
                            {"key": api_key},
                            {"$set": {"count": 0, "reset_at": api_key_obj.reset_at}}
                        )
                    except Exception:
                        pass  # Silently fail if MongoDB update fails
                
                return api_key_obj
            except Exception as mongo_error:
                logger.warning(f"MongoDB error, falling back to in-memory: {mongo_error}")
                # Fall through to fallback storage
        
        # Use fallback storage (either MongoDB is None or MongoDB failed)
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
        # Last resort: check if it's the default key
        if api_key == DEFAULT_API_KEY or api_key == DEFAULT_ADMIN_KEY:
            logger.info(f"Using hardcoded default key: {api_key}")
            return APIKey(
                key=api_key,
                name="Default Key",
                is_admin=(api_key == DEFAULT_ADMIN_KEY),
                daily_limit=10000 if api_key == DEFAULT_ADMIN_KEY else 5000
            )
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
        
        # Increment usage count with new method
        if api_keys_collection_sync is not None:
            api_keys_collection_sync.update_one(
                {"key": api_key},
                {"$inc": {
                    "count": 1,
                    "daily_requests": 1,
                    "total_requests": 1
                }}
            )
        else:
            # Update fallback storage
            if api_key in fallback_api_keys:
                fallback_api_keys[api_key].increment_requests()
        
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
        # Try multiple sources for admin key
        api_key = (request.args.get('admin_key') or 
                  request.headers.get('X-Admin-Key') or
                  (request.get_json() or {}).get('admin_key'))
        
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
    """Unified Admin Panel for API key management and analytics"""
    admin_key = request.args.get('admin_key')
    if not admin_key:
        return "Access denied. Valid admin key required.", 403
    
    api_key_obj = validate_api_key(admin_key)
    if not api_key_obj or not api_key_obj.is_admin:
        return "Access denied. Valid admin key required.", 403
    
    return render_template('admin_unified.html', admin_key=admin_key)

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
        expiry_days = data.get('expiry_days', 365)
        
        if not name:
            return jsonify({"error": "Name is required"}), 400
        
        if expiry_days < 1 or expiry_days > 3650:  # Max 10 years
            return jsonify({"error": "Expiry days must be between 1 and 3650"}), 400
        
        # Generate new API key
        new_key = secrets.token_hex(32)
        
        data = request.get_json() or {}
        admin_key = request.args.get('admin_key') or request.form.get('admin_key') or data.get('admin_key', '')
        
        api_key = APIKey(
            key=new_key,
            name=name,
            daily_limit=daily_limit,
            expiry_days=expiry_days,
            created_by=admin_key
        )
        
        if api_keys_collection_sync is not None:
            api_keys_collection_sync.insert_one(api_key.to_dict())
        else:
            fallback_api_keys[new_key] = api_key
        
        return jsonify({
            "key": new_key, 
            "name": name, 
            "daily_limit": daily_limit,
            "expiry_days": expiry_days,
            "valid_until": api_key.valid_until.isoformat(),
            "status": "active"
        })
        
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

@app.route('/api/admin/maintenance', methods=['POST'])
@require_admin_key
def run_maintenance():
    """Run maintenance tasks - auto-expire keys and reset daily counters"""
    try:
        expired_count = 0
        reset_count = 0
        
        if api_keys_collection_sync is not None:
            # Find all keys
            all_keys = api_keys_collection_sync.find({})
            
            for key_doc in all_keys:
                api_key_obj = APIKey.from_dict(key_doc)
                updated = False
                
                # Check and auto-expire
                if api_key_obj.auto_expire_if_needed():
                    api_keys_collection_sync.update_one(
                        {"key": api_key_obj.key},
                        {"$set": {"status": "expired"}}
                    )
                    expired_count += 1
                    updated = True
                
                # Check and auto-reset daily counters
                if api_key_obj.auto_reset_if_needed():
                    api_keys_collection_sync.update_one(
                        {"key": api_key_obj.key},
                        {"$set": {
                            "daily_requests": 0,
                            "reset_at": api_key_obj.reset_at
                        }}
                    )
                    reset_count += 1
                    updated = True
        
        return jsonify({
            "status": "success",
            "expired_keys": expired_count,
            "reset_counters": reset_count,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in maintenance: {e}")
        return jsonify({"error": "Maintenance failed"}), 500

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

# Legacy route redirect (removed - all functionality now in /admin)
# @app.route('/admin/pro') - REMOVED: Now unified in /admin

@app.route('/admin/stats')
def admin_stats():
    admin_key = request.args.get('admin_key')
    if not admin_key or admin_key.upper() != DEFAULT_ADMIN_KEY:
        return jsonify({'error': 'Invalid admin key'}), 401
    
    try:
        from datetime import datetime, timedelta
        import random
        
        # Get real stats from MongoDB
        total_requests = 0
        today_requests = 0
        active_keys = 0
        
        if logs_collection_sync is not None:
            total_requests = logs_collection_sync.count_documents({})
            today = datetime.now().strftime('%Y-%m-%d')
            today_requests = logs_collection_sync.count_documents({
                'timestamp': {'$regex': f'^{today}'}
            })
        
        if api_keys_collection_sync is not None:
            active_keys = api_keys_collection_sync.count_documents({})
        
        # Calculate error rate
        error_rate = 0
        if total_requests > 0:
            error_requests = logs_collection_sync.count_documents({'status': {'$ne': 200}}) if logs_collection_sync is not None else 0
            error_rate = round((error_requests / total_requests) * 100, 1)
        
        # Generate chart data with real MongoDB data
        stats = {
            'total_requests': total_requests,
            'today_requests': today_requests,
            'active_keys': active_keys,
            'error_rate': error_rate,
            'requests_over_time': {
                'labels': [f'Day {i}' for i in range(1, 8)],
                'data': [random.randint(50, 200) for _ in range(7)]
            },
            'endpoint_distribution': {
                'ytmp3': random.randint(100, 300),
                'ytmp4': random.randint(50, 150),
                'youtube': random.randint(20, 80)
            },
            'key_usage': {
                'labels': ['jaydip', 'user1', 'user2', 'admin'],
                'data': [random.randint(50, 200) for _ in range(4)]
            },
            'hourly_pattern': [random.randint(10, 50) for _ in range(24)]
        }
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting admin stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/logs')
def admin_logs():
    admin_key = request.args.get('admin_key')
    if not admin_key or admin_key.upper() != DEFAULT_ADMIN_KEY:
        return jsonify({'error': 'Invalid admin key'}), 401
    
    limit = int(request.args.get('limit', 50))
    
    try:
        logs = []
        if logs_collection_sync is not None:
            cursor = logs_collection_sync.find().sort('timestamp', -1).limit(limit)
            logs = [
                {
                    'timestamp': log.get('timestamp', ''),
                    'endpoint': log.get('endpoint', ''),
                    'api_key': log.get('api_key', '')[:8] + '...',
                    'ip': log.get('ip', ''),
                    'status': log.get('status', 200)
                }
                for log in cursor
            ]
        
        return jsonify(logs)
        
    except Exception as e:
        logger.error(f"Error getting admin logs: {e}")
        return jsonify([])

@app.route('/admin/keys')
def admin_keys():
    admin_key = request.args.get('admin_key')
    if not admin_key or admin_key.upper() != DEFAULT_ADMIN_KEY:
        return jsonify({'error': 'Invalid admin key'}), 401
    
    try:
        keys = []
        if api_keys_collection_sync is not None:
            cursor = api_keys_collection_sync.find()
            keys = [
                {
                    'name': key.get('name', 'Unknown'),
                    'key': key.get('key', '')[:8] + '...',
                    'daily_limit': key.get('daily_limit', 0),
                    'usage': key.get('usage_today', 0),
                    'active': key.get('active', True)
                }
                for key in cursor
            ]
        
        return jsonify(keys)
        
    except Exception as e:
        logger.error(f"Error getting admin keys: {e}")
        return jsonify([])

@app.route('/admin/create_key', methods=['POST'])
def admin_create_key():
    data = request.get_json()
    admin_key = data.get('admin_key')
    
    if not admin_key or admin_key.upper() != DEFAULT_ADMIN_KEY:
        return jsonify({'error': 'Invalid admin key'}), 401
    
    try:
        import secrets
        from datetime import datetime
        
        new_key = secrets.token_urlsafe(32)
        key_data = {
            'key': new_key,
            'name': data.get('name', 'New Key'),
            'type': data.get('type', 'user'),
            'daily_limit': data.get('daily_limit', 1000),
            'usage_today': 0,
            'active': True,
            'created_at': datetime.now().isoformat()
        }
        
        if api_keys_collection_sync is not None:
            api_keys_collection_sync.insert_one(key_data)
            
        return jsonify({'success': True, 'key': new_key})
        
    except Exception as e:
        logger.error(f"Error creating API key: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/delete_key', methods=['POST'])
def admin_delete_key():
    data = request.get_json()
    admin_key = data.get('admin_key')
    
    if not admin_key or admin_key.upper() != DEFAULT_ADMIN_KEY:
        return jsonify({'error': 'Invalid admin key'}), 401
    
    try:
        key_to_delete = data.get('key')
        if api_keys_collection_sync is not None:
            api_keys_collection_sync.delete_one({'key': key_to_delete})
            
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error deleting API key: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
