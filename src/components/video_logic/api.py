import os
import requests
from dotenv import load_dotenv

load_dotenv()

INSTAGRAM_APP_ID = os.getenv("INSTAGRAM_APP_ID")
INSTAGRAM_APP_SECRET = os.getenv("INSTAGRAM_APP_SECRET")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")

GRAPH_API_URL = "https://graph.instagram.com/v25.0"
RUPLOAD_URL = "https://rupload.facebook.com/ig-api-upload"


def get_headers():
    return {
        "Authorization": f"Bearer {INSTAGRAM_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def get_upload_headers():
    return {
        "Authorization": f"OAuth {INSTAGRAM_ACCESS_TOKEN}",
        "offset": "0",
        "file_size": "",
    }


def create_media_container(video_url, caption="", media_type="REELS"):
    """
    Create a media container for the video.
    
    Args:
        video_url: Publicly accessible URL of the video
        caption: Caption for the post
        media_type: REELS, VIDEO, or STORIES
    
    Returns:
        container_id: str
    """
    endpoint = f"{GRAPH_API_URL}/{INSTAGRAM_ACCOUNT_ID}/media"
    
    payload = {
        "media_type": media_type,
        "video_url": video_url,
        "caption": caption,
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    }
    
    response = requests.post(endpoint, json=payload, headers=get_headers())
    response.raise_for_status()
    
    data = response.json()
    return data.get("id")


def create_resumable_container(caption="", media_type="REELS"):
    """
    Create a media container for resumable upload (local files).
    
    Args:
        caption: Caption for the post
        media_type: REELS, VIDEO, or STORIES
    
    Returns:
        container_id: str
    """
    endpoint = f"{GRAPH_API_URL}/{INSTAGRAM_ACCOUNT_ID}/media"
    
    payload = {
        "media_type": media_type,
        "caption": caption,
        "upload_type": "resumable",
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    }
    
    response = requests.post(endpoint, json=payload, headers=get_headers())
    response.raise_for_status()
    
    data = response.json()
    return data.get("id")


def upload_video_local(container_id, file_path):
    """
    Upload a local video file using resumable upload.
    
    Args:
        container_id: The media container ID from create_resumable_container
        file_path: Path to the local video file
        
    Returns:
        dict with success status
    """
    file_size = os.path.getsize(file_path)
    
    headers = {
        "Authorization": f"OAuth {INSTAGRAM_ACCESS_TOKEN}",
        "offset": "0",
        "file_size": str(file_size),
    }
    
    with open(file_path, "rb") as f:
        video_data = f.read()
    
    endpoint = f"{RUPLOAD_URL}/v25.0/{container_id}"
    
    response = requests.post(
        endpoint,
        headers=headers,
        data=video_data,
    )
    response.raise_for_status()
    
    return response.json()


def check_container_status(container_id):
    """
    Check the publishing status of a media container.
    
    Statuses:
        - EXPIRED: Not published within 24 hours
        - ERROR: Failed to complete publishing
        - FINISHED: Ready to publish
        - IN_PROGRESS: Still processing
        - PUBLISHED: Already published
    """
    endpoint = f"{GRAPH_API_URL}/{container_id}"
    params = {
        "fields": "status_code",
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    }
    
    response = requests.get(endpoint, params=params, headers=get_headers())
    response.raise_for_status()
    
    return response.json()


def publish_container(container_id):
    """
    Publish a media container that has status FINISHED.
    
    Args:
        container_id: The container ID to publish
    
    Returns:
        media_id: The Instagram media ID of the published post
    """
    endpoint = f"{GRAPH_API_URL}/{INSTAGRAM_ACCOUNT_ID}/media_publish"
    
    payload = {
        "creation_id": container_id,
        "access_token": INSTAGRAM_ACCESS_TOKEN,
    }
    
    response = requests.post(endpoint, json=payload, headers=get_headers())
    response.raise_for_status()
    
    return response.json().get("id")


def wait_for_container_ready(container_id, timeout=300, interval=10):
    """
    Poll container status until it's FINISHED or times out.
    
    Args:
        container_id: The container to check
        timeout: Max seconds to wait (default 5 min)
        interval: Seconds between checks
    
    Returns:
        True if ready, False if timed out
    """
    import time
    
    elapsed = 0
    while elapsed < timeout:
        status = check_container_status(container_id)
        status_code = status.get("status_code")
        
        if status_code == "FINISHED":
            return True
        elif status_code in ("ERROR", "EXPIRED", "PUBLISHED"):
            return False
        
        time.sleep(interval)
        elapsed += interval
    
    return False


def upload_and_publish(video_path, caption="", media_type="REELS", poll_timeout=300):
    """
    Full workflow for local video file: create container, upload, publish.
    
    Args:
        video_path: Path to the local video file
        caption: Caption for the Instagram post
        media_type: REELS, VIDEO, or STORIES
        poll_timeout: Seconds to wait for container to be ready
    
    Returns:
        media_id: The published Instagram media ID
    """
    # Step 1: Create resumable container
    container_id = create_resumable_container(caption, media_type)
    
    # Step 2: Upload the video file
    upload_result = upload_video_local(container_id, video_path)
    
    # Step 3: Wait for video processing
    if not wait_for_container_ready(container_id, timeout=poll_timeout):
        status = check_container_status(container_id)
        raise Exception(f"Container failed with status: {status.get('status_code')}")
    
    # Step 4: Publish
    media_id = publish_container(container_id)
    
    return media_id


def upload_and_publish_url(video_url, caption="", media_type="REELS", poll_timeout=300):
    """
    Full workflow for publicly hosted video.
    
    Args:
        video_url: Publicly accessible URL of the video
        caption: Caption for the post
        media_type: REELS, VIDEO, or STORIES
        poll_timeout: Seconds to wait for container to be ready (default 300)
    
    Returns:
        media_id: The published Instagram media ID
    """
    # Step 1: Create container
    container_id = create_media_container(video_url, caption, media_type)
    
    # Step 2: Wait for container to be ready (video processing)
    if not wait_for_container_ready(container_id, timeout=poll_timeout):
        status = check_container_status(container_id)
        raise Exception(f"Container failed: {status.get('status_code')}")
    
    # Step 3: Publish
    media_id = publish_container(container_id)
    
    return media_id
