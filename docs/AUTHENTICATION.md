# EduPredict - Authentication and Authorization

Phase 2. This document separates what the project specification requires from
what the implementation chose.

The authoritative source is **`docs/Big Data-EduPredict.docx`** (unmodified).

---

## 1. SOURCE REQUIREMENTS

The document's only authentication and authorization requirement is in
*Functional Requirements*:

> **User Authentication and Authorization:**
> Implement a secure authentication system for users with different roles, such
> as administrators, teachers, students, and analysts.
> Define access controls to restrict data access based on user roles and
> responsibilities.

The relevant *Non-Functional Requirement* is:

> **Data Security:** Implement encryption mechanisms to secure sensitive
> educational data during storage and transmission. Ensure compliance with
> relevant data protection regulations and standards.

Everything below that is not quoted above is an **implementation decision**.

### 1.1 What the document does NOT specify

The following are absent from the document, and this phase therefore does not
invent them:

| Not specified | Consequence |
|---|---|
| An authentication framework or library | The simplest mechanism compatible with the existing Flask architecture was chosen and recorded as ADR-0009. |
| A database for user accounts | The simplest persistent mechanism was chosen and recorded as ADR-0010. |
| Per-role permissions or capabilities | No permission matrix is implemented. See section 5. |
| A role other than the four named | Exactly four roles exist. No fifth role is created. |
| Social / federated login | Not implemented. Not required, and excluded from scope. |
| User profile data (email, avatar, preferences) | Not implemented. Only what authentication requires is stored. |
| Sign-up, password reset, email verification | Not implemented. Accounts are provisioned by an operator. |

---

## 2. AUTHENTICATION ARCHITECTURE

### 2.1 Flow

```text
Browser
  |
  |  POST /auth/login   (username, password, csrf_token)
  v
edupredict.web.auth_routes.login
  |
  +--> verify_csrf()                    token compared with hmac.compare_digest
  |
  +--> service.is_locked(username)      repeated-failure lockout
  |
  v
edupredict.auth.AuthenticationService.authenticate
  |
  +--> UserStore.get_by_username()      case-insensitive lookup
  |
  +--> passwords.verify_password()      scrypt, constant-time
  |       (against a dummy hash when the user does not exist,
  |        so response time does not reveal valid usernames)
  |
  v
User  ->  session["uid"] = user.id      only the id goes in the cookie
       ->  session cleared and rewritten (session-fixation defence)
       ->  302 to the requested page
```

### 2.2 Password storage

* Hashing uses `werkzeug.security.generate_password_hash` /
  `check_password_hash`. Werkzeug 3.x defaults to **scrypt**
  (`scrypt:32768:8:1`), a memory-hard key derivation function.
* **Plaintext passwords are never stored.** There is no column, file or log
  line that holds one.
* Every hash carries its own random salt, so two accounts with the same password
  produce different stored values.
* The algorithm and its parameters are embedded in the hash string, so
  parameters can be raised later without invalidating existing accounts.
  `needs_rehash()` detects accounts that are still on old parameters.
* A minimum password length of 8 characters is enforced at account creation.

Werkzeug was chosen because it is **already a hard dependency of Flask**. Using
it adds no new third-party package, unlike Flask-Login, Authlib or a dedicated
auth package.

### 2.3 Timing and enumeration defences

* An unknown username is verified against a dummy hash, so "no such user" and
  "wrong password" take comparable time and return the identical message
  (`Incorrect username or password.`).
* Failed logins are counted per username; after `max_login_failures` within
  `lockout_seconds` the account is locked out. The counter is in-process state,
  which is appropriate for the documented single-node deployment and is
  documented as such rather than presented as a distributed control.

---

## 3. AUTHORIZATION ARCHITECTURE

### 3.1 Two layers

Authorization is expressed at two levels:

1. **Role guards** (implemented, enforced) - `@login_required` and
   `@roles_required(...)` decide whether a request may proceed. This is the
   requirement the document actually states: restrict access by role.
2. **Permission registry** (mechanism only, empty) - `auth/permissions.py`
   provides `PermissionRegistry` so a later phase can attach named capabilities
   to roles. It ships **empty**, because no permission names are specified in
   the document.

### 3.2 Guard behaviour

