import os
import re
import requests
from github import Github, GithubIntegration


class GitHubManager:
    def __init__(self, installation_id: int):
        app_id = os.getenv("GITHUB_APP_ID")
        private_key_path = os.getenv("GITHUB_PRIVATE_KEY_PATH")

        if not app_id or not private_key_path:
            raise RuntimeError("GITHUB_APP_ID and GITHUB_PRIVATE_KEY_PATH must be set in .env")

        with open(private_key_path, "r") as f:
            private_key = f.read()

        integration = GithubIntegration(app_id, private_key)
        self.token = integration.get_access_token(installation_id).token
        self.client = Github(self.token)

    def get_pr_details(self, repo_name: str, pr_number: int) -> dict:
        """Fetches the title, body, raw git diff, and linked issue text."""
        repo = self.client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        # Fetch the raw unified diff
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3.diff",
        }
        diff_response = requests.get(pr.url, headers=headers)

        if diff_response.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch diff (HTTP {diff_response.status_code}): "
                f"{diff_response.text[:300]}"
            )

        diff_text = diff_response.text
        if not diff_text.strip():
            raise RuntimeError(
                f"Diff is empty for PR #{pr_number} — the PR may have no code changes."
            )

        print(f"📄 Diff fetched: {len(diff_text)} chars across the changed files.")

        # Fetch the real issue description
        issue_body = self._fetch_issue_body(repo, pr)

        return {
            "title": pr.title,
            "body": pr.body or "",
            "diff": diff_text,
            "issue_body": issue_body,
        }

    def _fetch_issue_body(self, repo, pr) -> str:
        """
        Tries to find and return the body of the issue linked in the PR.
        Falls back to the PR body if no linked issue is found.
        """
        try:
            if pr.body:
                # Look for "Closes #12", "Fixes #5", "Resolves #99" etc.
                match = re.search(
                    r"(?:closes|fixes|resolves)\s+#(\d+)",
                    pr.body,
                    re.IGNORECASE,
                )
                if match:
                    issue_number = int(match.group(1))
                    linked_issue = repo.get_issue(issue_number)
                    body = linked_issue.body or ""
                    if body.strip():
                        print(f"🔗 Linked issue #{issue_number} fetched.")
                        return body

            # No linked issue found — use the PR body as context
            print("ℹ️  No linked issue found. Using PR body as issue context.")
            return pr.body or "No issue description provided."

        except Exception as e:
            print(f"⚠️  Could not fetch linked issue: {e}. Falling back to PR body.")
            return pr.body or "No issue description provided."

    def post_pr_comment(self, repo_name: str, pr_number: int, comment_body: str) -> bool:
        """Posts a top-level comment to the specified Pull Request."""
        try:
            repo = self.client.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            pr.create_issue_comment(comment_body)
            print(f" Successfully posted comment to PR #{pr_number}")
            return True
        except Exception as e:
            print(f" Failed to post comment: {str(e)}")
            return False