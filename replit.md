# Overview

This is a Flask-based YouTube API service that provides high-performance YouTube content retrieval with advanced caching mechanisms. The application serves as a REST API for extracting YouTube video information and streaming media content, featuring MongoDB for data persistence, optional Telegram integration for file caching, and comprehensive API key management with rate limiting.

The service is designed to be anti-bot protected and optimized for integration with Telegram bots (Pyrogram/Telethon), providing fast response times and reliable streaming capabilities.

## Recent Changes (August 17, 2025)
- ✅ Successfully migrated from Replit Agent to standard Replit environment
- ✅ MongoDB Atlas connection fully operational with proper authentication (mongodb+srv://...)
- ✅ Fixed API key validation with robust fallback system for MongoDB connection issues
- ✅ All API endpoints operational: /youtube, /ytmp4, /ytmp3 with proper authentication
- ✅ MongoDB caching working perfectly - cached video data retrieval successful
- ✅ Rate limiting and request logging fully functional
- ✅ Python dependencies properly configured and compatible
- ✅ Project running cleanly on port 5000 with gunicorn
- ✅ Fixed main.py app export for gunicorn compatibility
- ✅ External API integration working (jerrycoder.oggyapi.workers.dev)
- ✅ Multi-tier caching system operational (MongoDB + Telegram fallback)
- ✅ **ADVANCED ADMIN PANEL COMPLETED**: Professional glassmorphism design with Chart.js integration
- ✅ Real-time MongoDB Atlas data integration (38 requests, 5 API keys including new test key)
- ✅ All admin endpoints functional: /admin/stats, /admin/logs, /admin/keys, /admin/create_key, /admin/delete_key
- ✅ Interactive charts, live monitoring, auto-refresh, and comprehensive API key management
- ✅ Admin authentication working with JAYDIP key, beautiful gradient UI effects
- ✅ **MOBILE RECHARGE-STYLE API KEY SYSTEM**: Automatic expiry with configurable days (7-3650 days)
- ✅ Enhanced API key lifecycle management with auto-expiry and daily limit reset functionality
- ✅ Updated admin interface with Status & Expiry column showing remaining days
- ✅ Backward compatibility maintained for both basic and unified admin templates
- ✅ API key creation fully operational via backend (tested successfully via API calls)
- ✅ **FIXED ADMIN PANEL API KEY CREATION**: Resolved frontend-backend communication issue
- ✅ Updated require_admin_key decorator to accept admin keys from multiple sources (URL params, headers, JSON body)
- ✅ Admin panel JavaScript now properly sends admin_key in request body for seamless authentication
- ✅ All API key creation, management, and deletion functions working perfectly through web interface
- ✅ **MODERN ADMIN DASHBOARD REDESIGN**: Professional glassmorphism design with enhanced UI/UX
- ✅ Implemented card-based stats layout with gradient icons and hover animations
- ✅ Added service health monitor with pulsing status indicators for real-time system monitoring
- ✅ Enhanced API Usage Analytics with simplified grid layout and real-time data visualization
- ✅ Live activity feed showing recent downloads, API key creations, and system activities
- ✅ Quick action buttons for maintenance, log export, cache clearing with gradient hover effects
- ✅ Fixed API key deletion bug - now properly handles full key IDs instead of truncated versions
- ✅ Migration from Replit Agent to standard Replit environment 100% completed successfully

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Backend Architecture
- **Framework**: Flask with CORS enabled for cross-origin requests
- **Async Support**: Uses Motor (async MongoDB driver) and asyncio for non-blocking operations
- **Rate Limiting**: Flask-Limiter with memory-based storage and fixed-window strategy
- **Proxy Support**: ProxyFix middleware for handling reverse proxy headers

## Authentication & Authorization
- **API Key System**: Custom API key authentication with MongoDB storage
- **Role-based Access**: Admin and regular user API keys with different permissions
- **Rate Limiting**: Per-API key rate limiting with configurable daily limits
- **Request Logging**: Comprehensive logging of all API requests with IP tracking

## Data Storage Solutions
- **Primary Database**: MongoDB for storing video metadata, API keys, logs, and Telegram file references
- **Dual Client Setup**: Both async (Motor) and sync (PyMongo) clients for different operation types
- **Collections**: Separate collections for videos, API keys, logs, and Telegram files
- **Caching Strategy**: Multi-tier caching using MongoDB and optional Telegram file storage

## Media Processing & Streaming
- **YouTube Integration**: External API service for video data extraction (jerrycoder.oggyapi.workers.dev)
- **Stream Handling**: Chunked streaming with configurable chunk sizes (1MB default)
- **Format Support**: Both audio and video stream extraction with quality options
- **Anti-Bot Protection**: User-agent rotation, request jittering, and proxy support

## Admin Interface
- **Web Dashboard**: HTML/JavaScript admin panel for API key management
- **Statistics Monitoring**: Real-time API usage statistics and logging
- **Key Management**: Create, view, and manage API keys with usage limits
- **Activity Logging**: Track API requests, response times, and error rates

## Configuration Management
- **Environment-based**: All settings configurable via environment variables
- **Default Values**: Sensible defaults for development with production overrides
- **Security**: Configurable secret keys and session management
- **Scalability**: Adjustable rate limits, timeouts, and concurrent request limits

# External Dependencies

## Third-party Services
- **YouTube Data Source**: jerrycoder.oggyapi.workers.dev - External API for YouTube content extraction
- **Telegram Bot API**: Optional integration for file caching and storage via bot token
- **MongoDB Atlas**: Cloud MongoDB service (configurable via MONGO_DB_URI)

## Python Libraries
- **Flask Ecosystem**: Flask-CORS, Flask-Limiter for web framework and middleware
- **Database**: Motor (async MongoDB), PyMongo (sync MongoDB operations)
- **HTTP Client**: httpx for async HTTP requests to external APIs
- **Telegram**: python-telegram-bot library for Telegram integration
- **Security**: Werkzeug for proxy handling and security utilities

## Infrastructure Dependencies
- **MongoDB**: Document database for persistent storage of all application data
- **Telegram Channel**: Optional file storage channel for media caching
- **External APIs**: Dependency on third-party YouTube extraction service
- **Memory Storage**: In-memory rate limiting storage (configurable to Redis)