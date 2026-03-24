import os
import requests
from dotenv import load_dotenv

load_dotenv()

UPLOADTHING_APP_ID = os.getenv("UPLOADTHING_APP_ID")
UPLOADTHING_SECRET = os.getenv("UPLOADTHING_SECRET")
UPLOADTHING_API_URL = "https://api.uploadthing.com"

# Legacy auth: use secret as the API key
HEADERS = {
    "x-uploadthing-api-key": UPLOADTHING_SECRET,
}


def prepare_upload(filename, file_size, content_type="video/mp4"):
    """
    Prepare an upload by getting a presigned URL from UploadThing.
    
    Args:
        filename: Name of the file to upload
        file_size: Size of the file in bytes
        content_type: MIME type of the file
        
    Returns:
        dict with upload URL and fileKey
    """
    endpoint = f"{UPLOADTHING_API_URL}/v6/prepareUpload"
    
    payload = {
        "filename": filename,
        "fileSize": file_size,
        "contentType": content_type,
    }
    
    response = requests.post(endpoint, json=payload, headers=HEADERS)
    response.raise_for_status()
    
    return response.json()


def upload_file(upload_url, file_path, content_type="video/mp4"):
    """
    Upload a file to UploadThing using the presigned URL.
    
    Args:
        upload_url: The presigned upload URL from prepare_upload
        file_path: Path to the local file
        content_type: MIME type of the file
        
    Returns:
        dict with file key and URL
    """
    with open(file_path, "rb") as f:
        file_data = f.read()
    
    headers = {
        "Content-Type": content_type,
    }
    
    response = requests.post(upload_url, data=file_data, headers=headers)
    response.raise_for_status()
    
    return response.json()


def upload_local_file(file_path, filename=None, content_type="video/mp4"):
    """
    Upload a local file to UploadThing and get its public URL.
    
    Args:
        file_path: Path to the local file
        filename: Optional custom filename (defaults to actual filename)
        content_type: MIME type of the file
        
    Returns:
        dict with fileKey and url
    """
    if filename is None:
        filename = os.path.basename(file_path)
    
    file_size = os.path.getsize(file_path)
    
    # Use uploadFiles endpoint
    endpoint = f"{UPLOADTHING_API_URL}/v6/uploadFiles"
    
    payload = {
        "files": [{
            "name": filename,
            "size": file_size,
            "type": content_type,
        }]
    }
    
    response = requests.post(endpoint, json=payload, headers=HEADERS)
    response.raise_for_status()
    
    data = response.json()
    file_data = data["data"][0]
    
    # Upload the actual file to the S3 URL
    with open(file_path, "rb") as f:
        file_content = f.read()
    
    # Get the fields and url from response
    fields = file_data["fields"]
    upload_url = file_data["url"]
    
    # POST to the S3 URL with the fields and file
    s3_response = requests.post(
        upload_url,
        data=fields,
        files={"file": (filename, file_content, content_type)}
    )
    s3_response.raise_for_status()
    
    # Return the public URL
    return {
        "fileKey": file_data["key"],
        "url": file_data["fileUrl"],
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python uploadthing.py <file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    print(f"Uploading {file_path} to UploadThing...")
    result = upload_local_file(file_path)
    print(f"Uploaded! URL: {result['url']}")