| Situation | Browser (`Accept: text/html`) | API client (`Accept: application/json`) |
|---|---|---|
| Not authenticated | `302` to `/auth/login?next=...` | `401` JSON |
| Authenticated, role not permitted | `403` HTML page | `403` JSON |
| Authenticated and permitted | the view runs | the view runs |

`roles_required()` with no roles raises `AuthorizationError` rather than
silently denying everyone - a programming error must not look like a security
control.

### 3.3 Freshness of the role

The session cookie stores **only the numeric user id**. The role is re-read
from the store on every request, so:

* a role change applies immediately, without forcing a re-login;
* no password hash and no role value is exposed in a browser-readable cookie;
* deleting an account revokes access at once, because the lookup fails.

---

## 4. ROLES

Exactly four roles exist, matching the four named in the document. They are
declared in `src/edupredict/auth/roles.py`:

| Role | Stored value | Label |
|---|---|---|
| `Role.ADMINISTRATOR` | `administrator` | Administrator |
| `Role.TEACHER` | `teacher` | Teacher |
| `Role.STUDENT` | `student` | Student |
| `Role.ANALYST` | `analyst` | Analyst |

A test asserts `len(Role) == 4`, so an extra role cannot be added without
failing the suite.

The **stored value** is the stable token in the database; the **label** is
presentation only. `Role.parse()` accepts the value or the label in any case, so
the CLI, the database and the templates all accept the same spellings, and
rejecting anything else raises `UnknownRoleError`.

---

## 5. PERMISSIONS - DELIBERATELY NOT INVENTED

> **Detailed role permissions are not specified in the source document and will
> be defined when the corresponding functional modules are implemented.**

`PermissionRegistry` is therefore **empty** in this phase. The dashboard shows
this statement to the user rather than implying a permission model exists.

A later phase adds permissions with a single call, for example:

```python
from edupredict.auth import REGISTRY, Role

REGISTRY.define("analytics.view", "View analytics outputs", (Role.ANALYST, Role.TEACHER))
```

An undefined permission raises `AuthorizationError` on `check()` rather than
returning `False`, so a typo in a guard surfaces immediately instead of denying
access silently.

---

## 6. STORAGE

`sqlite3` from the Python standard library, in a single file at
`var/auth/users.db` (configurable).

**Why SQLite** (ADR-0010):

* It ships with CPython - no new dependency, consistent with Phase 1.
* It is transactional, so an interrupted write cannot corrupt the store.
* It is one file, which suits an eProject that must be simple to run and submit.
* MongoDB appears in the document's software list, but the document never says
  what it stores. It was **not** introduced for authentication, because listing
  a tool is not a requirement to use it for this purpose.

**Schema** (created on first use, so a fresh checkout needs no migration):

```sql
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL,
    created_at    TEXT    NOT NULL
);
```

`COLLATE NOCASE` prevents `Alice` and `alice` from being two accounts.

**Swapping the backend** requires only a new class satisfying the `UserStore`
Protocol in `auth/users.py`. `web/`, `app.py` and the CLI all use
`build_user_store()`, so no caller imports a concrete store.

---

## 7. SESSION AND TRANSPORT SECURITY

| Control | Setting | Why |
|---|---|---|
| Signing key | `[auth] secret_key` | Empty in the repository. Supplied via `EDUPREDICT_AUTH__SECRET_KEY`. |
| Ephemeral fallback | random key per process, development only | Lets a fresh checkout run. A warning is logged; sessions die on restart. |
| Missing key in production | `ConfigurationError` | A deployment must not silently run on a throwaway key. |
| Short key (<32 chars) | rejected | Too little entropy to sign a cookie. |
| `SESSION_COOKIE_HTTPONLY` | `true` | JavaScript cannot read the session cookie. |
| `SESSION_COOKIE_SAMESITE` | `Lax` | Blocks the cookie on cross-site POSTs. |
| `SESSION_COOKIE_SECURE` | configurable, `false` locally | Set `true` for any HTTPS deployment. |
| `PERMANENT_SESSION_LIFETIME` | 60 minutes | Limits the value of a stolen cookie. |
| Session fixation | cookie cleared and rewritten on login | A pre-login session id cannot be reused. |
| CSRF | token per session, `hmac.compare_digest` | State-changing POSTs are not forgeable cross-site. |
| `MAX_CONTENT_LENGTH` | 16 KiB | Caps the login form body. |
| Open redirect | `safe_next_target()` | `//evil.example` and absolute URLs are rejected. |
| Logout | `POST` only | A `GET` logout could be triggered by any web page. |

