# Phases

What is done, and what is deliberately reserved. Nothing in the "reserved"
column exists yet beyond an empty, labelled package.

> **Phase numbering note.** The original plan made Phase 2 the
> environment/infrastructure phase and Phase 4 the authentication phase. The
> project was re-sequenced by explicit instruction: authentication, roles and
> the web surface were delivered as **Phase 2**, and the environment work moved
> to **Phase 3**. The original plan is preserved below under its new number so
> no work is lost from the roadmap.

---

## Phase 1 - Foundation (complete)

| Item | Status | Where |
|---|---|---|
| Project packaging and dependency management | Done | `pyproject.toml` |
| Layered configuration (TOML + environment + CLI) | Done | `config/settings.toml`, `src/edupredict/config.py` |
| Logging with console + rotating file output | Done | `src/edupredict/logging_setup.py` |
| Exception hierarchy and centralised error handling | Done | `src/edupredict/errors.py`, `src/edupredict/app.py` |
| Application factory and CLI entry point | Done | `src/edupredict/app.py`, `src/edupredict/__main__.py` |
| HDFS client contract + real availability probe | Done | `src/edupredict/storage/hdfs.py` |
| Impala availability probe | Done | `src/edupredict/storage/impala.py` |
| Component health report (runtime, config, HDFS, Impala) | Done | `src/edupredict/health.py` |
| Web surface: `GET /` and `GET /health` | Done | `src/edupredict/web/` |
| Test suite (49 tests) | Done | `tests/` |
| Documentation | Done | `README.md`, `docs/` |
| Reserved module packages for later phases | Done | `src/edupredict/{auth,ingestion,...}` |

**Not done in Phase 1, by instruction:** dataset, ML models, dashboards,
authentication, authorization, real-time streaming, HDFS data pipeline,
analytics, notifications, support workflows, deployment.

---

## Phase 2 - Web surface, authentication and authorization (complete)

**Goal:** the four documented roles with genuinely enforced access control.

| Item | Status | Where |
|---|---|---|
| Four documented roles as an enum (Administrator, Teacher, Student, Analyst) | Done | `src/edupredict/auth/roles.py` |
| scrypt password hashing, no plaintext anywhere | Done | `src/edupredict/auth/passwords.py` |
| Account store behind a `UserStore` Protocol (SQLite) | Done | `src/edupredict/auth/users.py` |
| Authentication service with lockout and timing-equalised failures | Done | `src/edupredict/auth/service.py` |
| Permission registry, deliberately empty | Done | `src/edupredict/auth/permissions.py` |
| Role guards `@login_required` / `@roles_required` | Done | `src/edupredict/web/auth_guards.py` |
| Routes: login, logout, dashboard, admin | Done | `src/edupredict/web/auth_routes.py` |
| Session hardening, CSRF, safe redirect targets | Done | `src/edupredict/app.py`, `web/auth_guards.py` |
| `edupredict user create` / `user list` (no committed credentials) | Done | `src/edupredict/__main__.py` |
| Test suite (194 tests) | Done | `tests/` |
| Documentation | Done | `docs/AUTHENTICATION.md`, ADRs 0009-0013 |

**Not done in Phase 2, by instruction:** datasets, ingestion, HDFS pipeline,
batch/real-time processing, analytics, ML, Tableau dashboards, notifications,
support, deployment, video.

**Open items carried forward:** ADR-0004 (Impala integration method) and
ADR-0005 (the role of MongoDB) remain open. ADR-0005 is now lower priority:
the authentication store is SQLite and the document never states that MongoDB
holds users.

---

## Phase 3 - Environment and infrastructure (next)

**Goal:** a real, reachable cluster so later phases have a target.

* Install/verify the JDK and the Hadoop CLI.
* Start a local HDFS (single-node or Docker Compose) and confirm
  `hdfs dfs -ls /` answers.
* Create the EduPredict HDFS layout under `/user/edupredict` and record the
  partitioning strategy the document asks for.
* Install Impala (server + `impala-shell`) and create the `edupredict` database.
* Close **ADR-0004** (Impala integration method) now that the server exists.
* Re-run `edupredict check` until HDFS and Impala report `ok`.

---

## Phase 4 - Dataset

**Goal:** the educational dataset exists, is documented, and is stored in HDFS.

> Deferred. Phase 2 delivered authentication instead, and this phase cannot
> begin until the Phase 3 cluster is reachable - storing a dataset in HDFS
> requires a running NameNode.

* Agree the schema: academic records, student demographics, LMS activity,
  attendance.
* Source or generate the data; do not fabricate a large fake dataset without an
  explicit decision.
* Handle missing and incomplete data, as the document requires.
* Load into HDFS under the agreed partitioning.
* Produce a data dictionary and a dataset quality report.

---

## Phase 5 - Data ingestion, batch and real-time processing

**Goal:** educational data flows into the system.

* Ingestion of the four documented source types.
* Parallel batch processing.
* Real-time streaming, integrated with batch.
* HDFS read/write on top of the existing `HdfsClient` contract.

---

## Phase 6 - Analytics and machine learning

**Goal:** the predictive models the document asks for.

* Student performance prediction.
* Dropout prediction.
* Course demand prediction.
* Anomaly detection, trend prediction, correlation analysis.
* Model updating and refinement on new data.

---

## Phase 7 - Visualization, notifications and support

**Goal:** the stakeholder-facing surface.

* Interactive dashboards for key metrics, patterns, anomalies, predictions.
* Customisable views per role.
* Automated, threshold-based, configurable alerts.
* Contact, issue reporting and feedback.

---

## Phase 8 - Hardening and delivery

**Goal:** satisfy the non-functional requirements and the deliverables.

* Production WSGI server, 99% uptime target, backups.
* Encryption at rest and in transit; data-protection compliance.
* Performance and resource monitoring.
* User documentation (guides, FAQ, tutorials) and developer documentation.
* Flowcharts, data flow diagrams and the project report.
* Demonstration video (recorded manually once the application is complete).
* `ReadMe.doc` listing all assumptions.
