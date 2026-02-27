# Title: Prevent path traversal in file download

The download endpoint uses a user-provided filename. This may allow reading arbitrary files via "../".

We need at minimum:
- reject any filename containing path separators or ".."
- only allow files from the uploads directory
- raise ValueError("Invalid filename") on rejection
