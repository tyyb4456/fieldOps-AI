# FieldOps AI Frontend

React + TypeScript + Vite single-page application for FieldOps AI. This
foundation provides Clerk authentication, role-aware routing, an application
shell, and one typed API client for every backend call. Business workflows are
intentionally left as placeholders for later steps.

## Stack

- React 19 + TypeScript
- Vite 8
- Tailwind CSS v4
- React Router 7
- Clerk (`@clerk/react`) for authentication
- Native `fetch` through the shared `ApiClient` (no data-fetching library)
- Node's built-in test runner and Oxlint

## Getting started

```powershell
cd frontend
npm install
Copy-Item .env.example .env
# Set VITE_CLERK_PUBLISHABLE_KEY and VITE_API_BASE_URL
npm run dev
```

`VITE_API_BASE_URL` is validated when the SPA starts:

- Development falls back to `http://localhost:8000` when unset.
- Production requires an explicit absolute `http(s)` URL and rejects loopback
  hosts (`localhost`, `127.x`, `0.0.0.0`, `::1`).
- Embedded credentials are rejected.

The value is the API origin, not the versioned API path. For example:
`https://api.fieldops.example.com`. Requests are made to
`${VITE_API_BASE_URL}/api/v1/...`.

## Commands

```powershell
npm run dev        # Vite dev server
npm run build      # Type-check and production build
npm run preview    # Preview the production build
npm run lint       # Oxlint
npm test           # Node test runner (tests/**/*.test.ts)
npx tsc -b         # Type-check only
```

The production build validates configuration, so set a non-loopback
`VITE_API_BASE_URL` before running `npm run build`.

## Architecture

```text
src/
  main.tsx                    Clerk, Router, and API client providers
  App.tsx                     Route table and role guards
  auth/
    AuthProvider.tsx          Loads the backend account for the Clerk session
    ProtectedRoute.tsx        Applies route access decisions
    route-access.ts           Pure loading/error/redirect/allow logic
    app-auth-context.ts       Auth context and hook
    auth-errors.ts            Maps API failures to auth states
  navigation/
    role-navigation.ts        Role -> navigation items, home path, labels
  lib/api/
    base-url.ts               Environment validation (Node-testable)
    config.ts                 Reads import.meta.env for Vite
    client.ts                 Shared typed HTTP client
    errors.ts                 ApiError and envelope parsing helpers
    types.ts                  Shared enums and response types
    api-client-context.ts     Api client context and useApiClient hook
    ApiClientProvider.tsx     Creates the client with Clerk's getToken
  features/
    accounts/                 Current-user API and types
    customers/                Customer profile types
    equipment/                Equipment types
    complaints/               Complaint types
    knowledge/                Retrieval types
    diagnostics/              Diagnostic investigation types
    workflows/                Workflow run types
    assignments/              Assignment types
    work-orders/              Work order and proposal types
    documents/                Document and ingestion types
  components/                 App shell, loading, error, and config screens
  pages/                      Route-level placeholders
tests/                        Node test-runner suites
```

## Authentication and roles

1. Clerk handles sign-in and sign-up at `/sign-in/*` and `/sign-up/*`.
2. `ApiClientProvider` supplies Clerk's `getToken` to the API client. Every
   authenticated request uses `Authorization: Bearer <token>`.
3. `AuthProvider` calls `GET /api/v1/users/me` to obtain the authoritative
   application role (`customer`, `technician`, or `admin`).
4. If that request returns `404` with `account_not_provisioned`, the provider
   calls `POST /api/v1/auth/bootstrap` once and uses the returned account.
5. `route-access.ts` converts auth state into `loading`, `error`, `redirect`,
   or `allow`. Unauthenticated users go to `/sign-in`; authorization failures
   and inactive/unknown roles go to `/unauthorized`.

Role-based navigation and route guards are UX only. The backend remains the
source of truth for authorization.

| Role | Home | Navigation |
| --- | --- | --- |
| `customer` | `/customer` | Dashboard, Customer workspace |
| `technician` | `/technician` | Dashboard, Technician workspace |
| `admin` | `/admin` | Dashboard, Administrator workspace |

## API client

All backend access goes through `ApiClient`. Do not call `fetch` directly from
pages or components.

```ts
const api = useApiClient()

const complaints = await api.get<PaginatedResponse<Complaint>>(
  '/api/v1/customers/me/complaints',
  { query: { status: 'submitted', page: 1, page_size: 20 } },
)

const report = await api.post<CompletionReport>(
  `/api/v1/work-orders/${workOrderId}/completion-reports`,
  { json: payload },
)
```

Client behaviour:

- Adds the Clerk bearer token unless `authenticated: false`.
- Serializes query parameters and skips `null`/`undefined`.
- Supports JSON bodies, multipart `FormData`, text, and empty responses
  (`204`/`205`).
- Parses the backend error envelope
  `{ "error": { "code", "message", "details"? } }` into `ApiError`.
- Preserves `x-request-id` in `ApiError.requestId`.
- Reports missing/unavailable tokens, network failures, and invalid responses
  as typed errors.
- Never retries non-idempotent requests; abort errors are rethrown unchanged.

Handle failures with the helpers in `lib/api/errors.ts`:

```ts
import {
  isApiError,
  isUnauthorizedError,
  isForbiddenError,
  isNotFoundError,
} from '../lib/api/errors'
```

`401` and `account_not_provisioned` are handled by `AuthProvider`. Other
errors should be surfaced by the consuming screen.

## Backend API integration map

All paths below are prefixed with `/api/v1`. Contracts live in
`backend/app/api/routes` and `backend/app/schemas`; the backend is authoritative.

