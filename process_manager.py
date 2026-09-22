import subprocess
import os
import signal
import psutil
import threading
from datetime import datetime
from activity_log import log_event

class ProcessManager:
    def __init__(self):
        self.running_processes = {}  # project_id -> subprocess.Popen
        self.logs = {}  # project_id -> [log_lines]
        self.start_times = {}  # project_id -> datetime
        self.tracked_procs = {}  # project_id -> { pid: psutil.Process }
        self.project_names = {}  # project_id -> name, used to label crash events
        self.stopping = set()  # project_ids currently being stopped intentionally

    def _append_log(self, project_id, message):
        if project_id not in self.logs:
            self.logs[project_id] = []
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs[project_id].append(f"[{timestamp}] {message}")
        if len(self.logs[project_id]) > 100:
            self.logs[project_id].pop(0)

    def _read_output(self, project_id, process):
        for line in iter(process.stdout.readline, ''):
            if line:
                self._append_log(project_id, line.strip())
        process.stdout.close()
        process.wait()

        # If nobody called stop_project() for this run, the process exited on its
        # own (crash or the command simply finished) — surface that instead of
        # silently leaving the UI showing it as still running.
        if project_id in self.stopping or project_id not in self.running_processes:
            return
        code = process.returncode
        self._append_log(project_id, f"⚠️ Process exited unexpectedly (exit code {code}).")
        self.running_processes.pop(project_id, None)
        self.start_times.pop(project_id, None)
        self.tracked_procs.pop(project_id, None)
        name = self.project_names.get(project_id, project_id)
        log_event("crashed", name, f"exit code {code}")

    def _track_process_tree(self, project_id, root_pid):
        """Register the root process and its current children, priming cpu_percent for each."""
        try:
            root = psutil.Process(root_pid)
        except psutil.NoSuchProcess:
            return
        tracked = self.tracked_procs.setdefault(project_id, {})
        for proc in [root] + root.children(recursive=True):
            if proc.pid not in tracked:
                try:
                    proc.cpu_percent(interval=None)  # first call primes the measurement
                except psutil.NoSuchProcess:
                    continue
                tracked[proc.pid] = proc

    def start_project(self, project_id, project_name, folder_path, start_command, env_vars=None):
        if self.is_running(project_id):
            return False, "Project is already running."

        if not os.path.exists(folder_path):
            return False, f"Directory not found: {folder_path}"

        self.project_names[project_id] = project_name
        self.stopping.discard(project_id)  # clear any leftover flag from a previous run

        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)

        try:
            process = subprocess.Popen(
                start_command,
                shell=True,
                cwd=folder_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                preexec_fn=os.setsid if os.name != 'nt' else None  # process group id on Linux/Mac
            )

            self.running_processes[project_id] = process
            self.start_times[project_id] = datetime.now()
            self._track_process_tree(project_id, process.pid)
            self._append_log(project_id, f"🚀 Project started: '{start_command}'")

            thread = threading.Thread(target=self._read_output, args=(project_id, process), daemon=True)
            thread.start()

            return True, "Project started successfully."
        except Exception as e:
            return False, f"Start error: {str(e)}"

    def stop_project(self, project_id):
        if not self.is_running(project_id):
            return False, "Project is already stopped."

        process = self.running_processes.get(project_id)
        if process:
            self.stopping.add(project_id)  # tell _read_output this exit was intentional
            try:
                # Kill the whole process tree: shell=True means the tracked PID is
                # often just a wrapper (cmd.exe / sh) around the real dev server.
                if os.name == 'nt':
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)])
                else:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)

                del self.running_processes[project_id]
                self.start_times.pop(project_id, None)
                self.tracked_procs.pop(project_id, None)
                self._append_log(project_id, "🛑 Project stopped by user.")
                return True, "Project stopped."
            except Exception as e:
                return False, f"Stop error: {str(e)}"
        return False, "Process not found."

    def is_running(self, project_id):
        process = self.running_processes.get(project_id)
        if process:
            if process.poll() is None:
                return True
            # Process exited on its own
            del self.running_processes[project_id]
            self.start_times.pop(project_id, None)
            self.tracked_procs.pop(project_id, None)
        return False

    def get_stats(self, project_id):
        """Real CPU/RAM usage for a running project, summed across its full process tree."""
        if not self.is_running(project_id):
            return None

        root_process = self.running_processes.get(project_id)
        try:
            root = psutil.Process(root_process.pid)
        except psutil.NoSuchProcess:
            return None

        current = {root.pid: root}
        try:
            for child in root.children(recursive=True):
                current[child.pid] = child
        except psutil.NoSuchProcess:
            pass

        tracked = self.tracked_procs.setdefault(project_id, {})
        for pid, proc in current.items():
            if pid not in tracked:
                try:
                    proc.cpu_percent(interval=None)  # primed now, real value on next poll
                except psutil.NoSuchProcess:
                    continue
                tracked[pid] = proc
        for pid in list(tracked.keys()):
            if pid not in current:
                del tracked[pid]

        cpu_total = 0.0
        mem_total = 0
        for pid, proc in list(tracked.items()):
            try:
                cpu_total += proc.cpu_percent(interval=None)
                mem_total += proc.memory_info().rss
            except psutil.NoSuchProcess:
                del tracked[pid]

        started = self.start_times.get(project_id)
        uptime_seconds = int((datetime.now() - started).total_seconds()) if started else 0

        return {
            "cpu_percent": round(cpu_total, 1),
            "memory_mb": round(mem_total / (1024 * 1024), 1),
            "uptime_seconds": uptime_seconds,
        }

    def get_logs(self, project_id=None):
        if project_id:
            return self.logs.get(project_id, [])
        all_logs = []
        for p_id, p_logs in self.logs.items():
            for l in p_logs:
                all_logs.append(f"[{p_id}] {l}")
        return all_logs

manager = ProcessManager()  # module-level singleton
