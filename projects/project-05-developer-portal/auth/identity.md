# Identity and access

The portal is the auth boundary the user sees. SSO at the portal,
[OAuth 2.0 Token Exchange (RFC 8693)](https://www.rfc-editor.org/info/rfc8693/)
for every downstream call. The user signs in once a day; every
downstream API call rides a short-lived token bound to the user's
identity and tenant.

## Trust boundaries

```text
Browser
  │  HttpOnly cookie (portal session)
  ▼
Portal frontend ─── (CSP, no third-party JS) ───▶ Portal backend
                                                         │
        OIDC authorization code flow ──▶ Identity Provider (Okta/Auth0/Keycloak/Dex/Cognito)
                                                         │
                                                         ▼
                       RFC 8693 token exchange (subject token = portal-side
                       opaque session ref + actor token = portal SVID)
                                                         │
                                                         ▼
                              short-lived bearer access token
                                            │
                                            ▼
                           Platform APIs (project-01..04)
                           - sub  = user identity
                           - aud  = "<platform-component>"
                           - tenant claim selects RLS scope
```

## Sign-in

- The portal uses an OIDC authorization code flow with PKCE.
- The IdP returns an ID token (the user's identity) and an
  access token scoped to the portal's audience.
- The portal verifies the ID token, creates a server-side
  session, and sets one HttpOnly cookie:
  - `HttpOnly`
  - `Secure`
  - `SameSite=Lax`
  - `Max-Age` = 8 h with a sliding refresh; refresh window 24 h.
- The cookie value is an opaque session ID. Never a JWT, never
  the IdP's access token.

The portal stores no passwords. Account lifecycle (create,
disable, MFA enrollment) is entirely IdP-side.

## Downstream API calls

When the portal backend needs to talk to a platform API on
behalf of the user, it performs an RFC 8693 token exchange:

- **Subject token**: the opaque session reference (or the
  cached IdP access token from the user's sign-in).
- **Actor token**: the portal's own workload identity (a SPIFFE
  SVID issued by SPIRE; see project-01 `audit/`).
- **Requested audience**: the target platform API
  (`urn:ml-platform:project-01-control-plane`, etc.).

The IdP (or the platform's STS) returns a new access token whose:

- `sub` is the user's identity.
- `aud` is the target API.
- `tenant` claim is derived from the user's group membership.
- `exp` is 5 minutes from issue.

The platform API validates the token's signature, the `aud`, the
`tenant` claim, and the `sub`. The `tenant` claim sets the
row-level-security scope in project-01's database session
(`SET LOCAL platform.tenant = :claim`).

## Service identities

Service-to-service calls (the catalog backend ingesting from
the registry, the scaffolder bot publishing repos) use the same
flow with the `client_credentials` grant. The catalog backend
has read-only audience scopes; the scaffolder bot has
write-scoped audiences but only acts on behalf of the *requesting
user* via further token exchange.

The catalog backend never proxies a user's token to do its own
ingestion. Mixing user identity with system identity is the
confused-deputy pattern; reject it at design time.

## The F5 negative test

The probe that pins this design is the F5 acceptance check:

```bash
# Step 1: sign in normally; copy the session cookie out of dev tools.
cookie="$(./scripts/portal-login)"

# Step 2: replay the cookie directly against the platform API.
curl -sS -H "Cookie: portal-session=$cookie" \
     https://platform.example.com/v1/trainingruns
# Expect: HTTP 401. The session is not an API credential.
```

A platform API that accepts the portal's session cookie has
bypassed the trust boundary. The session is the *portal's*
state; the platform API only trusts tokens its STS issued.

## Logout

Logout invalidates the server-side session. The IdP's logout is
*also* called via OIDC RP-Initiated Logout, but the portal does
not depend on it — clearing the session row is what makes the
cookie unusable.

## Sensitive admin actions

`onboard-tenant` and other admin-only scaffolder templates
require step-up auth: the IdP is asked to re-prompt for MFA at
template runtime. The portal does not gate "admin-ness" by an
in-portal flag; the IdP's claim is the source of truth.

## References

- OAuth 2.0 Authorization Framework (RFC 6749):
  <https://www.rfc-editor.org/info/rfc6749/>
- OAuth 2.0 Token Exchange (RFC 8693):
  <https://www.rfc-editor.org/info/rfc8693/>
- OAuth 2.0 for Browser-Based Apps (RFC 9700, BCP 240):
  <https://www.rfc-editor.org/info/rfc9700/>
- OpenID Connect Core 1.0:
  <https://openid.net/specs/openid-connect-core-1_0.html>
- OpenID Connect RP-Initiated Logout 1.0:
  <https://openid.net/specs/openid-connect-rpinitiated-1_0.html>
- Backstage auth provider docs:
  <https://backstage.io/docs/auth/>
- SPIFFE / SPIRE workload identity (used for the actor token):
  <https://spiffe.io/docs/latest/spiffe-about/overview/>
