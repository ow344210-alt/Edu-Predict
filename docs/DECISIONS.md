# Architecture Decision Records

Decisions taken during Phase 1 and Phase 2, and questions deliberately left open
for later phases. Each record states the context, the decision, and what it
costs.

---

## ADR-0001 - Python as the implementation language

**Status:** Accepted (Phase 1)

**Context**
`Big Data-EduPredict.docx` does not name a programming language. It names
*Jupyter Anaconda Notebook*, *RStudio*, *Visual Studio Code / PyCharm*,
*MongoDB Compass and Shell*, *Hadoop, HDFS and Apache server*, *Tableau* and
*Impala server*. Both Python and R are therefore arguable.

**Decision**
Implement in **Python 3.12**.

**Rationale**
* Anaconda, PyCharm and VS Code are Python-first tools; R appears only as
  RStudio.
* The Hadoop/Impala ecosystem is driven from Python in practice (PySpark,
  `impala-shell`, `hdfs dfs` subprocess integration).
* The machine-learning requirement (performance, dropout and course-demand
  prediction) maps directly onto the Python scientific stack.
* Python is already the assumed language for a VS Code / PyCharm project.

**Consequences**
* R is not used. If a phase genuinely needs R, that is a separate decision.
* The documented Anaconda distribution is compatible; a plain CPython
  interpreter is sufficient for the current phase.

---

## ADR-0002 - Flask as the web framework

**Status:** Accepted (Phase 1)

**Context**
The deliverables require "a video clip demonstrating the working of the
**Website**" and optionally a hosted URL. No framework is named. The
application must stay modular so auth, ingestion, HDFS processing, ML,
visualization, alerts and support can be added later.

**Options considered**

| Option | Verdict |
|---|---|
| **Flask** | Chosen. Smallest framework that is sufficient; blueprint-per-module fits the required modularity; widely understood. |
| FastAPI | Rejected for now. Async, Pydantic models and an OpenAPI contract are capabilities the project has no documented requirement for yet. |
| Django | Rejected. ORM, admin site and URL conf add structure the project does not need, and would be a second architecture to justify. |
| No framework, HTTP server only | Rejected. The document explicitly requires a website. |

**Decision**
Use **Flask 3.x** with a single blueprint per module area
(`web/routes.py` today), registered by the application factory.

**Consequences**
* Only one third-party runtime dependency.
* A production WSGI server (for example Waitress or gunicorn) will be needed
  before the 99% uptime requirement can be met. Deferred to a deployment phase.

---

## ADR-0003 - Configuration is layered TOML plus environment variables

**Status:** Accepted (Phase 1)

**Context**
The project must be configurable without code edits, and the host will differ
between a developer laptop and a Hadoop cluster.

**Decision**
Layered configuration: dataclass defaults, then `config/settings.toml`, then
`EDUPREDICT_<SECTION>__<KEY>` environment variables, then CLI flags. Parsed with
`tomllib` from the standard library.

**Rationale**
* TOML is typed, commented and needs no extra dependency.
* Environment variables are the standard way to inject per-host settings such as
  the NameNode URI.
* Strict validation (unknown key, wrong type, malformed file) raises
  `ConfigurationError` rather than silently using a default.

**Consequences**
* No `.env` loader is included. Use real environment variables; secrets are not
  stored in the repository.
* A secret store will be needed when credentials are introduced in the auth
  phase.

---

## ADR-0004 - Open: how Impala will be integrated

**Status:** **Open** - to be decided in the analytics phase

**Context**
The document requires an Impala server, and the analytics requirement needs
pattern, anomaly and correlation analysis. Phase 1 only probes Impala.

**Decision**
Deferred. Do not choose a driver before the analytics workload is specified.

**Options to weigh then**
* `impala-shell` via subprocess - already proven in Phase 1, but poor for
  parameterised, high-volume queries.
* Impala daemon protocol / Thrift client - correct for production analytics,
  needs a maintained client library.
* ODBC driver - familiar, but adds a native Windows dependency.

**Blocked on**
Impala not being installed, and the concrete analytics queries not being defined.

---

## ADR-0005 - Open: the role of MongoDB

