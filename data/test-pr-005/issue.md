# Title: Add timeouts to external HTTP requests

Our worker sometimes hangs indefinitely when calling an external API.

We need at minimum:
- all outbound HTTP GET requests must specify a timeout (<= 5 seconds)
- on timeout, return None and log a warning
