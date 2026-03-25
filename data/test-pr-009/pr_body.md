Closes #53

This PR improves the security posture of the settings and search UI:
- Adds CSRF-aware requests for the theme toggle so preference updates are protected
- Updates the search banner display to reflect the user query safely and more clearly
- Includes small UX changes while keeping behavior consistent with the existing settings flow

