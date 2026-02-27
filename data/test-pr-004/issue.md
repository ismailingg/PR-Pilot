# Title: Normalize usernames by trimming whitespace

Users sometimes paste usernames with leading/trailing spaces, causing login failures.

We need at minimum:
- trim leading/trailing whitespace from username before validation
- if username becomes empty after trimming, raise "Username required"
