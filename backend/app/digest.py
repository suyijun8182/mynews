"""早晚报：划时间窗口 → 从 FreshRSS 同步文章 → 分类与本地精选 → 存成一期 → 按渠道排版拆分推送。

时间窗口按“进入 FreshRSS 的时间”算：
- 早报 / 晚报：从上一个已开启的推送时间到本次推送时间。早晚报都开时，早报覆盖前一天 20:00～今天 08:00，
  晚报覆盖 08:00～20:00；只开一个时覆盖 24 小时。
- 立即推送：从上一期的结束时间到现在（最多往前 24 小时）。
同一篇文章只推一次：进了某一期就记下 first_issue，之后各期都跳过它（网页预览不记）。

一期保存全部报道及本地精选；推送每个类别最多 8 件事，仅标题与链接。
"""
import json
import re
import secrets
import time
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from app import freshrss, highlights, notify, prefs
from app.config import get_settings
from app.models import Article, Delivery, Issue

KIND_NAME = {"morning": "早报", "evening": "晚报", "manual": "即时推送"}
WEEKDAY = "一二三四五六日"
UNCATEGORIZED = "未分类"
MANUAL_MAX = 86400


def _tz():
    return get_settings().zone


def _at(day: datetime, hm: str) -> datetime:
    h, m = (int(x) for x in hm.split(":"))
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


def slots(sched: dict) -> list[str]:
    """已开启的推送时间（HH:MM），去重排序"""
    out = {sched[k] for k in ("morning", "evening") if sched.get(k + "_on") and sched.get(k)}
    return sorted(out)


def window(kind: str, now: float | None = None, sched: dict | None = None, last_end: int | None = None) -> tuple[int, int]:
    """一期覆盖的时间段 [start, end)（秒）"""
    now = now or time.time()
    if kind == "manual":
        start = max(int(last_end or 0), int(now) - MANUAL_MAX)
        return start, int(now)
    sched = sched or prefs.get("schedule")
    cur = datetime.fromtimestamp(now, _tz())
    end = _at(cur, sched[kind])
    if end > cur + timedelta(minutes=5):   # 补发昨天错过的那一期时，end 落在今天会是未来
        end -= timedelta(days=1)
    times = slots(sched) or [sched[kind]]
    prev = max(t for t in (_at(end - timedelta(days=d), hm) for d in (0, 1) for hm in times) if t < end)
    return int(prev.timestamp()), int(end.timestamp())


def sync(db, since: int, client: freshrss.Client | None = None) -> int:
    """把 since 之后进入 FreshRSS 的文章存进本地缓存，返回新增条数"""
    cfg = prefs.get("freshrss")
    own = client is None
    client = client or freshrss.Client(cfg["url"], cfg["username"], cfg["api_password"])
    try:
        items = client.items_since(since)
    finally:
        if own:
            client.close()
    have = set(db.scalars(select(Article.id).where(Article.id.in_([x["id"] for x in items])))) if items else set()
    new = 0
    for x in items:
        if x["id"] in have:
            continue
        have.add(x["id"])
        db.add(Article(**x))
        new += 1
    db.flush()
    return new


def collect(db, start: int, end: int) -> list[Article]:
    """窗口内所选分类的全部未推文章；事件去重仅用于精选，不删网页版文章。"""
    cats = prefs.get("freshrss").get("categories") or []
    rows = db.scalars(select(Article).where(Article.crawled >= start, Article.crawled < end, Article.first_issue.is_(None))
                      .order_by(Article.crawled.desc(), Article.id.desc())).all()
    out = []
    for a in rows:
        if cats and (a.category or UNCATEGORIZED) not in cats:
            continue
        out.append(a)
    return out


def _item(a: Article) -> dict:
    return {"id": a.id, "title": a.title, "url": a.url or "", "source": a.source or "", "summary": a.summary or "",
            "crawled": a.crawled, "published": a.published}


def group(articles: list[Article]) -> list[dict]:
    """按分类分组：文章多的分类在前，同样多按名字"""
    by: dict[str, list] = {}
    for a in articles:
        by.setdefault(a.category or UNCATEGORIZED, []).append(_item(a))
    return [{"category": k, "items": v} for k, v in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0]))]


def build(db, kind: str, start: int, end: int, ai_transport=None) -> dict:
    """生成一期的内容（不存库）：{kind, window, total, sections, ai_points, ai_error}"""
    arts = collect(db, start, end)
    data = {"kind": kind, "window_start": start, "window_end": end, "total": len(arts),
            "sections": group(arts), "ai_points": None, "ai_error": None, "_ids": [a.id for a in arts]}
    data["highlights"] = highlights.select(data["sections"], end)
    return data