### Accounts and authentication

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/auth/bootstrap` | Provision the signed-in Clerk user after `account_not_provisioned` |
| `GET` | `/users/me` | Authoritative current account and role |

### Customers and equipment

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`, `PATCH` | `/customers/me` | Current customer profile |
| `GET` | `/customers/{customer_id}` | Admin customer lookup |
| `GET`, `POST` | `/customers/me/equipment` | List or register own equipment |
| `GET`, `PATCH`, `DELETE` | `/customers/me/equipment/{equipment_id}` | Equipment detail and changes |

### Complaints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`, `POST` | `/customers/me/complaints` | List or submit own complaints |
| `GET`, `PATCH` | `/customers/me/complaints/{complaint_id}` | Complaint detail and update |
| `POST` | `/customers/me/complaints/{complaint_id}/cancel` | Cancel a complaint |

Complaint submission does not automatically start AI work.

### Diagnostics and workflows

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/diagnostics/investigate` | Start diagnostic investigation; returns `202` |
| `GET` | `/workflows/{workflow_run_id}` | Poll workflow status (customer/technician view) |

A `202` means work was accepted, not completed. Poll until the workflow leaves
`running`. `running` with `current_step="queued"` means queued, not started.

### Work orders, proposals, and assignments

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/work-orders` | Technician work orders |
| `GET` | `/work-orders/{work_order_id}` | Work-order detail |
| `POST` | `/work-orders/{work_order_id}/accept`, `/reject` | Technician response |
| `POST` | `/work-orders/{work_order_id}/status` | Technician status update |
| `GET` | `/admin/work-orders` | Admin work-order list |
| `GET`, `PATCH` | `/admin/work-orders/{work_order_id}` | Admin detail and update |
| `POST` | `/admin/complaints/{complaint_id}/work-orders` | Create work order |
| `POST` | `/admin/work-orders/{work_order_id}/status` | Admin status update |
| `POST` | `/admin/complaints/{complaint_id}/work-order-proposals` | Start proposal generation; returns `202` |
| `GET` | `/admin/work-order-proposals` | List proposals |
| `GET` | `/admin/work-order-proposals/{proposal_id}` | Proposal detail |
| `POST` | `/admin/work-order-proposals/{proposal_id}/approve`, `/reject` | Synchronous human decision |
| `GET` | `/assignments` | Technician assignments |
| `POST` | `/assignments/{assignment_id}/accept`, `/reject` | Technician response |
| `GET` | `/admin/assignments` | Admin assignment list |
| `POST` | `/admin/work-orders/{work_order_id}/assignments` | Assign technician |
| `POST` | `/admin/work-orders/{work_order_id}/assignments/reassign` | Reassign |
| `POST` | `/admin/assignments/{assignment_id}/withdraw` | Withdraw assignment |
| `GET` | `/technicians`, `/admin/technicians` | Technician directory |

Proposal approval/rejection is synchronous. Poll the associated workflow to
observe generated output.

### Service records and completion reports

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/service-records`, `/admin/service-records` | List records |
| `GET` | `/service-records/{id}`, `/admin/service-records/{id}` | Record detail |
| `GET`, `POST` | `/work-orders/{work_order_id}/service-records` | List or create records |
| `PATCH` | `/service-records/{id}` | Update a record |
| `GET` | `/completion-reports`, `/admin/completion-reports` | List reports |
| `GET` | `/work-orders/{work_order_id}/completion-reports` | Work-order reports |
| `GET` | `/completion-reports/{id}`, `/admin/completion-reports/{id}` | Report detail |
| `POST` | `/work-orders/{work_order_id}/completion-reports` | Create report |
| `PATCH` | `/completion-reports/{id}` | Update report |

### Knowledge base and admin

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/knowledge/search` | Retrieval search |
| `POST` | `/knowledge/answer` | Grounded answer |
| `GET` | `/admin/documents` | List documents |
| `POST` | `/admin/documents` | Upload document |
| `GET`, `PATCH`, `DELETE` | `/admin/documents/{id}` | Document detail and changes |
| `POST` | `/admin/documents/{id}/ingest`, `/activate`, `/deactivate` | Ingestion lifecycle |
| `GET` | `/admin/documents/{id}/chunks` | Document chunks |
| `GET` | `/admin/customers/{customer_id}` | Admin customer detail |
| `GET`, `POST` | `/admin/customers/{customer_id}/equipment` | Admin customer equipment |
| `GET` | `/admin/equipment`, `/admin/equipment/{id}` | Admin equipment |
| `PATCH`, `DELETE` | `/admin/equipment/{id}` | Admin equipment changes |
| `GET` | `/admin/complaints`, `/admin/complaints/{id}` | Admin complaints |
| `GET` | `/admin/complaints/{complaint_id}/history` | Complaint history |
| `GET` | `/admin/workflow-runs` | List workflow runs |
| `GET` | `/admin/workflow-runs/{id}` | Run detail |
| `GET` | `/admin/complaints/{complaint_id}/workflow-runs` | Complaint runs |
| `POST` | `/admin/complaints/{complaint_id}/workflow-runs` | Start a run |
| `POST` | `/admin/workflow-runs/{id}/status` | Internal status update |

## Testing

Tests use Node's built-in runner and exercise pure logic with injected fetch
implementations:

- `tests/api-client.test.ts` - headers, query serialization, responses,
  errors, aborts, and no-retry behaviour
- `tests/api-url.test.ts` - environment validation
- `tests/auth-errors.test.ts` - auth failure mapping
- `tests/current-user.test.ts` - account response parsing
- `tests/role-navigation.test.ts` - role navigation mapping
- `tests/route-access.test.ts` - loading, redirect, and role decisions

Run `npm test`, `npm run lint`, and `npx tsc -b` before proposing changes.