**Status:** **Open** - to be decided in the auth / support phase

**Context**
The document lists "Mongo Db Compass, and Shell" in its software requirements,
but never states what MongoDB is meant to store. HDFS is explicitly the store
for large educational datasets, and Impala is the SQL engine over it.

**Decision**
Deferred. No MongoDB code, driver or configuration has been added.

**Candidate uses to evaluate later**
* User accounts and role assignments for the auth module.
* Feedback and support tickets (naturally document-shaped).
* Anything requiring the dataset itself - that belongs in HDFS, not MongoDB.

**Blocked on**
The auth and support modules being specified.

---

## ADR-0006 - HDFS is accessed through the native CLI

**Status:** Accepted (Phase 1)

**Context**
Hadoop is already installed on this machine. A Python HDFS library
(`pyarrow`, `pyhdfs`, `hdfs3`, `fsspec`) would need native components and is
notoriously fragile on Windows.

**Decision**
Wrap `hdfs dfs` via `subprocess` behind an `HdfsClient` protocol in
`storage/hdfs.py`.

**Rationale**
* Zero additional dependencies.
* Uses the Hadoop distribution the document requires.
* The protocol allows a different backend later without changing callers.

**Consequences**
* Output is text and must be parsed.
* This is a deliberate trade-off of throughput for reliability on Windows.
  Revisit if the storage phase shows the CLI cannot meet the latency
  requirement.

---

## ADR-0007 - Health checks report the truth

**Status:** Accepted (Phase 1)

**Context**
The document's non-functional requirements ask for monitoring, and the Phase 1
instructions forbid faking infrastructure connections.

**Decision**
`/health` probes HDFS and Impala for real and returns `503` when any component
is degraded. A missing component is always accompanied by a human-readable
reason.

**Consequences**
* Out of the box the report is `warn`, because Hadoop and Impala are not running
  on a fresh machine. This is correct, not a defect.
* `python -m edupredict check` shows the same information on the console.

---

## ADR-0008 - Reserved modules are empty on purpose

**Status:** Accepted (Phase 1)

**Context**
The architecture must already show the separation between auth, ingestion,
storage, processing, streaming, analytics, ML, visualization, notifications and
support, without implementing their business logic.

**Decision**
Create each package containing only a docstring that names the documented
requirement it will satisfy. No placeholder classes, no stub functions, no
`pass`-only "not implemented" code paths.

**Rationale**
Empty-but-labelled packages make the target architecture visible and give later
phases an obvious home, while writing no code that could be mistaken for a
finished feature.

---

## ADR-0009 - Authentication mechanism and role model

**Status:** Accepted (Phase 2)

**Context**
`Big Data-EduPredict.docx` requires "a secure authentication system for users
with different roles, such as administrators, teachers, students, and analysts"
and "access controls to restrict data access based on user roles and
responsibilities". It names no framework, no hashing scheme and no session
technology. The project already runs on Flask 3 with a deliberately minimal
dependency set.

**Decision**
Implement authentication directly on Flask, using `werkzeug.security` for
password hashing and a small `AuthenticationService`. Model the four documented
roles as a `Role` enum. Provide two Flask decorators, `@login_required` and
`@roles_required(...)`, as the authorization mechanism.

**Options considered**

| Option | Pros | Cons |
|---|---|---|
| **Own implementation on Flask + Werkzeug (chosen)** | No new dependency; complete control over session and error handling; fits the existing architecture | More code to review and test |
| Flask-Login | Mature, well known | A new dependency for roughly a page of logic; session behaviour is not configurable to this project's needs |
| Authlib / OAuthlib | Federation and social login | Solves a problem the document does not have; scope explicitly excludes social login |
| A separate identity server | Enterprise-grade | Far beyond an eProject; needs infrastructure that is not available |

**Consequences**
* Passwords are hashed with scrypt via Werkzeug, which is already a hard
  dependency of Flask. `werkzeug` is now declared explicitly in
  `pyproject.toml` because the project imports it directly.
* The login, lockout and role logic is testable without HTTP.
* Guard behaviour (redirect vs. 401, HTML vs. JSON) is decided in one place.
* `edupredict/auth/` never imports Flask, preserving the layering rule in
  `ARCHITECTURE.md`.