def save(db, data: dict) -> Issue:
    """存成一期，并把这些文章标记为已推过"""
    it = Issue(kind=data["kind"], window_start=data["window_start"], window_end=data["window_end"],
               created=int(time.time()), total=data["total"],
               content=json.dumps({"sections": data["sections"], "highlights": data.get("highlights")}, ensure_ascii=False),
               ai_points=json.dumps(data["ai_points"], ensure_ascii=False) if data["ai_points"] is not None else None,
               ai_error=data["ai_error"], token=secrets.token_urlsafe(12), status="pending" if data["total"] else "empty")
    db.add(it)
    db.flush()
    ids = data.get("_ids") or []
    for i in range(0, len(ids), 500):
        db.query(Article).filter(Article.id.in_(ids[i:i + 500])).update({Article.first_issue: it.id}, synchronize_session=False)
    return it


def issue_dict(it: Issue, with_token: bool = False) -> dict:
    content = json.loads(it.content or "{}")
    sections = content.get("sections") or []
    out = {"id": it.id, "kind": it.kind, "window_start": it.window_start, "window_end": it.window_end,
           "created": it.created, "total": it.total, "sections": sections,
           "highlights": content.get("highlights") if content.get("highlights") is not None else highlights.select(sections, it.window_end),
           "ai_points": json.loads(it.ai_points) if it.ai_points else None, "ai_error": it.ai_error, "status": it.status}
    if with_token:
        out["token"] = it.token
    return out


# ---------------- 排版与拆分 ----------------
def headline(d: dict) -> str:
    when = datetime.fromtimestamp(d["window_end"], _tz())
    return f"我的新闻 · {KIND_NAME.get(d['kind'], d['kind'])} · {when.month}月{when.day}日 周{WEEKDAY[when.weekday()]}"


def public_link(d: dict, token: str | None) -> str:
    base = (prefs.get("site").get("public_url") or "").strip().rstrip("/")
    return f"{base}/i/{d['id']}?t={token}" if base and token and d.get("id") else ""


def _esc(s: str, fmt: str) -> str:
    if fmt == "html":
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if fmt == "slack":
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if fmt == "md":
        return re.sub(r"([\[\]])", r"\\\1", s)
    return s


def _link(title: str, url: str, fmt: str) -> str:
    t = _esc(title, fmt)
    if not url:
        return t
    if fmt == "html":
        return f'<a href="{url.replace(chr(34), "%22")}">{t}</a>'
    if fmt == "md":
        return f"[{t}]({url.replace(')', '%29').replace(' ', '%20')})"
    if fmt == "slack":
        return f"<{url.replace('|', '%7C').replace('>', '%3E')}|{t}>"
    return t


def _bold(s: str, fmt: str) -> str:
    return {"html": f"<b>{_esc(s, fmt)}</b>", "md": f"**{s}**", "slack": f"*{s}*"}.get(fmt, s)


def units(d: dict, fmt: str, per_category: int = highlights.PER_CATEGORY, link: str = "", with_header: bool = True) -> list[tuple[str, str]]:
    """一期拆成排版好的小块 [(所属段落标题, 文本)]，拆分消息时按块装箱；段落标题用于续页时重复小标题"""
    br = "\n\n" if fmt == "md" else "\n"     # 钉钉 / 企业微信的 Markdown 要空一行才换行
    out: list[tuple[str, str]] = []
    sections = d.get("highlights")
    if sections is None:
        sections = highlights.select(d["sections"], d["window_end"])
    cats = len(sections)
    count = sum(len(s["items"][:highlights.PER_CATEGORY]) for s in sections)
    stat = f"共 {d['total']} 篇报道，来自 {cats} 个分类，精选 {count} 件事"
    out.append(("", (_bold(headline(d), fmt) + br if with_header else "") + _esc(stat, fmt)))
    for s in sections:
        head = f"【{s['category']}】"
        out.append((s["category"], _bold(head, fmt)))
        for i, it in enumerate(s["items"][:highlights.PER_CATEGORY], 1):
            line = f"{i}. {_link(it['title'], it['url'], fmt)}"
            if fmt == "text" and it.get("url"):
                line += "\n   " + it["url"]
            out.append((s["category"], line))
    if link:
        out.append(("", f"查看全部 {d['total']} 条 → " + (_link(link, link, fmt) if fmt != "text" else link)))
    return out


def _size(s: str, unit: str) -> int:
    return len(s.encode("utf-8")) if unit == "bytes" else len(s)


def _cut(s: str, n: int, unit: str) -> str:
    if _size(s, unit) <= n:
        return s
    if unit == "bytes":
        return s.encode("utf-8")[: n - 3].decode("utf-8", "ignore") + "…"
    return s[: n - 1] + "…"


