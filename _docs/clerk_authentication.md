# Clerk authentication and operator runbook

FieldOps uses Clerk for sign-in and session issuance, and the FastAPI backend
as the authority for accounts, roles, and profile data. Clerk tokens are
verified on every API request; token claims never assign roles.

## Trust model

- The browser sends a Clerk session token in the `Authorization: Bearer ...`
  header. Cookie-only authentication is rejected, even when a valid
  `__session` cookie is present.
- The backend verifies the token signature and the `azp` (authorized party)
  claim. A missing `azp`, an empty allowlist, or an untrusted `azp` is a 401.
- A valid Clerk identity only proves who the caller is. It does not grant a
  role and does not automatically bind a privileged local account.
- PostgreSQL is the source of truth for `role`, `is_active`, and profile data.
  Clerk token or metadata claims such as `role`, `public_metadata`, and
  `unsafe_metadata` are ignored for authorization.
- Public `POST /api/v1/auth/bootstrap` can create `CUSTOMER` accounts only.
  `ADMIN` and `TECHNICIAN` accounts are bound to Clerk identities only through
  an operator command.

Role/profile consistency is enforced on every authenticated read:

- `CUSTOMER` requires a customer profile and no technician profile.
- `TECHNICIAN` requires a technician profile and no customer profile.
- `ADMIN` has neither operational profile.

An inconsistent account returns `500 account_configuration_error` rather than
being provisioned or silently repaired.

## Required backend configuration

| Variable | Purpose |
| --- | --- |
| `CLERK_SECRET_KEY` | Server-only Backend API access and JWKS retrieval. Used for profile enrichment. Never expose to the frontend. |
| `CLERK_JWT_KEY` | Optional PEM public key for networkless verification. Preferred when available. |
| `CLERK_AUTHORIZED_PARTIES` | Comma-separated frontend origins allowed in the token `azp` claim. Must exactly match the deployed frontend origins. Wildcards are rejected. |
| `CORS_ORIGINS` | Comma-separated browser origins allowed by CORS. Keep aligned with the frontend origins. |
| `AUTH_BOOTSTRAP_RATE_LIMIT_PER_IP` | Best-effort bootstrap limit per direct peer IP. Default `30`. |
| `AUTH_BOOTSTRAP_RATE_LIMIT_PER_SUBJECT` | Best-effort bootstrap limit per Clerk subject. Default `10`. |
| `AUTH_BOOTSTRAP_RATE_LIMIT_WINDOW_SECONDS` | Shared sliding window. Default `60`. |

Production startup requires `CLERK_SECRET_KEY` or `CLERK_JWT_KEY`, a non-empty
`CLERK_AUTHORIZED_PARTIES`, secure CORS, and TLS database settings.

The bootstrap limiter is in-process and intentionally dependency-free. A
multi-instance deployment must also enforce authentication limits at the
reverse proxy or API gateway. The backend does not trust `X-Forwarded-For`;
configure trusted proxy handling before relying on client IPs.

## Required frontend configuration

| Variable | Purpose |
| --- | --- |
| `VITE_CLERK_PUBLISHABLE_KEY` | Clerk publishable key. Safe for the browser. |
| `VITE_API_BASE_URL` | Absolute backend origin. Required for production builds; the localhost fallback exists only in development. |

`VITE_API_BASE_URL` is validated at build time and at runtime. Production builds
fail if it is missing, malformed, non-HTTP(S), or contains embedded
credentials. Never put `CLERK_SECRET_KEY` in a `VITE_*` variable.

## Session token claims

No custom session token claims are required. Clerk's default version 2 session
token contains only standard claims (`azp`, `exp`, `fva`, `iat`, `iss`, `jti`,
`nbf`, `sid`, `sub`, `v`); it does **not** include `email`, name, or phone
claims by default. During bootstrap the backend therefore fetches the profile
from the Clerk Backend API using `CLERK_SECRET_KEY`. A deployment that provides
only `CLERK_JWT_KEY` can authenticate users but will not capture email/name or
support verified-email account linking unless those claims are added explicitly
to the session token.

The backend reads these optional signed claims when present:

- `sub` (required)
- `sid`
- `email` / `email_address` / `primary_email_address`
- `email_verified` / `primary_email_address_verified`
- `phone` / `phone_number` / `primary_phone_number`
- `phone_verified` / `phone_number_verified` / `primary_phone_number_verified`
- `name` / `full_name`, or `first_name` + `last_name`

If a new account has no verified email claim, the backend may query the Clerk
Backend API using `CLERK_SECRET_KEY`. Enrichment is bounded with exponential
backoff and a maximum of five attempts. A verified Clerk email is applied only
when the local account has no email; local data is never overwritten. Do not
put authorization roles in custom claims.

## Clerk Dashboard checklist

