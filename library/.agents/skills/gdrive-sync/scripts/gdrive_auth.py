import os
import sys
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/drive'
]

def get_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent
    return Path.cwd()

def resolve_token_path() -> Path:
    env_path = os.getenv("GDRIVE_TOKEN_PATH")
    if env_path:
        return Path(env_path).resolve()
    return get_repo_root() / "token.json"

def resolve_creds_path() -> Path:
    env_path = os.getenv("GDRIVE_CREDENTIALS_PATH")
    if env_path:
        return Path(env_path).resolve()
    return get_repo_root() / "credentials.json"

def get_drive_service(interactive: bool = True):
    token_path = resolve_token_path()
    creds_path = resolve_creds_path()
    
    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            if creds and not creds.valid and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
                print(f"[gdrive-sync] Refreshed expired OAuth token ({token_path})")
        except Exception as e:
            print(f"[gdrive-sync] Warning: Token load/refresh failed: {e}")
            creds = None

    if not creds or not creds.valid:
        if not interactive:
            raise RuntimeError(f"Valid token not found at {token_path} and interactive=False.")
        
        if not creds_path.exists():
            raise FileNotFoundError(
                f"credentials.json not found at {creds_path}. "
                "Please download OAuth client credentials from Google Cloud Console and save as credentials.json."
            )
            
        print(f"[gdrive-sync] Initiating OAuth login using {creds_path.name}...")
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
        flow.redirect_uri = "http://localhost:64744/"
        
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        
        print("\n" + "="*80)
        print("GOOGLE DRIVE AUTHENTICATION REQUIRED")
        print("Please visit the following URL to authorize:")
        print(auth_url)
        print("="*80 + "\n")
        
        try:
            subprocess.Popen(f'start "" "{auth_url}"', shell=True)
        except Exception:
            pass
            
        auth_response_url = []
        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                auth_response_url.append(f"http://localhost:64744{self.path}")
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h1>Authentication successful!</h1><p>You can close this tab now.</p>")
            def log_message(self, format, *args):
                pass
                
        httpd = HTTPServer(('localhost', 64744), CallbackHandler)
        print("[gdrive-sync] Waiting for authorization callback on port 64744...")
        httpd.handle_request()
        
        flow.fetch_token(authorization_response=auth_response_url[0])
        creds = flow.credentials
        
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"[gdrive-sync] OAuth token successfully saved to {token_path}")
        
    return build("drive", "v3", credentials=creds)

if __name__ == "__main__":
    service = get_drive_service(interactive=True)
    about = service.about().get(fields="user(displayName, emailAddress)").execute()
    user_info = about.get("user", {})
    print(f"[gdrive-sync] Authenticated successfully as: {user_info.get('displayName')} ({user_info.get('emailAddress')})")