def split(us: list[tuple[str, str]], limit: tuple[int, str] | None, fmt: str) -> list[str]:
    """按渠道上限把小块装箱成几条消息；换条时如果正处在某个分类中间，重复它的小标题并注明“续”"""
    sep = "\n\n"

    def gap(prev_sec, sec):
        """段落之间空一行；同一段里的条目紧挨着（Markdown 要空行才换行，照样空一行）"""
        return "\n" if fmt != "md" and sec and sec == prev_sec else sep
    if not limit:
        out, prev = "", None
        for sec, text in us:
            out = (out + gap(prev, sec) + text) if out else text
            prev = sec
        return [out]
    n, unit = limit
    n -= 40   # 给“（续 2/3）”留位置
    parts, cur, cur_sec, heads = [], "", None, {}
    for sec, text in us:
        if sec and sec not in heads:
            heads[sec] = text          # 每段第一块就是小标题
        text = _cut(text, n, unit)
        cand = (cur + gap(cur_sec, sec) + text) if cur else text
        if _size(cand, unit) <= n:
            cur, cur_sec = cand, sec
            continue
        parts.append(cur)
        cur = text
        if sec and sec == cur_sec and heads.get(sec) and heads[sec] != text:
            cur = heads[sec].rstrip() + _esc("（续）", fmt) + gap(sec, sec) + text
        cur_sec = sec
    if cur:
        parts.append(cur)
    return parts


def messages(d: dict, t: str, c: dict, token: str | None = None) -> list[tuple[str, str]]:
    """一期在某个渠道上的消息列表 [(标题, 正文)]"""
    fmt = notify.fmt_of(t, c)
    with_header = t not in notify.TITLE_FIELD
    bodies = split(units(d, fmt, link=public_link(d, token), with_header=with_header), notify.limit_of(t, c), fmt)
    title = headline(d)
    if len(bodies) == 1:
        return [(title, bodies[0])]
    total = len(bodies)
    out = []
    for i, b in enumerate(bodies, 1):
        mark = f"（{i}/{total}）"
        out.append((title + mark, b if (i == 1 or not with_header) else _esc(mark, fmt) + "\n" + b))
    return out


# ---------------- 推送 ----------------
def push(db, it: Issue, types: list[str] | None = None) -> list[dict]:
    """把一期推到已启用的渠道（types 给了就只推这些），记录结果、更新这一期的状态"""
    cfg = notify.load_config()
    todo = [t for t in (types or notify.enabled_types()) if t in cfg and not notify.missing(t, cfg[t])]
    d = issue_dict(it)
    results = []
    for t in todo:
        r = notify.deliver(t, cfg[t], messages(d, t, cfg[t], it.token))
        db.add(Delivery(issue_id=it.id, channel=t, ok=int(r["ok"]), error=r["error"] or None,
                        attempts=r["attempts"], parts=r["parts"], ts=int(time.time())))
        results.append(r)
    db.flush()   # 会话关了 autoflush：先把刚记的结果写进去，下面才查得到
    latest = {}
    for dv in db.scalars(select(Delivery).where(Delivery.issue_id == it.id).order_by(Delivery.id)):
        latest[dv.channel] = dv.ok
    if not latest:
        it.status = "nochannel"
    elif all(latest.values()):
        it.status = "sent"
    elif any(latest.values()):
        it.status = "partial"
    else:
        it.status = "failed"
    return results


def last_end(db) -> int | None:
    return db.scalar(select(Issue.window_end).order_by(Issue.window_end.desc()).limit(1))


def run(db, kind: str, now: float | None = None, client=None, ai_transport=None) -> Issue:
    """生成并推送一期（定时任务和「立即推送」都走这里）。没有新文章时只记一期“空”，不推送"""
    start, end = window(kind, now, last_end=last_end(db) if kind == "manual" else None)
    if kind != "manual":
        # 同一期已经生成过（服务重启后补跑、手动又点了一次）：不重复推送
        done = db.scalar(select(Issue).where(Issue.kind == kind, Issue.window_end == end))
        if done is not None:
            return done
    sync(db, start - 60, client)
    data = build(db, kind, start, end, ai_transport)
    it = save(db, data)
    if data["total"]:
        push(db, it)
    db.commit()
    return it


def preview(db, kind: str = "manual", now: float | None = None, client=None, ai_transport=None) -> dict:
    """网页预览：同样同步、生成，但不存期、不标记已推"""
    start, end = window(kind, now, last_end=last_end(db) if kind == "manual" else None)
    sync(db, start - 60, client)
    db.commit()
    data = build(db, kind, start, end, ai_transport)
    data.pop("_ids", None)
    return {**data, "id": None, "created": int(time.time()), "status": "preview"}


def cleanup(db) -> dict:
    """删掉超过保留天数的期、推送记录和文章缓存"""
    days = max(1, int(prefs.get("site").get("retention_days") or 10))
    cut = int(time.time()) - days * 86400
    old = list(db.scalars(select(Issue.id).where(Issue.created < cut)))
    n_del = 0
    for i in range(0, len(old), 500):
        n_del += db.execute(delete(Delivery).where(Delivery.issue_id.in_(old[i:i + 500]))).rowcount or 0
    n_issue = db.execute(delete(Issue).where(Issue.created < cut)).rowcount or 0
    n_art = db.execute(delete(Article).where(Article.crawled < cut)).rowcount or 0
    db.commit()
    return {"issues": n_issue, "deliveries": n_del, "articles": n_art}
