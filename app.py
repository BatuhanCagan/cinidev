from flask import Flask, render_template, request, jsonify
import json
import os
import uuid
import markdown
from process_manager import manager
from activity_log import log_event, get_events

app = Flask(__name__)
DATA_FILE = "projects.json"


def load_projects():
    if not os.path.exists(DATA_FILE):
        default_data = [
            {
                "id": "flask-api-1",
                "name": "my-flask-api",
                "path": "/home/user/projects/api",
                "port": "5000",
                "command": "python app.py",
                "tags": ["Python", "Flask"],
                "env": {"DB_HOST": "localhost", "PORT": "5000"}
            }
        ]
        save_projects(default_data)
        return default_data
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_projects(projects):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)


@app.route("/")
def index():
    projects = load_projects()
    for p in projects:
        p["is_running"] = manager.is_running(p["id"])
    return render_template("index.html", projects=projects, active_page="projects")


@app.route("/monitor")
def monitor():
    projects = load_projects()
    for p in projects:
        p["is_running"] = manager.is_running(p["id"])
    return render_template("monitor.html", projects=projects, active_page="monitor")


@app.route("/activity")
def activity():
    events = get_events()
    return render_template("activity.html", events=events, active_page="activity")


@app.route("/docs")
def docs():
    readme_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md")
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            content_html = markdown.markdown(f.read(), extensions=["fenced_code", "tables"])
    else:
        content_html = "<p>README.md not found.</p>"
    return render_template("docs.html", content=content_html, active_page="docs")


@app.route("/api/projects", methods=["POST"])
def add_project():
    data = request.json
    projects = load_projects()

    new_project = {
        "id": str(uuid.uuid4())[:8],
        "name": data.get("name"),
        "path": data.get("path"),
        "port": data.get("port", "3000"),
        "command": data.get("command", "npm start"),
        "tags": data.get("tags", []),
        "env": {}
    }

    projects.append(new_project)
    save_projects(projects)
    log_event("created", new_project["name"], f"path={new_project['path']}")
    return jsonify({"success": True, "project": new_project})


@app.route("/api/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    if manager.is_running(project_id):
        manager.stop_project(project_id)

    projects = load_projects()
    deleted = next((p for p in projects if p["id"] == project_id), None)
    projects = [p for p in projects if p["id"] != project_id]
    save_projects(projects)

    if deleted:
        log_event("deleted", deleted["name"])
    return jsonify({"success": True})


@app.route("/api/projects/<project_id>/start", methods=["POST"])
def start_project(project_id):
    projects = load_projects()
    project = next((p for p in projects if p["id"] == project_id), None)

    if not project:
        return jsonify({"success": False, "message": "Project not found."}), 404

    success, message = manager.start_project(
        project_id=project["id"],
        project_name=project["name"],
        folder_path=project["path"],
        start_command=project["command"],
        env_vars=project.get("env", {})
    )
    if success:
        log_event("started", project["name"])
    else:
        log_event("start_failed", project["name"], message)
    return jsonify({"success": success, "message": message})


@app.route("/api/projects/<project_id>/stop", methods=["POST"])
def stop_project(project_id):
    projects = load_projects()
    project = next((p for p in projects if p["id"] == project_id), None)

    success, message = manager.stop_project(project_id)
    if success and project:
        log_event("stopped", project["name"])
    return jsonify({"success": success, "message": message})


@app.route("/api/projects/<project_id>/config", methods=["POST"])
def update_config(project_id):
    data = request.json
    projects = load_projects()

    updated_name = None
    for p in projects:
        if p["id"] == project_id:
            p["port"] = data.get("port", p["port"])
            p["command"] = data.get("command", p["command"])
            p["env"] = data.get("env", p["env"])
            updated_name = p["name"]
            break

    save_projects(projects)
    if updated_name:
        log_event("config_updated", updated_name)
    return jsonify({"success": True})


@app.route("/api/logs")
def get_logs():
    project_id = request.args.get("project_id")
    logs = manager.get_logs(project_id)
    return jsonify({"logs": logs})


@app.route("/api/stats")
def get_stats():
    projects = load_projects()
    stats = {}
    for p in projects:
        s = manager.get_stats(p["id"])
        if s:
            stats[p["id"]] = s
    return jsonify({"stats": stats})


if __name__ == "__main__":
    # host is pinned to localhost: this tool launches arbitrary shell commands,
    # so it must never be reachable from outside the machine it runs on.
    app.run(debug=True, host="127.0.0.1", port=8000)
