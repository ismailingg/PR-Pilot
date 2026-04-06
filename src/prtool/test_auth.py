import os
from dotenv import load_dotenv
from github import GithubIntegration

load_dotenv()

def test_connection():
    app_id = os.getenv("GITHUB_APP_ID")
    private_key_path = os.getenv("GITHUB_PRIVATE_KEY_PATH")
    install_id = os.getenv("GITHUB_INSTALLATION_ID")

    print(f" Testing Auth for App ID: {app_id}...")

    with open(private_key_path, 'r') as f:
        private_key = f.read()

    # The Handshake
    integration = GithubIntegration(app_id, private_key)
    
    try:
        # Try to get an access token
        access_token = integration.get_access_token(install_id)
        print(" SUCCESS! Authentication works.")
        print(f" Token generated: {access_token.token[:10]}...")
    except Exception as e:
        print(f" AUTH FAILED: {str(e)}")

if __name__ == "__main__":
    test_connection()