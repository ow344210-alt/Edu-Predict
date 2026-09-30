# EduPredict - Architecture

Phase 1 established the module skeleton and the layer rules. Phase 2 filled in
the authentication and authorization layer without changing those rules.

---

## 1. Design goals

1. **Traceability to the document.** Every package maps to a documented
   functional requirement, so later phases have an obvious home.
2. **Honest infrastructure state.** A missing Hadoop or Impala install is
   reported as `unavailable` with a reason. The application never pretends a
   connection succeeded. The same rule applies to scope: the application never
   pretends a future module exists.
3. **Minimal dependencies.** Only Flask and Werkzeug are required at runtime -
   Werkzeug already ships with Flask, and the project imports it directly for
   password hashing. Configuration parsing, logging, health checks and account
   storage all use the standard library.
4. **Testability.** The application is built by a factory function, so tests get
   a configured app without starting a server.

---

## 2. Layer model

```text
                    +----------------------------------+
                    |        Presentation / HTTP       |
                    |  web.routes | web.auth_routes     |
                    |  web.auth_guards | Jinja2          |
                    +----------------------------------+
                    |        Application assembly      |
                    |  edupredict.app.create_app()     |
                    +----------------------------------+
                    |        Cross-cutting concerns     |
                    |  config | logging | errors | health|
                    +----------------------------------+
                    |        Domain modules             |
                    |  auth (roles, passwords, users,  |
                    |  permissions, service)           |
                    |  ingestion | processing           |
                    |  streaming | analytics | ml       |
                    |  visualization | notifications  |
                    |  | support                       |
                    +----------------------------------+
                    |        Infrastructure adapters   |
                    |  storage.hdfs | storage.impala   |
                    +----------------------------------+
                    |        External systems           |
                    |  HDFS / NameNode | Impala server  |
                    +----------------------------------+
```

Dependencies point **downward only**. A domain module may use
`config`/`logging`/`health`; it may not import Flask. Only `web/` and
`app.py` know that a web framework exists.

This rule is load-bearing, not decorative. `edupredict.auth` contains the
`Role` enum, the password hasher, the `UserStore` and the
`AuthenticationService`, and **none of them import Flask** - which is why they
can be tested directly and would still work behind a CLI or a batch job. The
framework-aware parts (`@login_required`, `@roles_required`, CSRF, the session
helpers) live in `web/auth_guards.py`; the HTTP endpoints live in
`web/auth_routes.py`.

### 2.1 Authentication request flow

```text
Browser
  |
  v
web.auth_routes.login                    # HTTP concern
  +-- web.auth_guards.verify_csrf()      # session concern
  v
auth.AuthenticationService.authenticate  # domain concern, no Flask
  +-- auth.users.UserStore.get_by_username()
  +-- auth.passwords.verify_password()   # werkzeug scrypt
  v
User
  |
  v
web.auth_guards.login_user()             # session["uid"] = user.id
```

The session holds only the integer id. Every later request re-reads the `User`
from the store, so a role is never stale and no credential material is ever
written to a client-readable cookie.

---

## 3. Request flow

```text
Browser / monitor
      |
      v
edupredict.__main__.main()          # parse args, load Settings, setup logging
      |
      v
edupredict.app.create_app()        # build Flask app, register blueprint
      |
      v
edupredict.web.routes.index()  or  .health()
      |
      +--> health.build_health_report(settings)
      |        |
      |        +--> runtime check        (interpreter, OS)
      |        +--> configuration check  (which settings file was loaded)
      |        +--> storage.hdfs.HadoopCliClient.probe()    -> hdfs dfs -ls
      |        +--> storage.impala.ImpalaClient.probe()    -> TCP + impala-shell
      |
      v
HTML page / JSON report
```

`/health` maps the aggregated status to an HTTP code: `200` when everything is
`ok`, `503` when any component is degraded. This makes the endpoint directly
usable by an uptime monitor.

---

## 4. Configuration flow

```text
dataclass defaults
      +
config/settings.toml
      +
EDUPREDICT_<SECTION>__<KEY> environment variables
      +
command line flags
      |
      v
edupredict.config.Settings  (frozen dataclasses)
      |
      +--> app.py       (host, port, debug)
      +--> logging_setup (level, target, file)
      +--> auth         (database_path, secret_key, session_lifetime,
      |                  csrf_protection, lockout, cookie_secure)
      +--> storage.hdfs (namenode_uri, hadoop_home, base_path)
      +--> storage.impala (host, port, database)
```

Design notes:

* Settings are **frozen dataclasses**, so a component cannot mutate shared
  configuration at runtime.
* Values coming from the environment are strings; `_coerce` converts them using
  the type of the dataclass default, so `EDUPREDICT_APP__PORT=8080` yields the
  integer `8080`.
