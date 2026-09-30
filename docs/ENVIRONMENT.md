# Environment Requirements

What must be installed and configured before the next development phases, and
what the state of this machine is today.

---

## 1. Status on this machine

| Component | Documented as | State | Notes |
|---|---|---|---|
| Python | implied by Anaconda / Jupyter / PyCharm | **Working** | Python 3.12.7 at `C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe`; added to the user PATH |
| Flask | not named in the document | **Working** | 3.1.3, the web framework chosen by ADR-0002 |
| pytest | not named in the document | **Working** | 9.1.1, 49 tests passing |
| JDK / Java | required by Hadoop | **Working (repaired in Phase 1)** | Temurin OpenJDK 17.0.20.1 at `C:\Users\admin\jdk-17`; user `JAVA_HOME` now points there |
| Hadoop CLI | required | **Working (repaired in Phase 1)** | Hadoop 3.5.0 at `C:\hadoop`; `hadoop version` prints its banner. `C:\hadoop\etc\hadoop\hadoop-env.cmd` hardcoded a `JAVA_HOME` that did not exist and was corrected |
| `winutils.exe` | required by Hadoop on Windows | **MISSING - blocker** | Not present anywhere under `C:\hadoop`. Every `hdfs dfs ...` command fails until it is supplied |
| HDFS (NameNode running) | required | **Not running** | No NameNode/DataNode process; ports 9000, 8020 and 9870 all closed |
| Impala | required | **Not installed** | `impala-shell` not on PATH |
| Docker | not named (Hadoop ships a `compose` dir) | **Not installed** | The usual way to start HDFS locally, so it is also a blocker for that route |
| Jupyter / Anaconda | listed | **Not installed** | Not required by Phase 1 code |
| RStudio / R | listed | **Not installed** | Not required by Phase 1 code |
| MongoDB + Compass Shell | listed | Compass shortcut only; shell not on PATH | Not required by Phase 1 code |
| Tableau | listed | **Not installed** | Not required by Phase 1 code |

**The Phase 1 application runs without HDFS, Impala, MongoDB, Tableau, Jupyter,
R or Docker.** They are listed in the document but no implemented module needs
them yet, and adding them now would be unjustified scope.

`edupredict check` currently reports:

```text
  [         ok] runtime        CPython 3.12.7 on Windows 11
  [         ok] configuration  loaded from settings.toml
  [unavailable] hdfs           Hadoop on Windows requires winutils.exe ...
  [unavailable] impala         Impala shell (impala-shell) not found on PATH ...
overall: warn
```

That `warn` is the truthful state of this machine, not a defect in the code.


---

## 2. Required for the next phases (HDFS / Data Storage)

### 2.1 A working JDK

**Status: done.** Temurin OpenJDK 17.0.20.1 is installed at
`C:\Users\admin\jdk-17` and the user `JAVA_HOME` points to it. It had to be
placed there because the session is not elevated, so
`C:\Program Files\Java` could not be created.

```bash
java -version
echo %JAVA_HOME%
if exist "%JAVA_HOME%\bin\java.exe" (echo OK) else (echo BROKEN)
```

Hadoop's shell scripts refuse to start without a valid `JAVA_HOME`. If
`hadoop version` reports `JAVA_HOME is incorrectly set`, the JDK is the problem.

### 2.2 A working Hadoop CLI

**Status: partly done.** `hadoop version` now works (Hadoop 3.5.0), after
correcting a hardcoded `JAVA_HOME` in `C:\hadoop\etc\hadoop\hadoop-env.cmd`
line 3, which pointed at `C:\Program Files\Java\jdk-17` - a directory that never
existed. That file hardcodes the value unconditionally, so setting the
environment variable alone was not enough.

`winutils.exe` is still missing:

```text
java.io.FileNotFoundException: Could not locate Hadoop executable:
C:\hadoop\bin\winutils.exe
```

