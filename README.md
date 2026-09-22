# ÇiniDev

**ÇiniDev** is a small, local-first control panel for developers who juggle several projects on one machine. Instead of a wall of terminal tabs for your API, your frontend, and that one worker script, you register each project once and then start, stop, configure, and watch it from a single browser dashboard.

It's meant to be a genuinely useful personal tool, not a SaaS clone — no accounts, no cloud, no telemetry. Everything binds to `127.0.0.1` and all state lives in plain JSON files next to the code, so you can read it, back it up, or delete it with zero ceremony. The visual design draws on traditional İznik ceramic tile patterns (hence "Çini," Turkish for tile).

Built with Flask on the backend and a single Tailwind-styled dashboard on the frontend.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Flask](https://img.shields.io/badge/flask-3.0-black)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Project registry** — register any local project by name, folder path, start command, port, and free-form tags.
- **Start / stop control** — launches each project as a managed subprocess and kills the full process tree on stop (works on both Windows and Unix).
- **Live log streaming** — captures each process's stdout/stderr and streams the last 100 lines per project to an in-browser terminal.
- **Per-project configuration** — edit the port, start command, and a full environment variable table after a project has been added.
- **Resource monitor** — real per-process CPU and RAM usage (via `psutil`, aggregated across the whole process tree so it's accurate even through `npm`/`shell=True` wrapper processes), shown live on each project card and on a dedicated `/monitor` page.
- **Activity log** — every create / delete / start / stop / config change is recorded with a timestamp and viewable on `/activity`.
- **Error visibility** — a failed start (bad path, bad command) or a process that crashes on its own is logged to both the in-browser terminal and the activity log, and surfaced as a toast in the UI instead of failing silently.
- **In-app docs** — this README, rendered at `/docs`.
- **Zero external database** — no Docker, no DB server; project state and activity history live in local files.

## Tech stack

| Layer     | Technology                                    |
|-----------|------------------------------------------------|
| Backend   | Python, Flask                                  |
| Process control & monitoring | `subprocess` + `psutil`         |
| Frontend  | Jinja2 templates, Tailwind CSS (CDN), vanilla JS |
| Storage   | Flat files (`projects.json`, `activity.jsonl`) |

## Getting started

### Prerequisites

- Python 3.11+

### Installation

```bash
git clone https://github.com/BatuhanCagan/cinidev.git
cd cinidev

python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Run

```bash
python app.py
```

The dashboard will be available at **http://127.0.0.1:8000**.

On first run, ÇiniDev seeds `projects.json` with a sample project entry — edit or delete it from the UI, or add your own with the **"Add New Project"** button.

## How it works

- Each registered project is a JSON record: `{ name, path, port, command, tags, env }`.
- **Start** runs `command` inside `path` via `subprocess.Popen(shell=True)`, with your custom `env` vars merged into the process environment. Its combined stdout/stderr is captured on a background thread and kept in memory.
- **Stop** kills the process and all of its children (`taskkill /T` on Windows, `killpg` on Unix) so that dev servers spawned by package managers (e.g. `npm start`) don't linger.
- Logs are polled by the frontend every 2 seconds via `/api/logs`.
- **Resource stats** (`/api/stats`) walk the running process's full child tree with `psutil` and sum CPU/RAM, since `shell=True` means the tracked PID is often just a wrapper (e.g. `cmd.exe` around the real `node`/`python` process).
- **Activity events** are appended as JSON lines to `activity.jsonl` by `activity_log.py` and rendered newest-first on `/activity`.
- If a process exits on its own (crash, or the command just finishing) instead of being stopped by the user, the background log-reader thread detects it, logs a `⚠️ Process exited unexpectedly` line, and records a `crashed` activity event.

## ⚠️ Security note

ÇiniDev runs **arbitrary shell commands you configure**, and the Flask dev server runs with the debugger enabled. This is intentional for a personal, local tool — it is **not** meant to be exposed to a network or the internet. The server binds to `127.0.0.1` by default; keep it that way.

## Project structure

```
cinidev/
├── app.py                    # Flask routes / API
├── process_manager.py        # Subprocess lifecycle, log capture, resource stats
├── activity_log.py           # Append-only JSON-lines audit log
├── requirements.txt
├── projects.json             # Local project registry (git-ignored, generated on first run)
├── activity.jsonl            # Activity log (git-ignored, generated on first run)
├── templates/
│   ├── _layout.html          # Shared sidebar/page shell
│   ├── index.html            # Dashboard: project cards, modals, terminal
│   ├── monitor.html          # Resource Monitor page
│   ├── activity.html         # Activity Log page
│   ├── docs.html             # In-app README viewer
│   ├── base.html             # Original full-dashboard design mockup (reference only, not routed)
│   └── components/           # Original per-modal design mockups (reference only, not routed)
└── static/                    # Reserved for future static assets
```

## License

MIT — see [LICENSE](LICENSE).
