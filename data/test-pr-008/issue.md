# Title: Fix admin auth bypass, SQL injection, and XSS in login/admin flows

The admin login flow was updated as part of the SSO work, but the current behavior allows:
- authenticating as admin without a valid signed token
- injecting SQL through email/search parameters used by admin UI
- executing reflected HTML/JavaScript through a `returnUrl` parameter rendered on the frontend

We need at minimum:
- remove any client-controlled “admin bypass” behavior (no trusting `role`/query params for authorization)
- ensure all DB access uses parameterized queries (no string-built SQL from user input)
- ensure all user-controlled values reflected in HTML are properly escaped/sanitized (no `dangerouslySetInnerHTML` with unsanitized input)
- add regression coverage so the admin page cannot be exploited by malformed `returnUrl`, `email`, or `q`