**No secret is committed.** `config/settings.toml` ships
`secret_key = ""`, and a test asserts that value is empty. The CLI reads the
password from a hidden prompt or from standard input, never from `argv`, so it
cannot leak into shell history, a process listing or a CI log.

---

## 8. WEB SURFACE

| Route | Method | Guard | Purpose |
|---|---|---|---|
| `/` | GET | public | Status page; shows who is signed in, if anyone. |
| `/health` | GET | public | Phase 1 JSON health report, unchanged. |
| `/auth/login` | GET, POST | public | Sign-in form and credential check. |
| `/auth/logout` | POST | CSRF | End the session. |
| `/auth/dashboard` | GET | `login_required` | Authenticated, role-aware landing page. |
| `/auth/admin` | GET | `roles_required(ADMINISTRATOR)` | Proves and tests the role boundary. |

`/auth/admin` lists accounts so an administrator can see who exists. It shows
username, role and creation time only - never any credential material.

**No fabricated content.** The pages contain no statistics, predictions, dataset
values or dashboards. The dashboard states explicitly which modules arrive in
later phases.

---

## 9. CONFIGURATION

```toml
[auth]
database_path         = "var/auth/users.db"
secret_key            = ""      # never commit a real value
session_lifetime_minutes = 60
csrf_protection       = true
max_login_failures    = 5
lockout_seconds       = 300
cookie_secure         = false   # set true behind HTTPS
max_content_length    = 16384
```

Every key can be overridden by environment variable using the existing
convention, e.g. `EDUPREDICT_AUTH__SECRET_KEY`.

---

## 10. RUNNING AND TESTING LOCALLY

```bash
cd C:\Users\admin\Desktop\EduPredict
python -m pip install -e ".[dev]"

# 1. Set a signing key (recommended; optional in development)
setx EDUPREDICT_AUTH__SECRET_KEY "a-long-random-string-of-at-least-32-chars"

# 2. Create one account per documented role. The password is prompted
#    without echo, so it never enters shell history.
python -m edupredict user create admin.user  --role administrator
python -m edupredict user create teacher.one --role teacher
python -m edupredict user create student.one --role student
python -m edupredict user create analyst.one --role analyst

# 3. List accounts (never shows hashes)
python -m edupredict user list

# 4. Run the application
python -m edupredict serve --port 5000

# 5. Run the tests
python -m pytest
python -m pytest tests/test_auth.py tests/test_auth_web.py tests/test_auth_security.py
```

Then open <http://127.0.0.1:5000/>, sign in, and open
<http://127.0.0.1:5000/auth/admin> to confirm the role boundary.

### Manual checks

```bash
# Unauthenticated browser -> 302 to the login form
curl -i http://127.0.0.1:5000/auth/dashboard

# Unauthenticated API client -> 401 JSON
curl -i -H "Accept: application/json" http://127.0.0.1:5000/auth/dashboard

# Non-administrator -> 403
# (sign in as teacher.one first, carrying the session cookie)
curl -i -b cookies.txt -H "Accept: application/json" http://127.0.0.1:5000/auth/admin
```

---

## 11. WHAT THIS PHASE DOES NOT CLAIM

* **No regulatory compliance.** The document asks for compliance with data
  protection regulations. No audit, certification or legal review was performed,
  and none is claimed. What *is* implemented is a set of concrete controls:
  salted memory-hard hashing, no plaintext storage, no committed secrets, role
  enforcement, CSRF tokens, hardened cookies, generic error responses.
* **No encryption of stored data at rest.** The document's Data Security clause
  mentions encryption. Passwords are hashed, which is the correct control for
  credentials, but the account database is not encrypted - that is filesystem
  and deployment work, not application work, and it is not claimed here.
* **No distributed lockout.** The failure counter is per process.
* **No password rotation policy, MFA, or session revocation on logout
  elsewhere** beyond clearing this session.
* **No permission matrix**, by design - see section 5.

---

## 12. ADRs

| ADR | Subject |
|---|---|
| ADR-0009 | Authentication mechanism and role model |
| ADR-0010 | SQLite as the authentication store |
| ADR-0011 | Session security, CSRF and secret-key handling |
| ADR-0012 | Account provisioning through the CLI |

See `docs/DECISIONS.md`.