1. Configure the application origins used by Clerk and set allowed/authorized
   parties to exactly the deployed frontend origin(s). Keep them identical to
   `CLERK_AUTHORIZED_PARTIES`.
2. Require email address verification if customer accounts may link to an
   existing local account by email. Unverified email addresses are never used
   for linking or profile storage, and unverified accounts are stored without
   an email address.
3. Confirm that `CLERK_SECRET_KEY`, `CLERK_JWT_KEY`, and
   `VITE_CLERK_PUBLISHABLE_KEY` all belong to the same Clerk application
   instance. A stale or mismatched key causes 401 responses (verification) or
   silent profile-enrichment failures (email/name not captured).
4. Keep session token lifetime and clock-skew assumptions consistent with the
   backend defaults. The backend uses the SDK default clock skew.
5. Do not use Clerk metadata to drive FieldOps roles. Roles stay in PostgreSQL.
6. If custom session claims are added, use the exact claim names above and
   treat them as untrusted profile hints, never as authorization input.

## Account lifecycle

1. The frontend signs the user in with Clerk and obtains a session token.
2. It calls `GET /api/v1/users/me` with the bearer token.
3. If the backend returns `404 account_not_provisioned`, the frontend calls
   `POST /api/v1/auth/bootstrap` once and uses the returned account.
4. `GET /api/v1/users/me` is read-only. It never provisions users or creates
   profiles.
5. Bootstrap is idempotent. Repeated calls do not duplicate users and ignore
   role claims.
6. A 401 signs the user out. A 403 is an authorization/inactive-account state
   and routes to the unauthorized screen without signing the user out.

Response codes:

| Status | Code | Meaning |
| --- | --- | --- |
| 401 | `unauthenticated` | Missing, malformed, expired, or untrusted bearer token. |
| 403 | `account_inactive` | The local account is disabled. |
| 403 | `forbidden` | The authenticated role is not allowed for the route. |
| 404 | `account_not_provisioned` | Valid identity with no local account yet; bootstrap first. |
| 409 | `account_conflict` | Identity/email conflict or privileged auto-link attempt. |
| 429 | `rate_limited` | Bootstrap limit exceeded; retry after `Retry-After`. |
| 500 | `account_configuration_error` | Role/profile invariant violation. |

## Operator commands

Use the backend virtual environment from `backend/`:

```powershell
python -m app.scripts.manage_roles set-role --email admin@example.com --role admin
python -m app.scripts.manage_roles set-role --user-id <uuid> --role technician
python -m app.scripts.manage_roles link-identity --email admin@example.com --clerk-user-id user_xxx
python -m app.scripts.manage_roles link-identity --user-id <uuid> --clerk-user-id user_xxx
```

`link-identity` fetches and verifies the Clerk profile with
`CLERK_SECRET_KEY`, requires a verified email matching the local account, does
not change the role, and refuses identities already linked elsewhere. Verified
email auto-linking is public only for `CUSTOMER` accounts. Privileged accounts
that match an email are rejected until an operator links them explicitly.

## Key rotation

### Session signing key (`CLERK_JWT_KEY`)

Use `CLERK_SECRET_KEY` (dynamic JWKS) where possible so Clerk key rotation is
handled by the SDK. When using a static `CLERK_JWT_KEY`:

1. Schedule a controlled maintenance window; a single PEM cannot contain both
   old and new signing keys.
2. Rotate the instance/session signing key in the Clerk Dashboard.
3. Update `CLERK_JWT_KEY` in the secret manager, redeploy, and restart every
   backend instance at the same time.
4. Expect existing sessions signed by the old key to fail verification and
   require sign-in again.
5. Verify a fresh sign-in against `GET /api/v1/users/me` and confirm the
   `sub` matches the expected local account.

### Secret key (`CLERK_SECRET_KEY`)

1. Create a new secret key in the Clerk Dashboard.
2. Store it in the deployment secret manager; do not commit it or place it in
   frontend variables.
3. Roll the backend deployment. Old and new keys may overlap only as long as
   the Dashboard keeps the old key active.
4. Revoke the old secret key after all instances report healthy.
5. Re-run the bootstrap smoke test and check logs for Clerk API failures.

### Publishable key

Rotate `VITE_CLERK_PUBLISHABLE_KEY` together with a Clerk instance change,
rebuild the frontend, and redeploy. Confirm the new key is a publishable key
(`pk_...`) and that no secret value is present in the bundle.

## Verification

Backend:

```powershell
cd backend
python -m pytest -q
python -m compileall -q app alembic
python -m alembic current
python -m alembic check
```

Frontend:

```powershell
cd frontend
npm run lint
npm test
$env:VITE_API_BASE_URL = "https://api.example.com"
npm run build
```

Also confirm the production build fails when `VITE_API_BASE_URL` is unset and
that `CLERK_AUTHORIZED_PARTIES` matches the deployed frontend origin exactly.
