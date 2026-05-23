# OIDC + RBAC — Solution

`oidc_auth.py` shows the minimum complete pattern:
- Verify Bearer token against IdP's JWKS
- Map IdP groups → roles → permissions
- Per-endpoint `Depends(require_permission(...))`

Test by submitting requests with no token (401), bad role (403), and good role (200).
