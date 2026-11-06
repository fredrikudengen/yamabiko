# Auth Boundary Guide

This guide defines the supported authentication boundary for non-auth modules.

## Public Boundary

Non-auth modules must consume auth **only** through these public entry points:

- `auth.dependencies`
- `auth.identity_service.IdentityService`

`IdentityService` exposes both credential resolution (e.g. `resolve_from_access_token`,
`resolve_from_api_key`) and the higher-level account-security workflows (sessions,
password change, MFA lifecycle). Non-auth modules call these methods on
the injected `IdentityService`; they do **not** import the implementations.

The workflow implementations live in `auth.services.*` (see *Auth Service Modules*
below), but those modules are **auth-internal**: `IdentityService` delegates to them,
and import-linter forbids non-auth modules from importing them directly. Do not import
low-level auth internals or `auth.services.*` from non-auth modules.

## Principal Model

`IdentityService` resolves identity into a `Principal` object that carries auth-relevant identity and authorization data for the current request.

Core fields include:

- `user_id`
- `username`
- `email`
- `is_active`
- `is_superuser`
- `scopes`
- `credential`

Callers should prefer helper methods on `Principal` (for example `is_api_key()` and credential ID helpers) instead of matching against internal credential-shape details in non-auth modules.

## Credential Discriminated Union

`Principal.credential` is a discriminated union, not a set of parallel optionals. Variants include:

- `PasswordCred`
- `AccessTokenCred`
- `ApiKeyCred`
- `SessionCookieCred`
- `OAuthCred`

Each variant contains only the fields meaningful for that authentication method (for example, access-token metadata for `AccessTokenCred`, API-key identifiers for `ApiKeyCred`, and session IDs for `SessionCookieCred`).

## Ownership Map

Auth-owned modules include:

- Credentials and token lifecycle (`auth.token_manager`, `auth.password_hasher`)
- Sessions and rotated refresh tokens (`auth.sessions`)
- API keys (`auth.api_keys`)
- MFA setup state, TOTP logic, and backup-code lifecycle (`auth.mfa`, `auth.mfa.backup_codes`)
- Password reset tokens (`auth.password_reset_tokens`)
- Step-up credential verification with lockout (`auth.services.step_up_service`)
- Password change workflows (`auth.services.account_security_service`)
- MFA management workflows (`auth.services.mfa_workflow`)

Users/profile-owned modules include:

- Profile fields
- Privacy settings
- User-facing profile routes and orchestration
- Business-level user data unrelated to auth credential/state ownership

## Auth Service Modules

The following facade modules implement the account-security workflows that
`IdentityService` delegates to. They are **auth-internal**: non-auth modules reach
this behaviour through the matching `IdentityService` methods, never by importing
these modules directly. Each encapsulates a cluster of related auth workflows so the
delegators stay thin and low-level auth persistence modules are not imported across
the boundary.

| Module (internal) | Responsibility | Reached via `IdentityService` |
| ----------------- | -------------- | ----------------------------- |
| `auth.services.account_security_service` | `change_own_password`, `change_managed_user_password`, session listing/revocation | `get_user_sessions`, `delete_user_session`, `change_own_password`, `change_managed_user_password` |
| `auth.services.mfa_workflow` | MFA status, setup, enable, disable, backup-code status and regeneration | `get_mfa_status`, `setup_mfa`, `enable_mfa`, `disable_mfa`, `verify_mfa`, `get_backup_code_status`, `generate_backup_codes` |
| `auth.services.step_up_service` | `verify_step_up_credentials` with progressive lockout (5/5 min, 10/30 min, 15/2 hr) | used internally by the workflow modules above |

## Service Placement Rule

- `auth.services.*` owns high-level workflows, reached by non-auth callers through
  `IdentityService` (not imported directly).
- `auth.<domain>.crud` owns persistence for one auth domain.
- `auth.<domain>.schema` owns request/response models for that domain.
- Pure helpers may live in `auth.<domain>.*` when they do not orchestrate step-up,
  route behavior, or multi-module workflows.
- New non-auth callers must use `auth.dependencies` or `IdentityService`, not
  `auth.services.*` or low-level CRUD modules.

## Import-Linter Contracts

The backend import-linter enforces two key constraints:

1. Non-auth modules cannot import:
   - `auth.internal_dependencies`
   - `auth.password_hasher`
   - `auth.token_manager`
2. Non-auth modules cannot import low-level ownership modules or the internal
   workflow layer directly:
   - `auth.password_reset_tokens.crud`
   - `auth.sessions.crud`
   - `auth.mfa.crud`
   - `auth.mfa.backup_codes.crud`
   - `auth.credentials.crud`
   - `auth.security_stores`
   - `auth.services`

These workflows and persistence helpers are reached through `IdentityService`
instead. A small set of route/service facade exceptions is explicitly
allow-listed in `backend/.importlinter`.

## Transaction Contract

`IdentityService` does not own transaction policy. It delegates DB operations to auth CRUD helpers, and those helpers own commit/refresh behavior. When callers need multi-step atomic workflows, use dedicated CRUD/service helpers designed for that workflow.

## Known Structural Debt

### Step-up for accounts without a local password

`auth.services.step_up_service.verify_step_up_credentials` skips the password
factor when the account has no local password (no row in
`users_local_credentials`). Such accounts came from SSO, which Yamabiko has
removed, and they can no longer sign in, so the gap is theoretical. MFA still
gates if enabled.