* `bool` is tested before `int` because `bool` is a subclass of `int`.
* An unknown section or key raises `ConfigurationError` - a typo must not be
  silently ignored.

---

## 5. Error handling

```text
Exception
   |
   +-- EduPredictError ........... domain errors, HTTP 500 + JSON
   |     +-- ConfigurationError
   |     +-- InfrastructureError
   |     |     +-- HdfsUnavailableError
   |     |     +-- ImpalaUnavailableError
   |     +-- NotImplementedYetError
   |     +-- AuthenticationError .......... login/credential problems
   |     |     +-- AccountLockedError
   |     |     +-- UnknownRoleError
   |     |     +-- UserAlreadyExistsError
   |     +-- AuthorizationError ........... role checks, undefined permissions
   |
   +-- HTTPException ............. Flask/Werkzeug errors, original code
   |                               (401/403 render HTML for browsers,
   |                                JSON for API clients)
   |
   +-- Exception ................. anything unexpected, HTTP 500 + generic JSON
```

The catch-all handler logs the traceback server-side and returns a generic
message to the client. This satisfies the document's data-security requirement
by not leaking internal details over HTTP.

Two deliberate refinements in Phase 2:

* **401 and 403 render HTML for browsers.** Every other HTTP error still returns
  JSON. A person clicking a link should get a page, not a JSON blob, while a
  monitoring client must still receive a machine-readable body. The status code
  is identical either way, so `401`/`403` stay machine-detectable.
* **Authentication failures never reach this handler.** A wrong password is a
  normal outcome, not an exception: the login view re-renders with a generic
  message and the same HTTP 200, so the endpoint cannot be used to distinguish a
  valid username from an invalid one.

---

## 6. HDFS integration approach

The document requires HDFS. Two integration options were considered:

| Option | Pros | Cons |
|---|---|---|
| **Native `hdfs dfs` CLI** (chosen) | No native Python libraries, works with the Hadoop already installed, no JNI/Windows binary problems | Text output must be parsed |
| `pyarrow` / `pyhdfs` / `hdfs3` | Programmatic API | Native dependencies, frequently broken on Windows |

`storage/hdfs.py` therefore wraps the CLI and exposes a `HdfsClient` protocol
that a different backend could implement later without touching callers.

The probe performs three genuine checks:

1. Is the `hdfs` client on `PATH` or in `HADOOP_HOME`?
2. Is `JAVA_HOME` set and does `JAVA_HOME/bin/java` exist? (The Hadoop shell
   scripts refuse to start otherwise.)
3. `hdfs dfs -ls <base_path>` - does the NameNode answer?

A missing base directory is reported as *"NameNode reachable; base path not
created yet"*, which is distinct from *"Hadoop not installed"*.

---

## 7. Impala integration approach

`storage/impala.py` performs a TCP connect to the Impala daemon and, if that
succeeds, verifies the configured database with `impala-shell`. The choice
between `impala-shell` and a production driver for the analytics phase is
recorded as **ADR-0004** - it must be decided when the analytics module is
built, not guessed now.

---

## 8. Module map

| Package | Documented requirement | Status |
|---|---|---|
| `auth` | Authentication and Authorization | **Implemented (Phase 2)**: `Role` (4 documented roles), scrypt password hashing, `UserStore` Protocol + SQLite implementation, `AuthenticationService` with lockout, and an intentionally empty `PermissionRegistry`. No Flask import. |
| `ingestion` | Data Ingestion | Package reserved. Sources: academic records, demographics, LMS, attendance; historical and real-time. |
| `storage` | Data Storage | **Implemented**: HDFS client contract + probe, Impala probe. `base_path` reserves the HDFS layout. |
| `processing` | Data Processing (batch) | Package reserved for parallel batch jobs. |
| `streaming` | Real-Time Processing | Package reserved for the streaming consumer and its batch bridge. |
| `analytics` | Patterns, anomalies, correlations | Package reserved; will consume `storage.impala`. |
| `ml` | Machine Learning Models | Package reserved; will consume processed features. |
| `visualization` | Data Visualization | Package reserved; `web/templates` is the only view layer today. |
| `notifications` | Notifications and Alerts | Package reserved; will consume thresholds from `config`. |
| `support` | Feedback and Support | Package reserved. |

---

## 9. Extending the project

Later phases should follow the same pattern:

1. Implement the logic inside its own reserved package.
2. Add configuration under a new section in `config/settings.toml` (add the
   matching dataclass in `config.py`).
3. Register routes on a blueprint inside `web/`, not on the app object.
4. Add a health probe if the module talks to external infrastructure.
5. Add tests under `tests/`.

This keeps each phase independently testable and keeps the domain logic free of
framework concerns.
