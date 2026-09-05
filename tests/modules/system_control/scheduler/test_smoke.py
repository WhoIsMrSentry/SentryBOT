from __future__ import annotations

from modules.system_control.scheduler.xSchedulerService import create_app


def test_create_app():
    app = create_app()
    assert app is not None


def test_start_without_running_loop_does_not_raise():
    from modules.system_control.scheduler.services.runner import Scheduler

    sched = Scheduler(jobs=[{"id": "ping", "kind": "http", "path": "/healthz", "every_s": 30}])
    sched.start()
    jobs = sched.list_jobs()
    assert jobs and jobs[0]["id"] == "ping"


def test_default_jobs_include_health_and_diagnostics():
    from modules.system_control.scheduler.config_loader import load_config

    cfg = load_config()
    ids = {str(job.get("id")) for job in cfg.get("jobs") or []}
    assert "gateway_health" in ids
    assert "diagnostics_hourly" in ids
