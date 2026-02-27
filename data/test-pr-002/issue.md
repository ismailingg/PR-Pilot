# Title: Reject empty usernames on login

Users can submit empty / whitespace-only usernames, which leads to confusing behavior and inconsistent error handling.

We need at minimum:
- username must be non-empty after trimming whitespace
- error message should be "Username required"
