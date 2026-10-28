"""设置页：FreshRSS、早晚报、AI 摘要、站点、推送渠道、版本更新。全部要登录。"""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import __version__, ai, freshrss, notify, prefs, scheduler
from app.database import get_db
from app.security import current_user

router = APIRouter(prefix="/api", tags=["settings"], dependencies=[Depends(current_user)])
HM = r"^([01]\d|2[0-3]):[0-5]\d$"


def _url_ok(u: str, name: str):
    if u and not re.match(r"^https?://", u.strip()):
        raise HTTPException(400, f"{name}要以 http:// 或 https:// 开头")


# ---------------- FreshRSS ----------------
class FreshIn(BaseModel):
    url: str = Field("", max_length=500)
    username: str = Field("", max_length=128)
    api_password: str = Field("", max_length=256)
    categories: list[str] = Field(default_factory=list, max_length=500)


def _fresh_client(req: FreshIn) -> freshrss.Client:
    old = prefs.get("freshrss")
    pw = req.api_password
    if pw.endswith("…"):
        # 沿用已保存的密码：地址或用户名改了就不行，免得把地址改成别处套出已保存的密码
        if req.url.strip().rstrip("/") != old["url"].strip().rstrip("/") or req.username != old["username"]:
            raise HTTPException(400, "改了地址或用户名，请重新填写 API 密码")
        pw = old["api_password"]
    return freshrss.Client(req.url, req.username, pw)


@router.get("/settings/freshrss")
def get_fresh():
    return prefs.masked("freshrss")


@router.post("/settings/freshrss/test")
def test_fresh(req: FreshIn):
    """测试连接（可以是还没保存的配置），成功时返回分类列表"""
    _url_ok(req.url, "FreshRSS 地址")
    try:
        with _fresh_client(req) as c:
            c.login()
            cats = c.categories()
    except freshrss.FreshRSSError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "categories": cats}


@router.put("/settings/freshrss")
def put_fresh(req: FreshIn, db: Session = Depends(get_db)):
    _url_ok(req.url, "FreshRSS 地址")
    old = prefs.get("freshrss")
    if req.api_password.endswith("…") and (req.url.strip().rstrip("/") != old["url"].strip().rstrip("/")
                                           or req.username != old["username"]):
        raise HTTPException(400, "改了地址或用户名，请重新填写 API 密码")
    v = prefs.put(db, "freshrss", {**req.model_dump(), "url": req.url.strip().rstrip("/"),
                                    "categories": [c for c in req.categories if c][:500]})
    db.commit()
    return prefs.masked("freshrss", v)


# ---------------- 早晚报 ----------------
class ScheduleIn(BaseModel):
    morning_on: bool = True
    morning: str = Field("08:00", pattern=HM)
    evening_on: bool = True
    evening: str = Field("20:00", pattern=HM)
    per_category: int = Field(10, ge=1, le=50)


@router.get("/settings/schedule")
def get_schedule():
    return {**prefs.get("schedule"), "next": scheduler.next_runs()}


@router.put("/settings/schedule")
def put_schedule(req: ScheduleIn, db: Session = Depends(get_db)):
    if req.morning_on and req.evening_on and req.morning == req.evening:
        raise HTTPException(400, "早报和晚报的时间不能相同")
    prefs.put(db, "schedule", req.model_dump())
    db.commit()
    scheduler.reschedule()
    return get_schedule()


# ---------------- AI 摘要 ----------------
class AIIn(BaseModel):
    enabled: bool = False
    base_url: str = Field("", max_length=500)
    api_key: str = Field("", max_length=500)
    model: str = Field("", max_length=128)


def _ai_cfg(req: AIIn) -> dict:
    old = prefs.get("ai")
    key = req.api_key
    if key.endswith("…"):
        if req.base_url.strip().rstrip("/") != old["base_url"].strip().rstrip("/"):
            raise HTTPException(400, "改了接口地址，请重新填写 API Key")
        key = old["api_key"]
    return {**req.model_dump(), "base_url": req.base_url.strip().rstrip("/"), "api_key": key}


@router.get("/settings/ai")
def get_ai():
    return prefs.masked("ai")


@router.put("/settings/ai")
def put_ai(req: AIIn, db: Session = Depends(get_db)):
    _url_ok(req.base_url, "接口地址")
    cfg = _ai_cfg(req)
    if cfg["enabled"] and not (cfg["base_url"] and cfg["api_key"] and cfg["model"]):
        raise HTTPException(400, "开启 AI 摘要要填写接口地址、API Key 和模型")
    v = prefs.put(db, "ai", cfg)
    db.commit()
    return prefs.masked("ai", v)


@router.post("/settings/ai/test")
def test_ai(req: AIIn):
    """用两条示例新闻试一次，确认接口、Key、模型都能用"""
    _url_ok(req.base_url, "接口地址")
    sample = [{"title": "示例：某地发布新一轮城市更新计划", "summary": "计划覆盖老旧小区改造与公共交通。", "category": "国内", "url": ""},
              {"title": "示例：开源社区发布新版本编程语言", "summary": "新版本带来性能改进和新语法。", "category": "科技", "url": ""}]
    try:
        points, _ = ai.summarize(_ai_cfg(req), sample)
    except ai.AIError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "points": points}


# ---------------- 站点 ----------------
class SiteIn(BaseModel):
    public_url: str = Field("", max_length=500)
    retention_days: int = Field(10, ge=1, le=365)


@router.get("/settings/site")
def get_site():
    return prefs.get("site")


