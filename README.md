# EduPredict

**Educational Big Data and Predictive Analytics System**

EduPredict is the implementation of the project described in
`Big Data-EduPredict.docx`. It helps education institutions address declining
student retention, inefficient resource allocation and the need to personalise
learning, by applying Hadoop-based big data processing and predictive analytics
to academic records, student demographics, LMS data and attendance records.

> **Phase 2 - Web surface, authentication and authorization.**
> This repository contains the application foundation **plus** a working
> authentication system with the four documented roles and enforced role-based
> access control. **No dataset, machine learning model, dashboard or data
> pipeline has been implemented yet.** See
> [Project Status](#project-status), [`docs/AUTHENTICATION.md`](docs/AUTHENTICATION.md)
> and [`docs/PHASES.md`](docs/PHASES.md).

---

## Purpose

Built strictly from the requirements document. The documented functional areas
are:

| Area | Documented requirement | Status |
|---|---|---|
| Authentication & Authorization | Secure login, roles (Administrator, Teacher, Student, Analyst), role-based access control | **Implemented** (Phase 2) |
| Data Ingestion | Academic records, demographics, LMS, attendance; historical + real-time | Reserved |
| Data Storage | HDFS, scalable, fault tolerant, partitioned | Probe only |
| Data Processing | Parallel processing, patterns, anomalies, correlations, missing data | Reserved |
| Real-Time Processing | Streaming integrated with batch | Reserved |
| Machine Learning | Performance, dropout, course demand, anomaly detection, trend prediction, model refinement | Reserved |
| Data Visualization | Interactive dashboards, key metrics, patterns, anomalies, predictions | Reserved |
| Notifications & Alerts | Automated, threshold-based, configurable, real-time | Reserved |
| Feedback & Support | Contact support, report issues, provide feedback | Reserved |

Non-functional requirements (performance, security, data integrity, reliability,
scalability, monitoring, compliance, documentation) shaped the foundation:
structured logging, layered configuration, a machine-readable health endpoint
and centralised error handling.

---

## Technology Stack

| Technology | Version | Why it was chosen |
|---|---|---|
| **Python** | 3.12 | The document names *Jupyter Anaconda Notebook*, *PyCharm* and *VS Code* - a Python-centric data-science toolchain. Hadoop, Impala and the ML stack are all driven from Python. *(Language decision - see ADR-0001.)* |
| **Flask** | 3.x | The document requires a "Website" deliverable but names no framework. Flask is the simplest appropriate web framework for this ecosystem - minimal, well understood, and it does not impose an async/data-model stack the project does not need. *(ADR-0002.)* |
| **Werkzeug** | 3.x | Ships with Flask; imported directly in Phase 2 for `scrypt` password hashing and cookie signing. No new dependency was introduced. *(ADR-0009.)* |
| **Jinja2** | 3.x | Ships with Flask; renders the status, login, dashboard, admin and error pages. |
| **pytest** | 9.x | Test runner for the verification suite. |
| **tomllib** (stdlib) | 3.11+ | TOML configuration parsing with no extra dependency. |
| **sqlite3** (stdlib) | CPython | Account storage for authentication. Transactional, single file, no server. *(ADR-0010.)* |
| **Hadoop HDFS** | 3.x (installed at `C:\hadoop`) | Explicitly required by the document as the system of record. Integrated through the native `hdfs dfs` CLI so no native Python libraries are needed. |
| **Impala** | server-side | Listed in the document's software requirements; the SQL engine for data held in HDFS. Probe implemented, integration deferred (ADR-0004). |
| **Jupyter / Anaconda, RStudio, MongoDB, Tableau** | not installed in Phase 1 | Named in the document. No code depends on them yet, so they are not required to run the foundation. See [`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md). |

**Runtime third-party dependencies: Flask and Werkzeug.** Werkzeug is already a
hard dependency of Flask and is declared explicitly because the project imports
`werkzeug.security` directly. Everything else is the Python standard library, the
Hadoop/Impala command line clients, or the OS. No authentication framework, no
ORM and no database server were added.

---

## Project Structure

```text
EduPredict/
|-- pyproject.toml               # packaging, dependencies, pytest config
|-- README.md                    # this file
|-- .gitignore
|
|-- config/
|   `-- settings.toml            # the single configuration file (TOML)
|
|-- docs/
|   |-- ARCHITECTURE.md          # layers, request flow, module map
|   |-- AUTHENTICATION.md        # auth architecture, flow, roles, security
|   |-- ENVIRONMENT.md           # required software + Hadoop/HDFS/Impala setup
|   |-- DECISIONS.md             # numbered architecture decision records
|   |-- PHASES.md                # what is done now vs. reserved for later
|   `-- Big Data-EduPredict.docx # the requirements document (unmodified)
|
|-- src/
|   `-- edupredict/
|       |-- __init__.py          # package metadata
|       |-- __main__.py          # CLI (serve / check / version / user)
|       |-- app.py               # application factory + error handlers
|       |-- config.py            # layered settings loading
|       |-- errors.py            # exception hierarchy
|       |-- logging_setup.py     # logging configuration
|       |-- health.py            # component health report
|       |
|       |-- web/                 # HTTP layer (the only Flask-aware layer)
|       |   |-- __init__.py
|       |   |-- routes.py        # / and /health
|       |   |-- auth_routes.py   # /auth/login|logout|dashboard|admin
|       |   |-- auth_guards.py   # login_required, roles_required, CSRF
|       |   |-- responses.py     # content negotiation
|       |   `-- templates/
|       |       |-- base.html
|       |       |-- index.html
|       |       |-- login.html
|       |       |-- dashboard.html
|       |       |-- admin.html
|       |       `-- error.html
|       |
|       |-- auth/                # AUTHENTICATION & AUTHORIZATION (no Flask)
|       |   |-- __init__.py      # public API
|       |   |-- roles.py         # the four documented roles
|       |   |-- passwords.py     # scrypt hashing / verification
|       |   |-- users.py         # User, UserStore protocol, SQLite store
|       |   |-- service.py       # credential checking + lockout
|       |   `-- permissions.py   # permission registry (empty by design)
|       |
|       |-- storage/             # DATA STORAGE
|       |   |-- __init__.py
|       |   |-- hdfs.py          # HDFS client contract + real availability probe
|       |   `-- impala.py        # Impala availability probe
|       |
|       |-- ingestion/           # RESERVED: data ingestion
|       |-- processing/          # RESERVED: batch processing
|       |-- streaming/           # RESERVED: real-time processing
|       |-- analytics/           # RESERVED: pattern/anomaly/correlation analysis
|       |-- ml/                  # RESERVED: machine learning models
|       |-- visualization/       # RESERVED: dashboards
|       |-- notifications/       # RESERVED: alerts & notifications
|       `-- support/             # RESERVED: feedback & support
|
`-- tests/
    |-- conftest.py              # shared fixtures
    |-- test_config.py           # configuration loading
    |-- test_errors.py           # exception hierarchy
    |-- test_health.py           # health report
    |-- test_storage.py          # HDFS / Impala probes
    |-- test_web.py              # HTTP surface + error handling
    |-- test_cli.py              # command line entry point
    |-- test_auth.py             # roles, hashing, store, service
    |-- test_auth_web.py         # login, session, role boundaries
    `-- test_auth_security.py    # CLI provisioning, secrets, CSRF
```

Each `RESERVED` package exists only to establish the module boundary required by
the architecture. **It contains a docstring and nothing else - no business
logic has been written for those areas.**

Runtime output (created automatically, git-ignored):

```text
|-- logs/edupredict.log          # rotating application log
`-- var/                         # local working root
    `-- auth/users.db            # SQLite account store (created on first use)
```

---

## Quick Start

### Requirements

* Python 3.11 or newer (3.12 recommended)
* Optional for the foundation: Hadoop + a JDK, and Impala. Without them the
  application still starts and the health report marks those components
  `unavailable` with the reason.

### Install

```bash
cd EduPredict
python -m pip install -e ".[dev]"
```

### Set a session signing key (recommended)

The committed configuration ships an **empty** `secret_key` so that no secret is
ever stored in the repository. In development the application generates an
ephemeral key and logs a warning; sessions then stop working when the process
restarts. To keep sessions across restarts, set a real key through the
environment:

```bash
# PowerShell
$env:EDUPREDICT_AUTH__SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
```

### Create an account

Accounts are provisioned from the command line. The password is prompted
without echo, so it never appears in shell history, a process listing or a CI
log. **No credential is committed to this repository.**

```bash
python -m edupredict user create admin.user   --role administrator
python -m edupredict user create teacher.one  --role teacher
python -m edupredict user create student.one  --role student
python -m edupredict user create analyst.one  --role analyst

# Review the accounts (never shows password hashes)
python -m edupredict user list
```

### Run

```bash
# Start the web application
python -m edupredict serve
#   or override the bind address
python -m edupredict serve --host 0.0.0.0 --port 8080

# Verify the installation and infrastructure
python -m edupredict check
python -m edupredict check --json

# Version
python -m edupredict version
```

After `pip install -e .` the same commands are available as `edupredict serve`,
`edupredict check`, `edupredict version`, `edupredict user create` and
`edupredict user list`.

Open <http://127.0.0.1:5000/> for the status page,
<http://127.0.0.1:5000/auth/login> to sign in, and
<http://127.0.0.1:5000/health> for the JSON health report.

### Test

```bash
python -m pytest

# Authentication tests only
python -m pytest tests/test_auth.py tests/test_auth_web.py tests/test_auth_security.py
```

---

## Configuration

Configuration is layered. Later layers win:

1. **Built-in defaults** - `src/edupredict/config.py`
2. **`config/settings.toml`** - the project configuration file
3. **Environment variables** - `EDUPREDICT_<SECTION>__<KEY>`
4. **Command line flags** - `--host`, `--port`, `--debug`, `--log-level`, `--config`

```bash
# Windows PowerShell
$env:EDUPREDICT_APP__PORT = "8080"
$env:EDUPREDICT_HDFS__ENABLED = "false"
python -m edupredict check
```

| Section | Key | Default | Purpose |
|---|---|---|---|
| `app` | `name` | `EduPredict` | Display name |
| `app` | `environment` | `development` | Environment label |
| `app` | `host` / `port` | `127.0.0.1` / `5000` | Bind address |
| `app` | `debug` | `false` | Flask debug mode |
| `logging` | `level` | `INFO` | Log level |
| `logging` | `target` | `both` | `console`, `file`, `both`, `none` |
| `logging` | `file` | `logs/edupredict.log` | Log file path |
| `hdfs` | `enabled` | `true` | Enable the HDFS probe |
| `hdfs` | `namenode_uri` | `hdfs://localhost:9000` | NameNode address |
| `hdfs` | `hadoop_home` | `""` | Blank = auto-detect from `HADOOP_HOME` / PATH |
| `hdfs` | `base_path` | `/user/edupredict` | Root for the educational dataset |
| `impala` | `enabled` | `true` | Enable the Impala probe |
| `impala` | `host` / `port` | `localhost` / `21050` | Impala daemon address |
| `impala` | `database` | `edupredict` | Target database |
| `storage` | `local_root` | `var` | Local working root |
| `auth` | `database_path` | `var/auth/users.db` | SQLite file holding accounts |
| `auth` | `secret_key` | `""` | Session signing key. **Empty in the repository - set `EDUPREDICT_AUTH__SECRET_KEY`** |
| `auth` | `session_lifetime_minutes` | `60` | Session lifetime |
| `auth` | `csrf_protection` | `true` | Require a CSRF token on POST |
| `auth` | `max_login_failures` / `lockout_seconds` | `5` / `300` | Account lockout after repeated failures |
| `auth` | `cookie_secure` | `false` | Set `true` when served over HTTPS |
| `auth` | `max_content_length` | `16384` | Max request body (bytes) |

Invalid configuration (bad TOML, unknown key, wrong type) raises
`ConfigurationError` and the CLI exits with status `1` instead of starting with
silent defaults.

---

## HTTP Endpoints

### Public

| Method | Path | Purpose | Response |
|---|---|---|---|
| `GET` | `/` | Status page; shows who is signed in | `200` HTML |
| `GET` | `/health` | Machine-readable health report | `200` when all components are healthy, otherwise `503` |
| `GET` | `/auth/login` | Sign-in form | `200` HTML |
| `POST` | `/auth/login` | Credential check (CSRF required) | `302` on success, `200` with an error message on failure |

### Authenticated

| Method | Path | Guard | Response |
|---|---|---|---|
| `GET` | `/auth/dashboard` | any signed-in role | `200` HTML, else `302` → login (browser) or `401` (API) |
| `POST` | `/auth/logout` | CSRF required | `302` → `/` |
| `GET` | `/auth/admin` | **Administrator only** | `200` HTML, `302`/`401` if anonymous, `403` if signed in with another role |

```bash
curl http://127.0.0.1:5000/health

# Anonymous -> 302 to the login form
curl -i http://127.0.0.1:5000/auth/dashboard

# Anonymous API client -> 401 JSON
curl -i -H "Accept: application/json" http://127.0.0.1:5000/auth/dashboard
```

`/health` returns `503` when Hadoop or Impala is missing. This is intentional:
the endpoint is designed for an external monitor and must never report a
component as healthy when it is not.

See [`docs/AUTHENTICATION.md`](docs/AUTHENTICATION.md) for the full flow,
security controls and manual verification steps.

---

## Project Status

**The final dataset has NOT been created in this phase.** No dataset collection,
cleaning, transformation, generation or import has been performed.

**Implemented now:** project packaging, layered configuration, logging, error
handling, HDFS/Impala availability probes, a health report, a CLI, and a working
authentication and authorization layer - four documented roles, scrypt password
hashing, a SQLite account store, session hardening, CSRF protection and
role-enforced routes.

**Reserved for later phases:** data ingestion, the HDFS data pipeline, batch
processing, real-time streaming, analytics, machine learning, dashboards,
notifications and alerts, feedback and support, deployment.

**Known environment blockers (unchanged, not part of this phase):** Hadoop on
Windows needs `winutils.exe`, no NameNode is running, and Impala is not
installed. `python -m edupredict check` reports these as `unavailable` with the
reason rather than hiding them. See
[`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md).

See [`docs/PHASES.md`](docs/PHASES.md) for the full breakdown,
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the design,
[`docs/AUTHENTICATION.md`](docs/AUTHENTICATION.md) for the authentication design
and [`docs/DECISIONS.md`](docs/DECISIONS.md) for the decision records.

---

## Scope Statement

No product features beyond the requirements of `Big Data-EduPredict.docx` have
been added. RStudio, MongoDB, Tableau and Jupyter are named in the document but
are not yet wired in, because no implemented module requires them. MongoDB was
specifically **not** adopted for authentication: the document lists the tool
without stating what it stores, so using it for accounts would be an invented
requirement.
