import os
import time
import requests
from abc import ABC, abstractmethod
from pyngrok import ngrok

# YouTube Imports
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

class SocialPublisher(ABC):
    @abstractmethod
    def publish(self, video_path: str, caption: str):
        pass

class YouTubePublisher(SocialPublisher):
    """Handles authenticated uploads to YouTube Shorts"""
    def __init__(self, client_secrets_path="client_secrets.json"):
        self.client_secrets_path = client_secrets_path
        self.scopes = ["https://www.googleapis.com/auth/youtube.upload"]

    def publish(self, video_path: str, caption: str):
        if not os.path.exists(self.client_secrets_path):
            print(f"[-] YouTube Error: {self.client_secrets_path} not found.")
            return False
            
        try:
            print(f"[*] Initializing YouTube OAuth flow for: {video_path}")
            flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_path, self.scopes)
            credentials = flow.run_local_server(port=0)
            youtube = build("youtube", "v3", credentials=credentials)

            request_body = {
                "snippet": {
                    "title": caption[:100], # YouTube title limit
                    "description": f"{caption}\n\n#shorts #ai #fypd",
                    "categoryId": "22" # People & Blogs
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False
                }
            }

            media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
            request = youtube.videos().insert(part="snippet,status", body=request_body, media_body=media)
            
            print("[*] Uploading to YouTube Shorts...")
            response = request.execute()
            print(f"[+] YouTube Success: https://youtu.be/{response['id']}")
            return True
        except Exception as e:
            print(f"[-] YouTube Upload Failed: {e}")
            return False

class InstagramPublisher(SocialPublisher):
    """Handles automated Reels publishing via Facebook Graph API with On-Demand Tunneling"""
    def __init__(self, access_token: str, ig_user_id: str, ngrok_auth_token: str = None):
        self.access_token = access_token
        self.ig_user_id = ig_user_id
        if ngrok_auth_token:
            ngrok.set_auth_token(ngrok_auth_token)

    def publish(self, video_path: str, caption: str):
        tunnel = None
        try:
            # 1. Start On-Demand Tunnel
            print("[*] Opening secure on-demand tunnel for Instagram...")
            tunnel = ngrok.connect(8000)
            public_url = tunnel.public_url
            video_url = f"{public_url}/videos/{os.path.basename(video_path)}"
            
            print(f"[*] Dispatching Reel to Instagram via: {video_url}")

            # 2. Create Media Container
            container_url = f"https://graph.facebook.com/v19.0/{self.ig_user_id}/media"
            payload = {
                'media_type': 'REELS',
                'video_url': video_url,
                'caption': caption,
                'access_token': self.access_token
            }
            res = requests.post(container_url, data=payload).json()
            container_id = res.get('id')
            if not container_id: raise Exception(f"Container error: {res}")

            # 3. Poll for Processing (Wait for IG to fetch from our tunnel)
            # Fix #5: Add a 5-minute timeout so a stalled IG job doesn't hang the worker thread.
            print("[*] Waiting for Instagram to fetch and process video...")
            status_url = f"https://graph.facebook.com/v19.0/{container_id}"
            IG_POLL_TIMEOUT_SECS = 300  # 5 minutes
            deadline = time.monotonic() + IG_POLL_TIMEOUT_SECS
            while True:
                if time.monotonic() > deadline:
                    raise Exception(
                        f"Instagram processing timed out after {IG_POLL_TIMEOUT_SECS}s. "
                        "Container ID: {container_id}"
                    )
                status_res = requests.get(status_url, params={'fields': 'status_code', 'access_token': self.access_token}).json()
                status = status_res.get('status_code')
                if status == 'FINISHED': break
                elif status == 'ERROR': raise Exception(f"IG Processing Error: {status_res}")
                time.sleep(5)

            # 4. Publish
            publish_url = f"https://graph.facebook.com/v19.0/{self.ig_user_id}/media_publish"
            requests.post(publish_url, data={'creation_id': container_id, 'access_token': self.access_token})
            print("[+] Instagram Reel Published Successfully!")
            return True

        except Exception as e:
            print(f"[-] Instagram Error: {e}")
            return False
        finally:
            if tunnel:
                print("[*] Tearing down secure tunnel.")
                ngrok.disconnect(tunnel.public_url)