Hadoop on Windows requires `winutils.exe` in `HADOOP_HOME\bin` (or
`HADOOP_HOME`) before any `hdfs dfs` command will run. It is not bundled with
every Windows build. Supply it from an official Hadoop Windows distribution and
place it at `C:\hadoop\bin\winutils.exe`.

Once `winutils.exe` is in place, `edupredict check` will move on to the next
question - whether a NameNode is actually running:

```bash
hdfs dfs -ls /     # must answer, i.e. a NameNode must be reachable
```

Two outcomes are then possible:

* **Client working, no cluster** - `hdfs dfs -ls` fails to connect. EduPredict
  reports this distinctly from "Hadoop not installed", which is exactly the
  distinction the storage phase needs.
* **Local pseudo-distributed cluster** - start one so the storage phase has a
  real target. The usual route on Windows is the Docker Compose file shipped
  with the distribution:

  ```bash
  cd C:\hadoop\compose
  docker compose up -d
  ```

  Docker is not currently installed, so this route is blocked until it is.

### 2.3 Point EduPredict at the cluster

Edit `config/settings.toml` or set environment variables:

```bash
set EDUPREDICT_HDFS__NAMENODE_URI=hdfs://localhost:8020
set EDUPREDICT_HDFS__BASE_PATH=/user/edupredict
python -m edupredict check
```

The default `hdfs://localhost:9000` is the classic single-node default port.
`8020` is used by several modern distributions, so verify against the actual
cluster.

---

## 3. Required for the analytics phase (Impala)

Impala queries data held in HDFS and needs its own service plus client tools:

```bash
impala-shell --host=<host> --port=21050 -q "SHOW DATABASES;"
```

Configure it via:

```bash
set EDUPREDICT_IMPALA__HOST=localhost
set EDUPREDICT_IMPALA__PORT=21050
set EDUPREDICT_IMPALA__DATABASE=edupredict
```

Until Impala is installed, `edupredict check` reports
`Impala shell (impala-shell) not found on PATH` - this is the correct and
expected result, not a bug.

---

## 4. Optional tooling named in the document

| Tool | Why it is named | When it becomes useful |
|---|---|---|
| Jupyter / Anaconda Notebook | Exploratory analysis of the educational dataset | Dataset + analytics phase |
| RStudio | Statistical analysis, alternative to Python for modelling | Analytics / ML phase, if R is chosen for a model |
| MongoDB + Compass | Document store; Compass for browsing | **Undecided** - the document lists it but never says what it stores. See ADR-0005. |
| Tableau | Business dashboards for stakeholders | Visualization phase |
| PyCharm / VS Code | IDEs for the source code | Already usable now; no setup required |

---

## 5. Reproducing the Phase 1 environment

```bash
# 1. Python 3.12 (per-user, no admin rights required)
python-3.12.7-amd64.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0

# 2. A JDK 17 (Hadoop cannot run without one)
#    Extract to a writable folder, then point JAVA_HOME at it and correct
#    <HADOOP_HOME>\etc\hadoop\hadoop-env.cmd, which hardcodes the value.
setx JAVA_HOME C:\Users\admin\jdk-17

# 3. Project dependencies
cd EduPredict
python -m pip install -e ".[dev]"

# 4. Verify
python -m pytest
python -m edupredict check
python -m edupredict serve
```

> On Windows, if `curl` fails against GitHub-hosted downloads with
> `schannel: ... revocation server was offline`, add `--ssl-no-revoke`. This was
> needed to install the JDK in Phase 1.

---

## 6. Note on the project folder name

The working directory is `C:\Users\admin\Desktop\EduPredict`, matching the
product name. The Python package is spelled `edupredict`.

The folder was previously named `EduPridict` (missing the `e`) and was renamed
after Phase 1. Because the project is installed in editable mode, the
`__editable__.edupredict-*.pth` file in `site-packages` records an absolute
path to `src`. **After moving or renaming the project folder, reinstall before
running anything:**

```bash
cd C:\Users\admin\Desktop\EduPredict
python -m pip install -e ".[dev]"
```

Until that is done, `import edupredict` fails or resolves to a stale path.