---

## ADR-0010 - SQLite as the authentication store

**Status:** Accepted (Phase 2)

**Context**
The document requires user accounts with roles but specifies no database. It
lists "Mongo Db Compass, and Shell" among the software, without saying what it
is used for.

**Decision**
Store accounts in **SQLite** through the standard library `sqlite3` module, in
a single file at `var/auth/users.db`, behind a `UserStore` Protocol.

**Options considered**

| Option | Pros | Cons |
|---|---|---|
| **SQLite via `sqlite3` (chosen)** | Zero new dependencies; transactional; one file; part of CPython | Single-writer; no network access |
| JSON file | Simplest possible | No transactions, no unique constraint, hash comparisons in application code, easy to corrupt |
| MongoDB | Listed in the document's software | Requires a running server; the document never states it stores users, so adopting it here would be an unjustified inference |
| SQLAlchemy + PostgreSQL | Production-grade | Two new dependencies plus a server; disproportionate for four roles and a handful of accounts |

**Consequences**
* Accounts survive a restart, which a JSON file would not guarantee safely.
* Swapping the backend later means implementing `UserStore`; only
  `build_user_store()` knows the concrete class.
* The database is created on first use, so a fresh checkout needs no migration
  step.
* `var/` is git-ignored, so the account database is never committed.

---

## ADR-0011 - Session security, CSRF and secret-key handling

**Status:** Accepted (Phase 2)

**Context**
The document's Data Security requirement asks for protection of data "during
storage and transmission". Flask's default session is a client-side signed
cookie, and no key may be committed to the repository.

**Decision**
* Read the signing key from `[auth] secret_key`, expected to arrive through
  `EDUPREDICT_AUTH__SECRET_KEY`. The committed value is empty.
* If no key is configured, generate an ephemeral random key **only** in
  `development` / `testing` / `local`, log a warning, and let sessions die on
  restart. In any other environment, raise `ConfigurationError`.
* Reject a configured key shorter than 32 characters.
* Harden the cookie: `HttpOnly`, `SameSite=Lax`, `Secure` configurable.
* Protect every state-changing POST with a per-session CSRF token compared with
  `hmac.compare_digest`.
* Store only the numeric user id in the session; re-read the role from the store
  on every request.

**Consequences**
* A fresh checkout runs without setup, while a deployment is forced to supply a
  real key.
* The cookie contains no role and no password material, so a role change applies
  immediately and a deleted account loses access at once.
* Sign-out clears the whole session, and logout is POST-only so it cannot be
  triggered from another site.

---

## ADR-0012 - Accounts are provisioned from the command line

**Status:** Accepted (Phase 2)

**Context**
Authentication needs accounts, but the document describes no sign-up flow, and
shipping default accounts would mean committing credentials.

**Decision**
Add `edupredict user create` and `edupredict user list`. `create` reads the
password from a hidden prompt (or `--password-stdin` for automation), never from
`argv`, and never stores it in plaintext. No account is created automatically at
startup, and no credential is committed.

**Consequences**
* The repository contains no working credential.
* Account creation requires filesystem access to the machine, which is
  appropriate for an operator-provisioned system.
* Bootstrap on a fresh machine is two commands: set the key, create an
  administrator.

---

## ADR-0013 - Role-based guards, and an empty permission registry

**Status:** Accepted (Phase 2)

**Context**
The document requires access to be "restrict[ed] ... based on user roles and
responsibilities" but never states what any role may do. Inventing a permission
matrix would fabricate requirements.

**Decision**
Enforce **role membership** with `@roles_required(...)`, which is what the
document states, and ship a `PermissionRegistry` that is **empty**. The
dashboard and admin page display the note that detailed role permissions are not
specified in the source document and will be defined when the corresponding
functional modules are implemented.

**Consequences**
* No permission is asserted that the document does not support.
* Later phases add capabilities with a single `REGISTRY.define(...)` call.
* Checking an undefined permission raises `AuthorizationError` rather than
  returning `False`, so a typo cannot silently deny access.
