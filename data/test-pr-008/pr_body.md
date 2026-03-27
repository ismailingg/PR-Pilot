Closes #52

This PR ships security hardening for the login and admin experience:
- Admin auth guard updated to support the new SSO token format and prevent unauthorized admin access
- User lookup + search queries updated to avoid unsafe query construction
- Frontend redirect banner improved to safely render `returnUrl` and prevent XSS

#this is a pr 