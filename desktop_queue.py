"""Subprocess lifecycle, queue advancement and per-job progress."""
from __future__ import annotations

import os
import re
import sys
import subprocess
import threading
from desktop_options import APP_DIR
from desktop_strings import STRINGS
from desktop_types import STATUS_WAITING, STATUS_RUNNING, STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED

def fill_parallel_slots(window) -> None:
    while len(window.active_processes) < window.max_parallel:
        idx = window._next_waiting_index()
        if idx is None:
            break
        window._start_job(idx)
    if not window.active_processes and window._next_waiting_index() is None:
        window.finish_batch()

def next_waiting_index(window) -> int | None:
    for i, job in enumerate(window.jobs):
        if job.status == STATUS_WAITING:
            return i
    return None

def start_job(window, index: int) -> None:
    job = window.jobs[index]
    job.status = STATUS_RUNNING
    window.refresh_table()
    if window.table.currentRow() < 0:
        window.table.selectRow(index)
    s = STRINGS[window.ui_lang]
    window.append_log(f"\n{s['starting'].format(job.video.name)}\n")

    command = window.command_for(job)
    generation = window.process_generation
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        process = subprocess.Popen(
            command,
            cwd=str(APP_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
    except OSError as exc:
        window._job_start_failed(index, str(exc))
        return

    window.active_processes[index] = process
    window.preview.setReadOnly(True)
    window.save_preview_btn.setEnabled(False)
    window._update_editor_controls()
    threading.Thread(target=window._read_process_stream, args=(generation, index, process), daemon=True).start()
    window.process_pump.start()

def read_process_stream(window, generation: int, index: int, process: subprocess.Popen[str]) -> None:
    exit_code = 1
    try:
        if process.stdout is not None:
            for text in process.stdout:
                window.process_outputs.append((generation, index, text))
        exit_code = process.wait()
    except Exception as exc:
        window.process_outputs.append((generation, index, f"Process error: {exc}\n"))
        if process.poll() is None:
            process.kill()
        process.wait()
        exit_code = 1
    if process.stdout is not None:
        process.stdout.close()
    window.process_finishes.append((generation, index, exit_code))

def drain_process_events(window) -> None:
    for _ in range(min(len(window.process_outputs), 200)):
        generation, index, text = window.process_outputs.popleft()
        if generation != window.process_generation:
            continue
        window.append_log(text)
        window._parse_progress(text, index)

    while window.process_finishes:
        generation, index, exit_code = window.process_finishes.popleft()
        if generation != window.process_generation:
            continue
        window._job_finished(index, exit_code)

    if not window.active_processes:
        window.process_pump.stop()

def parse_progress(window, text: str, index: int | None = None) -> None:
    job = window.jobs[index] if index is not None and 0 <= index < len(window.jobs) else None
    stage = re.search(r"\[stage:(\w+)\]", text)
    if stage:
        window.status_badge.setText(window.tr("stage_" + stage.group(1)))
        if job is not None:
            job.stage = stage.group(1)
    match = re.search(r"(\d+)%\|", text)
    if match:
        pct = min(100, int(match.group(1)))
        window.progress.setRange(0, 100)
        window.progress.setValue(pct)
        if job is not None:
            job.progress = pct
    if job is not None and job.status == STATUS_RUNNING:
        status = window.tr("stage_" + job.stage) if job.stage else window._status_text(job.status)
        if job.progress is not None:
            status += f" {job.progress}%"
        item = window.table.item(index, 4)
        if item is not None:
            item.setText(status)

def job_finished(window, index: int, exit_code: int) -> None:
    if index is None or index not in window.active_processes or index >= len(window.jobs):
        return
    del window.active_processes[index]

    job = window.jobs[index]
    s = STRINGS[window.ui_lang]
    if exit_code == 0:
        job.status = STATUS_DONE
        window.append_log(f"{s['saved'].format(job.output)}\n")
        if not job.output.is_file():
            job.status = STATUS_FAILED
            window.append_log("Process exited without creating its output.\n")
    else:
        job.status = STATUS_FAILED
        window.append_log(f"{s['failed_code'].format(exit_code)}\n")
    if job.status == STATUS_FAILED:
        window.statusBar().showMessage(window.tr("job_error"), 8000)
    window.refresh_table()

    window._fill_parallel_slots()

def job_start_failed(window, index: int, message: str) -> None:
    if index >= len(window.jobs):
        return
    window.jobs[index].status = STATUS_FAILED
    window.append_log(f"Process error: {message}\n")
    window.refresh_table()

def finish_batch(window) -> None:
    s = STRINGS[window.ui_lang]
    window.progress.setRange(0, 100)
    window.progress.setValue(round(sum(job.status == STATUS_DONE for job in window.jobs) / len(window.jobs) * 100) if window.jobs else 0)
    window.status_badge.setText(window._batch_status_text(s))
    window.start_button.setEnabled(True)
    window.cancel_button.setEnabled(False)
    window.skip_button.setEnabled(False)
    window.skip_button.setVisible(False)
    window._set_editing_enabled(True)

def cancel_all(window) -> None:
    if window.burn_process is not None:
        window.burn_process.kill()
        return
    for process in window.active_processes.values():
        if process.poll() is None:
            process.kill()
    window.active_processes.clear()
    window.process_generation += 1
    window._clear_process_queues()
    window.process_pump.stop()
    s = STRINGS[window.ui_lang]
    for job in window.jobs:
        if job.status in {STATUS_WAITING, STATUS_RUNNING}:
            job.status = STATUS_CANCELLED
    window.refresh_table()
    window.finish_batch()
    window.status_badge.setText(window._batch_status_text(s))

def skip_current(window) -> None:
    """Kill the currently selected running job and advance to the next one."""
    rows = sorted({index.row() for index in window.table.selectedIndexes()})
    if not rows:
        return
    index = rows[0]
    if index >= len(window.jobs):
        return
    job = window.jobs[index]
    if job.status != STATUS_RUNNING:
        return
    # Kill the process if it is still alive.
    process = window.active_processes.get(index)
    if process:
        if process.poll() is None:
            process.kill()
        del window.active_processes[index]
    job.status = STATUS_CANCELLED
    s = STRINGS[window.ui_lang]
    window.append_log(f"\nSkipped: {job.video.name}\n")
    window.refresh_table()
    # Advance to next waiting job without touching process_generation so
    # that other still-running parallel jobs keep their finish events valid.
    window._fill_parallel_slots()

def clear_process_queues(window) -> None:
    window.process_outputs.clear()
    window.process_finishes.clear()
