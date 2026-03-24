import os
import sys
import time
import requests
from dotenv import load_dotenv

# Add parent directory to path for dotenv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

# Import from sibling modules
from src.components.video_logic.api import (
    INSTAGRAM_ACCESS_TOKEN,
    INSTAGRAM_ACCOUNT_ID,
    create_media_container,
    check_container_status,
    publish_container,
    wait_for_container_ready,
)
from .uploadthing import upload_local_file as upload_to_uploadthing


class InstagramUploader:
    """Handles uploading and publishing videos to Instagram."""
    
    def __init__(self, access_token=None, account_id=None):
        self.access_token = access_token or INSTAGRAM_ACCESS_TOKEN
        self.account_id = account_id or INSTAGRAM_ACCOUNT_ID
        
        if not self.access_token or not self.account_id:
            raise ValueError(
                "Missing credentials. Set INSTAGRAM_ACCESS_TOKEN and "
                "INSTAGRAM_ACCOUNT_ID in your .env file."
            )
    
    def upload_video(self, video_path, caption="", media_type="REELS", poll_timeout=300):
        """
        Upload a local video and publish it to Instagram.
        
        Args:
            video_path: Path to the video file on your machine
            caption: Caption for the Instagram post
            media_type: REELS, VIDEO, or STORIES
            poll_timeout: Seconds to wait for video processing
            
        Returns:
            dict with media_id and container_id
        """
        # Step 1: Upload to UploadThing to get a public URL
        print(f"Uploading {video_path} to UploadThing...")
        uploadthing_result = upload_to_uploadthing(video_path)
        video_url = uploadthing_result["url"]
        print(f"UploadThing URL: {video_url}")
        
        # Step 2: Create Instagram container with the public URL
        print(f"Creating Instagram container...")
        container_id = create_media_container(
            video_url=video_url,
            caption=caption,
            media_type=media_type,
        )
        print(f"Container created: {container_id}")
        
        # Step 3: Wait for video processing
        print("Waiting for video processing...")
        if not wait_for_container_ready(container_id, timeout=poll_timeout):
            status = check_container_status(container_id)
            raise Exception(f"Container failed with status: {status.get('status_code')}")
        
        # Step 4: Publish
        print("Video processed. Publishing...")
        media_id = publish_container(container_id)
        print(f"Published! Media ID: {media_id}")
        
        return {
            "media_id": media_id,
            "container_id": container_id,
            "video_url": video_url,
        }
    
    def upload_from_url(self, video_url, caption="", media_type="REELS", poll_timeout=300):
        """
        Upload a video from a public URL and publish to Instagram.
        
        Args:
            video_url: Publicly accessible URL to the video file
            caption: Caption for the Instagram post
            media_type: REELS, VIDEO, or STORIES
            poll_timeout: Seconds to wait for video processing (default 5 min)
            
        Returns:
            dict with media_id and container_id
        """
        print(f"Creating media container for: {video_url}")
        container_id = create_media_container(
            video_url=video_url,
            caption=caption,
            media_type=media_type,
        )
        print(f"Container created: {container_id}")
        
        # Poll until the container is ready
        print("Waiting for video processing...")
        if not wait_for_container_ready(container_id, timeout=poll_timeout):
            status = check_container_status(container_id)
            raise Exception(f"Container failed with status: {status.get('status_code')}")
        
        print("Video processed. Publishing...")
        media_id = publish_container(container_id)
        print(f"Published! Media ID: {media_id}")
        
        return {
            "media_id": media_id,
            "container_id": container_id,
        }
    
    def check_rate_limit(self):
        """Check your current content publishing rate limit."""
        from api import GRAPH_API_URL
        
        endpoint = f"{GRAPH_API_URL}/{self.account_id}/content_publishing_limit"
        params = {
            "access_token": self.access_token,
        }
        
        response = requests.get(endpoint, params=params)
        response.raise_for_status()
        
        return response.json()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Upload video to Instagram")
    parser.add_argument("video_path", help="Path to the video file")
    parser.add_argument("--caption", default="", help="Post caption")
    parser.add_argument("--type", default="REELS", choices=["REELS", "VIDEO", "STORIES"],
                        help="Media type")
    
    args = parser.parse_args()
    
    uploader = InstagramUploader()
    result = uploader.upload_video(
        video_path=args.video_path,
        caption=args.caption,
        media_type=args.type,
    )
    
    print(f"\nSuccess! Posted to Instagram.")
    print(f"Media ID: {result['media_id']}")
    print(f"Video URL: {result['video_url']}")
