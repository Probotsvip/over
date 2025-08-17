#!/usr/bin/env python3
"""
Fix Telegram caching for videos that failed background upload
This script will manually trigger uploads for videos in MongoDB but not in Telegram
"""
import asyncio
import os
import pymongo
from telegram_service import TelegramService
from mongo import videos_collection_sync
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_missing_telegram_files():
    """Find videos in MongoDB but missing from Telegram and upload them"""
    try:
        # Get MongoDB client
        mongo_uri = os.environ.get('MONGO_DB_URI')
        if not mongo_uri:
            print("❌ MongoDB URI not found")
            return
            
        client = pymongo.MongoClient(mongo_uri)
        db = client['youtube_api']
        
        # Initialize Telegram service
        telegram_service = TelegramService()
        if not telegram_service.bot:
            print("❌ Telegram bot not available")
            return
            
        print("🔍 Checking for videos that need Telegram upload...")
        
        # Get all videos from MongoDB
        videos = list(db.videos.find())
        telegram_files = list(db.telegram_files.find())
        
        # Create a set of video_id + stream_type combinations that are already in Telegram
        telegram_cached = {(tf['video_id'], tf['stream_type']) for tf in telegram_files}
        
        # Find videos that need Telegram upload
        needs_upload = []
        for video in videos:
            video_key = (video['video_id'], video['stream_type'])
            if video_key not in telegram_cached and video.get('url'):
                needs_upload.append(video)
                
        print(f"📤 Found {len(needs_upload)} videos needing Telegram upload:")
        
        for video in needs_upload:
            print(f"  - {video['title'][:50]}... ({video['video_id']}, {video['stream_type']})")
            
        # Upload missing files
        for video in needs_upload:
            try:
                print(f"🚀 Uploading {video['title'][:30]}... to Telegram")
                await telegram_service.upload_file_background(
                    video['video_id'],
                    video['stream_type'], 
                    video['url'],
                    video['title']
                )
                print(f"✅ Successfully uploaded {video['video_id']}")
                
                # Small delay between uploads
                await asyncio.sleep(2)
                
            except Exception as e:
                print(f"❌ Failed to upload {video['video_id']}: {e}")
                
        print("🎯 Telegram cache fix completed!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(fix_missing_telegram_files())