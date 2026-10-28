"""定时任务：早报 / 晚报按网页上设的时间推送，每天清理过期数据，数据库断开时自动重连。"""
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app import database, digest, prefs
from app.config import get_settings

_sched: BackgroundScheduler | None = None
_run_lock = threading.Lock()   # 早晚报、立即推送不同时跑：都要改 first_issue，同时跑会把同一篇推两次


def _safe(fn, name):
    def run():
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            print(f"[job] {name} 失败：{type(e).__name__}: {e}", flush=True)
    return run


def run_issue(kind: str):
    """生成并推送一期；返回这一期"""
    with _run_lock:
        with database.session() as db:
            it = digest.run(db, kind)
            print(f"[digest] {digest.KIND_NAME.get(kind, kind)} #{it.id}：{it.total} 条，状态 {it.status}", flush=True)
            return it


def _job(kind: str):
    def run():
        if database.is_configured() and prefs.get("freshrss").get("url"):
            run_issue(kind)
    return run


def _cleanup():
    if database.is_configured():
        with database.session() as db:
            res = digest.cleanup(db)
        if any(res.values()):
            print(f"[cleanup] 已清理过期数据：{res}", flush=True)


def _reconnect():
    if not database.is_configured() and database.configured_url():
        database.connect_from_saved(force=True)


def reschedule():
    """按网页上的早晚报设置重排任务（保存设置后调用）"""
    if _sched is None:
        return
    try:
        s = prefs.get("schedule")
    except Exception:  # noqa: BLE001
        # 启动时数据库在后台连接：引擎已建好、表还没建完就会查失败。先按默认时间排，连好后 _on_db_ready 会再排一次
        s = prefs.DEFAULTS["schedule"]
    for kind in ("morning", "evening"):
        if _sched.get_job(kind):
            _sched.remove_job(kind)
        if s.get(kind + "_on") and s.get(kind):
            h, m = (int(x) for x in s[kind].split(":"))
            # 服务在推送时间前后停了一会儿：1 小时内起来还会补发
            _sched.add_job(_safe(_job(kind), kind), "cron", id=kind, hour=h, minute=m,
                           misfire_grace_time=3600, coalesce=True, max_instances=1)


def next_runs() -> dict:
    if _sched is None:
        return {}
    out = {}
    now = datetime.now(_sched.timezone)
    for kind in ("morning", "evening"):
        j = _sched.get_job(kind)
        # 调度器没启动时（测试）任务还没有 next_run_time，直接问触发器
        nxt = j.trigger.get_next_fire_time(None, now) if j else None
        out[kind] = int(nxt.timestamp()) if nxt else None
    return out


def start(run_jobs: bool = True):
    global _sched
    _sched = BackgroundScheduler(timezone=get_settings().tz)
    _sched.add_job(_safe(_cleanup, "cleanup"), "cron", hour=3, minute=30, max_instances=1, coalesce=True)
    _sched.add_job(_safe(_reconnect, "db-reconnect"), "interval", seconds=30, max_instances=1, coalesce=True)
    reschedule()
    if run_jobs:
        _sched.start()


def stop():
    if _sched is not None and _sched.running:
        _sched.shutdown(wait=False)
