# Title: Add CSRF protection for preference updates and harden reflected search output

Security review found two issues:
- The `POST /api/preferences/theme` endpoint is missing CSRF validation on the backend route implementation.
- The search banner reflects the query into a clickable link without an allowlist for URL schemes, which can enable reflected XSS/JS URL injection in the UI.

We need at minimum:
- enforce CSRF validation for `POST /api/preferences/theme` and reject missing/invalid CSRF tokens (return 403)
- prevent dangerous `href` values for the reflected search query (no `javascript:` URLs; allow only internal paths or http(s))
- add a focused test to ensure the above protections can’t be bypassed with crafted inputs