@router.put("/settings/site")
def put_site(req: SiteIn, db: Session = Depends(get_db)):
    _url_ok(req.public_url, "外部访问地址")
    v = prefs.put(db, "site", {**req.model_dump(), "public_url": req.public_url.strip().rstrip("/")})
    db.commit()
    return v


# ---------------- 推送渠道（同 EasySub / ROS-DPI） ----------------
class NotifyIn(BaseModel):
    config: dict[str, dict] = {}


class NotifyTest(BaseModel):
    channel: str
    config: dict | None = None   # 未保存的配置也能测试


NAMES = {"wecom": "企业微信", "dingtalk": "钉钉", "feishu": "飞书", "qq": "QQ", "bark": "Bark", "telegram": "Telegram",
         "email": "Email", "pushplus": "Pushplus", "serverchan": "Server酱", "ntfy": "ntfy", "gotify": "Gotify",
         "discord": "Discord", "slack": "Slack", "webhook": "Webhook"}


def _clean(t: str, c: dict, old: dict) -> dict:
    """只保留该渠道认识的字段，类型按默认值转换；以“…”结尾的密钥沿用原值"""
    base = notify.DEFAULTS[t]
    try:
        c = notify.unmask(c, old)
    except ValueError as e:
        raise HTTPException(400, f"{NAMES[t]}：{e}") from None
    out = {"enabled": bool(c.get("enabled"))}
    for k, dv in base.items():
        v = c.get(k, dv)
        if isinstance(dv, bool):
            v = bool(v)
        elif isinstance(dv, list):
            v = [x for x in (v or []) if (x.get("key") if isinstance(x, dict) else str(x).strip())]
            if k != "headers":
                v = [str(x).strip() for x in v]
        elif isinstance(dv, int):
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = dv
        else:
            v = str(v or "").strip()
        out[k] = v
    if t == "wecom":
        if out["mode"] not in ("webhook", "app"):
            out["mode"] = "webhook"
        if out["msg_type"] not in ("text", "markdown", "textcard"):
            out["msg_type"] = "markdown"
    for k in ("url", "server", "card_url", "icon"):
        if out.get(k) and not str(out[k]).startswith(("http://", "https://")):
            raise HTTPException(400, f"{NAMES[t]}：地址要以 http:// 或 https:// 开头")
    for u in out.get("urls") or []:
        if not u.startswith(("http://", "https://")):
            raise HTTPException(400, f"{NAMES[t]}：地址要以 http:// 或 https:// 开头")
    if out["enabled"] and notify.missing(t, out):
        raise HTTPException(400, f"{NAMES[t]}：请先填写 {', '.join(notify.missing(t, out))}")
    return out


@router.get("/notify")
def get_notify():
    return {"config": notify.mask(notify.load_config()), "types": list(notify.CHANNEL_TYPES),
            "last": notify.last_results(), "enabled": notify.enabled_types()}


@router.put("/notify")
def put_notify(req: NotifyIn, db: Session = Depends(get_db)):
    """一次保存所有渠道（和 EasySub 一样）"""
    old = notify.load_config()
    cfg = {t: _clean(t, req.config.get(t) or old[t], old[t]) for t in notify.CHANNEL_TYPES}
    notify.save_config(db, cfg)
    db.commit()
    return get_notify()


@router.post("/notify/test")
def test_notify(req: NotifyTest):
    """测试一个渠道；带了 config 就用这份（可以是还没保存的），密钥以“…”结尾时沿用已保存的值"""
    if req.channel not in notify.DEFAULTS:
        raise HTTPException(400, "未知的渠道")
    old = notify.load_config()[req.channel]
    c = _clean(req.channel, {**(req.config or old), "enabled": True}, old)
    res = notify.send("我的新闻 测试消息", "收到这条消息，说明推送渠道配置正确。", types=[req.channel], config={req.channel: c})
    if not res[0]["ok"]:
        raise HTTPException(502, res[0]["error"])
    return {"ok": True}


def _draft(channel: str, config: dict | None) -> dict:
    old = notify.load_config()[channel]
    return _clean(channel, {**(config or old), "enabled": False}, old)


@router.post("/notify/telegram/{action}")
def telegram_helper(action: str, req: NotifyTest):
    """同 EasySub：「验证机器人」= getMe，「获取 Chat ID」= getUpdates（先给机器人发一条消息）"""
    method = {"me": "getMe", "updates": "getUpdates"}.get(action)
    if not method:
        raise HTTPException(404, "未知操作")
    try:
        return notify.telegram_call(_draft("telegram", req.config), method)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, notify.scrub_error(f"Telegram {method} 失败：{e}"))


@router.post("/notify/wecom/check")
def wecom_check(req: NotifyTest):
    """校验企业微信自建应用：拉取 access_token 并读取应用名与可见范围"""
    conf = _draft("wecom", req.config)
    if conf.get("mode") != "app":
        raise HTTPException(400, "只有自建应用模式需要校验")
    try:
        return {"ok": True, "agent": notify.wecom_agent_info(conf)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, notify.scrub_error(str(e)))


# ---------------- 版本 ----------------
@router.get("/system/version")
def version():
    from app import selfupdate
    return selfupdate.status(__version__)


@router.post("/system/update")
def update():
    from app import selfupdate
    try:
        return selfupdate.perform(__version__)
    except selfupdate.Busy as e:
        raise HTTPException(409, str(e))
    except RuntimeError as e:
        raise HTTPException(400, str(e))
