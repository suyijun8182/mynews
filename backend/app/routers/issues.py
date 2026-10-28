"""各期内容：本期 / 历史、预览、立即推送、重新推送，以及「查看全部」的只读公开页。"""
import hmac

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import digest, freshrss, notify, prefs, scheduler
from app.database import get_db
from app.models import Delivery, Issue
from app.security import current_user

router = APIRouter(prefix="/api", tags=["issues"])
auth = [Depends(current_user)]


def _deliveries(db, issue_id: int) -> list[dict]:
    rows = db.scalars(select(Delivery).where(Delivery.issue_id == issue_id).order_by(Delivery.id)).all()
    return [{"channel": d.channel, "ok": bool(d.ok), "error": d.error, "attempts": d.attempts, "parts": d.parts, "ts": d.ts}
            for d in rows]


def _summary(it: Issue) -> dict:
    return {"id": it.id, "kind": it.kind, "window_start": it.window_start, "window_end": it.window_end,
            "created": it.created, "total": it.total, "status": it.status}


@router.get("/overview", dependencies=auth)
def overview(db: Session = Depends(get_db)):
    """首页报头用：配置是否齐全、下次推送时间、最近一期"""
    fr = prefs.get("freshrss")
    last = db.scalar(select(Issue).order_by(Issue.id.desc()).limit(1))
    return {"freshrss": bool(fr["url"] and fr["username"] and fr["api_password"]),
            "channels": notify.enabled_types(), "ai": prefs.get("ai")["enabled"],
            "next": scheduler.next_runs(), "last": _summary(last) if last else None}


@router.get("/issues", dependencies=auth)
def list_issues(limit: int = Query(60, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.scalars(select(Issue).order_by(Issue.id.desc()).limit(limit)).all()
    dl: dict[int, list] = {}
    if rows:
        for d in db.scalars(select(Delivery).where(Delivery.issue_id.in_([r.id for r in rows])).order_by(Delivery.id)):
            dl.setdefault(d.issue_id, []).append(d)
    out = []
    for r in rows:
        latest = {}
        for d in dl.get(r.id, []):
            latest[d.channel] = {"channel": d.channel, "ok": bool(d.ok), "error": d.error}
        out.append({**_summary(r), "deliveries": list(latest.values())})
    return out


@router.get("/issues/{issue_id}", dependencies=auth)
def get_issue(issue_id: int, db: Session = Depends(get_db)):
    it = db.get(Issue, issue_id)
    if it is None:
        raise HTTPException(404, "这一期不存在（可能已超过保留天数被清理）")
    return {**digest.issue_dict(it), "deliveries": _deliveries(db, it.id), "link": digest.public_link(
        digest.issue_dict(it), it.token)}


class KindIn(BaseModel):
    kind: str = Field("manual", pattern="^(morning|evening|manual)$")


def _need_freshrss():
    fr = prefs.get("freshrss")
    if not (fr["url"] and fr["username"] and fr["api_password"]):
        raise HTTPException(400, "还没有连接 FreshRSS：请先到 设置 → FreshRSS 填写")


@router.post("/issues/preview", dependencies=auth)
def preview(req: KindIn, db: Session = Depends(get_db)):
    """按现在的数据生成一期看看（不存、不推、不标记已推过）"""
    _need_freshrss()
    try:
        return digest.preview(db, req.kind)
    except freshrss.FreshRSSError as e:
        raise HTTPException(502, str(e))


@router.post("/issues/push", dependencies=auth)
def push_now(req: KindIn):
    """立即生成并推送一期（默认「即时推送」：上一期之后的新文章）"""
    _need_freshrss()
    if not notify.enabled_types():
        raise HTTPException(400, "还没有启用任何推送渠道：请先到 设置 → 推送渠道 配置")
    try:
        it = scheduler.run_issue(req.kind)
    except freshrss.FreshRSSError as e:
        raise HTTPException(502, str(e))
    return _summary(it)


class RepushIn(BaseModel):
    channels: list[str] | None = None   # 不给：只重推上次失败的渠道；都成功过就全部重推


@router.post("/issues/{issue_id}/repush", dependencies=auth)
def repush(issue_id: int, req: RepushIn, db: Session = Depends(get_db)):
    it = db.get(Issue, issue_id)
    if it is None:
        raise HTTPException(404, "这一期不存在")
    if not it.total:
        raise HTTPException(400, "这一期没有文章，不需要推送")
    types = req.channels
    if types is None:
        latest = {d["channel"]: d["ok"] for d in _deliveries(db, it.id)}
        failed = [t for t, ok in latest.items() if not ok and t in notify.enabled_types()]
        types = failed or None
    bad = [t for t in types or [] if t not in notify.CHANNEL_TYPES]
    if bad:
        raise HTTPException(400, f"未知的渠道：{', '.join(bad)}")
    res = digest.push(db, it, types)
    db.commit()
    if not res:
        raise HTTPException(400, "没有可推送的渠道：请先到 设置 → 推送渠道 启用")
    return {"status": it.status, "results": res}


@router.get("/public/issues/{issue_id}")
def public_issue(issue_id: int, t: str = Query(..., min_length=8, max_length=64), db: Session = Depends(get_db)):
    """推送消息里「查看全部」链接打开的只读页：凭令牌访问，不用登录"""
    it = db.get(Issue, issue_id)
    if it is None or not it.token or not hmac.compare_digest(it.token, t):
        raise HTTPException(404, "链接无效或这一期已过期")
    d = digest.issue_dict(it)
    return {k: d[k] for k in ("id", "kind", "window_start", "window_end", "created", "total", "sections", "ai_points", "ai_error")}