class TikTokPublisher(SocialPublisher):
    """Handles automated TikTok uploads via Playwright browser automation"""
    def __init__(self, user_data_dir="tiktok_session"):
        self.user_data_dir = user_data_dir

    def publish(self, video_path: str, caption: str):
        from playwright.sync_api import sync_playwright
        
        abs_video_path = os.path.abspath(video_path)
        print(f"[*] Initializing TikTok browser factory for: {abs_video_path}")
        
        try:
            with sync_playwright() as p:
                # Use persistent context to maintain login session
                browser = p.chromium.launch_persistent_context(
                    self.user_data_dir,
                    headless=False, # TikTok often blocks headless uploads
                    args=["--disable-blink-features=AutomationControlled"]
                )
                
                page = browser.new_page()
                page.goto("https://www.tiktok.com/upload?lang=en", wait_until="networkidle")
                
                # Check if logged in (if not, we can't automate the login here safely)
                if "login" in page.url:
                    print("[-] TikTok Error: User not logged in. Please use the 'Login to TikTok' button in the dashboard first.")
                    browser.close()
                    return False

                print("[*] Uploading video file...")
                # Handle file input
                # Note: TikTok uses an iframe for the upload area in some regions
                file_input = page.wait_for_selector('input[type="file"]')
                file_input.set_input_files(abs_video_path)
                
                print("[*] Entering caption and tags...")
                # Wait for upload to complete and caption field to appear
                caption_div = page.wait_for_selector('div[contenteditable="true"]')
                page.wait_for_timeout(2000) # Wait for text to clear
                caption_div.fill(caption + " #shorts #ai #fypd")
                
                print("[*] Finalizing post...")
                # Click Post
                post_btn = page.locator('button:has-text("Post")')
                post_btn.click()
                
                # Wait for success message
                page.wait_for_selector('text="Your video is being uploaded"', timeout=60000)
                print("[+] TikTok Success: Video posted successfully!")
                
                page.wait_for_timeout(5000)
                browser.close()
                return True
                
        except Exception as e:
            print(f"[-] TikTok Automation Failed: {e}")
            return False

class FacebookPublisher(SocialPublisher):
    """Handles automated Reels publishing to Facebook Pages via Graph API with On-Demand Tunneling"""
    def __init__(self, access_token: str, page_id: str, ngrok_auth_token: str = None):
        self.access_token = access_token
        self.page_id = page_id
        if ngrok_auth_token:
            ngrok.set_auth_token(ngrok_auth_token)

    def publish(self, video_path: str, caption: str):
        tunnel = None
        try:
            # 1. Start On-Demand Tunnel
            print("[*] Opening secure on-demand tunnel for Facebook...")
            tunnel = ngrok.connect(8000)
            public_url = tunnel.public_url
            video_url = f"{public_url}/videos/{os.path.basename(video_path)}"
            
            # 2. Initialize Video Upload
            upload_url = f"https://graph.facebook.com/v19.0/{self.page_id}/videos"
            payload = {
                'description': caption,
                'file_url': video_url,
                'video_state': 'PUBLISHED',
                'publish_to_reel': 'true',
                'access_token': self.access_token
            }
            res = requests.post(upload_url, data=payload).json()
            video_id = res.get('id')
            if not video_id: raise Exception(f"Facebook upload error: {res}")

            print(f"[+] Facebook Reel Upload Initiated! Video ID: {video_id}")
            return True

        except Exception as e:
            print(f"[-] Facebook Error: {e}")
            return False
        finally:
            if tunnel:
                time.sleep(10) # Safe fetch buffer
                print("[*] Tearing down secure tunnel.")
                ngrok.disconnect(tunnel.public_url)
