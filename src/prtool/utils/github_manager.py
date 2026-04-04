import os
import requests
from github import Github, GithubIntegration

class GitHubManager:
    def __init__(self, installation_id: int):
        app_id = os.getenv("GITHUB_APP_ID")
        private_key_path = os.getenv("GITHUB_PRIVATE_KEY_PATH")
        
        with open(private_key_path, 'r') as f:
            private_key = f.read()

        # Authenticate as the specific installation (your repo)
        integration = GithubIntegration(app_id, private_key)
        self.token = integration.get_access_token(installation_id).token
        self.client = Github(self.token)

    def get_pr_details(self, repo_name: str, pr_number: int):
        """Fetches the title, body, and the raw git diff."""
        repo = self.client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        
        # We use a direct request for the diff because it's cleaner for AI to read
        headers = {
            "Authorization": f"token {self.token}", 
            "Accept": "application/vnd.github.v3.diff"
        }
        diff_response = requests.get(pr.diff_url, headers=headers)
        
        return {
            "title": pr.title,
            "body": pr.body,
            "diff": diff_response.text,
            "issue_url": pr.issue_url
        }