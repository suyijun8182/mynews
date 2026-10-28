"""定时任务：按设置排早晚报；启动时数据库还没建好表也不能把服务带崩。"""
from app import prefs, scheduler


def test_reschedule_survives_db_not_ready(monkeypatch):
    # 启动时数据库在后台连接：引擎有了、表还没建完，读设置会抛错。以前这会让整个服务启动失败
    def boom(group):
        raise RuntimeError("no such table: settings")
    monkeypatch.setattr(prefs, "get", boom)
    scheduler.start(run_jobs=False)
    try:
        nxt = scheduler.next_runs()
        assert nxt["morning"] and nxt["evening"]       # 按默认 08:00 / 20:00 排上了
    finally:
        scheduler.stop()


def test_reschedule_follows_settings(db):
    prefs.put(db, "schedule", {"morning_on": True, "morning": "07:15", "evening_on": False, "evening": "20:00", "per_category": 10})
    db.commit()
    scheduler.start(run_jobs=False)
    try:
        nxt = scheduler.next_runs()
        assert nxt["evening"] is None
        from datetime import datetime
        from app.config import get_settings
        assert datetime.fromtimestamp(nxt["morning"], get_settings().zone).strftime("%H:%M") == "07:15"
    finally:
        scheduler.stop()
