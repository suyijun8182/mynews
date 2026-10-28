"""早晚报：FreshRSS 读取、时间窗口、去重分组、排版拆分、推送重试、AI 要点、清理。"""
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app import digest, freshrss, notify, prefs
from app.models import Article, Delivery, Issue
from fake import FakeFreshRSS, ai_transport, item

TZ = ZoneInfo("Asia/Shanghai")


def ts(y, mo, d, h, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=TZ).timestamp())


def setup_prefs(db, **kw):
    prefs.put(db, "freshrss", {"url": "https://rss.example.com", "username": "me", "api_password": "apipass",
                                "categories": kw.get("categories", [])})
    prefs.put(db, "schedule", {"morning_on": True, "morning": "08:00", "evening_on": kw.get("evening_on", True),
                                "evening": "20:00", "per_category": kw.get("per_category", 10)})
    db.commit()


@pytest.fixture
def sent(monkeypatch):
    """假渠道：记下每次发出的 (渠道, 标题, 正文)"""
    out = []
    monkeypatch.setattr(notify, "_send_rich", lambda t, c, title, text, fmt: out.append((t, title, text, fmt)))
    return out


def enable_telegram(db):
    notify.save_config(db, {"telegram": {"enabled": True, "bot_token": "123:abc", "chat_id": "42"}})
    db.commit()


# ---------------- FreshRSS ----------------
def test_freshrss_client():
    t0 = ts(2026, 10, 29, 6)
    fake = FakeFreshRSS([item(i, t0 + i * 60) for i in range(1, 6)], page=2)
    with fake.client() as c:
        assert c.categories() == ["科技", "国内", "国际"]
        got = c.items_since(t0 + 60)          # 第 1 条正好等于 since，不要
    assert [g["title"] for g in got] == ["新闻标题 5", "新闻标题 4", "新闻标题 3", "新闻标题 2"]
    assert got[0]["summary"] == "这是 正文 开头。" and got[0]["category"] == "科技" and got[0]["source"] == "示例源"
    assert got[0]["id"] == f"{5:016x}" and got[0]["crawled"] == t0 + 300
    assert sum(p.endswith("reading-list") for p in fake.calls) == 2   # 翻页
    with pytest.raises(freshrss.FreshRSSError, match="API 密码"):
        with fake.client(password="wrong") as c:
            c.login()


def test_summary_drops_repeated_title():
    x = freshrss.parse_item(item(1, 1, title="央行降准", summary="<p>央行降准：释放长期资金约一万亿元。</p>"))
    assert x["summary"] == "释放长期资金约一万亿元。"


def test_api_base():
    assert freshrss.api_base("rss.example.com:8443/") == "https://rss.example.com:8443/api/greader.php"
    assert freshrss.api_base("https://x.com/i/") == "https://x.com/api/greader.php"
    assert freshrss.api_base("https://x.com/api/greader.php") == "https://x.com/api/greader.php"


# ---------------- 时间窗口 ----------------
def test_window_morning_evening():
    sched = {"morning_on": True, "morning": "08:00", "evening_on": True, "evening": "20:00"}
    now = ts(2026, 10, 29, 8, 0) + 5
    assert digest.window("morning", now, sched) == (ts(2026, 10, 28, 20), ts(2026, 10, 29, 8))
    assert digest.window("evening", ts(2026, 10, 29, 20) + 5, sched) == (ts(2026, 10, 29, 8), ts(2026, 10, 29, 20))
    # 只开早报：覆盖 24 小时
    only = {**sched, "evening_on": False}
    assert digest.window("morning", now, only) == (ts(2026, 10, 28, 8), ts(2026, 10, 29, 8))
    # 早报时间之前手动跑早报：取昨天那一期
    assert digest.window("morning", ts(2026, 10, 29, 7), sched) == (ts(2026, 10, 27, 20), ts(2026, 10, 28, 8))
    # 立即推送：从上一期结束到现在，最多 24 小时
    n = ts(2026, 10, 29, 12)
    assert digest.window("manual", n, sched, last_end=ts(2026, 10, 29, 8)) == (ts(2026, 10, 29, 8), n)
    assert digest.window("manual", n, sched, last_end=None) == (n - 86400, n)


# ---------------- 生成一期 ----------------
def test_collect_dedupe_and_categories(db):
    setup_prefs(db, categories=["科技", "未分类"])
    t0 = ts(2026, 10, 29, 3)
    fake = FakeFreshRSS([
        item(1, t0, title="同一条新闻", url="https://a.com/x"),
        item(2, t0 + 60, title="同一条新闻！", url="https://b.com/y"),      # 标题只差标点：重复
        item(3, t0 + 120, title="另一条", url="https://a.com/x#frag"),      # 链接相同：重复
        item(4, t0 + 180, title="国内新闻", cat="国内"),                     # 没选这个分类
        item(5, t0 + 240, title="没分类的", cat=None),
    ])
    digest.sync(db, t0 - 1, fake.client())
    arts = digest.collect(db, t0 - 1, t0 + 3600)
    assert [a.title for a in arts] == ["没分类的", "另一条", "同一条新闻！"]
    secs = digest.group(arts)
    assert [s["category"] for s in secs] == ["科技", "未分类"] and len(secs[0]["items"]) == 2
    assert digest.sync(db, t0 - 1, fake.client()) == 0     # 已有的不重复存


def test_run_flow_marks_and_pushes(db, sent):
    setup_prefs(db)
    enable_telegram(db)
    now = ts(2026, 10, 29, 8) + 30
    fake = FakeFreshRSS([item(i, ts(2026, 10, 28, 21) + i * 600, cat=("科技" if i % 2 else "国际")) for i in range(1, 7)]
                        + [item(99, ts(2026, 10, 28, 19), title="窗口之前的")])
    it = digest.run(db, "morning", now=now, client=fake.client())
    assert it.total == 6 and it.status == "sent" and it.kind == "morning"
    assert db.query(Article).filter(Article.first_issue == it.id).count() == 6
    assert len(sent) == 1 and sent[0][0] == "telegram" and sent[0][3] == "html"
    body = sent[0][2]
    assert body.startswith("<b>我的新闻 · 早报 · 10月29日 周四</b>") and "共 6 条，来自 2 个分类" in body
    assert '<a href="https://news.example.com/6">新闻标题 6</a> — 示例源' in body and "窗口之前的" not in body
    dv = db.query(Delivery).filter(Delivery.issue_id == it.id).one()
    assert dv.ok == 1 and dv.parts == 1 and dv.attempts == 1
    # 同一期再跑一次：不重复生成、不重复推送
    again = digest.run(db, "morning", now=now + 60, client=fake.client())
    assert again.id == it.id and len(sent) == 1
    # 紧接着立即推送：这些文章都推过了，生成一期空的，不推送
    m = digest.run(db, "manual", now=now + 120, client=fake.client())
    assert m.total == 0 and m.status == "empty" and len(sent) == 1


def test_retry_then_fail(db, monkeypatch):
    setup_prefs(db)
    enable_telegram(db)
    calls = []

    def flaky(t, c, title, text, fmt):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("timeout https://api.telegram.org/bot123:abc/sendMessage")
    monkeypatch.setattr(notify, "_send_rich", flaky)
    fake = FakeFreshRSS([item(1, ts(2026, 10, 29, 9))])
    it = digest.run(db, "manual", now=ts(2026, 10, 29, 10), client=fake.client())
    dv = db.query(Delivery).filter(Delivery.issue_id == it.id).one()
    assert it.status == "sent" and dv.attempts == 3

    monkeypatch.setattr(notify, "_send_rich", lambda *a: (_ for _ in ()).throw(RuntimeError("boom /bot123:abc/x")))
    res = digest.push(db, it)
    assert res[0]["ok"] is False and "bot***" in res[0]["error"] and "123:abc" not in res[0]["error"]
    assert it.status == "failed"


def _issue(n_per_cat=3, cats=("科技", "国际"), total=None):
    secs = [{"category": c, "items": [{"id": f"{c}{i}", "title": f"{c}标题<{i}>", "url": f"https://x.com/{c}/{i}",
                                       "source": "源", "summary": "摘要" * 10} for i in range(1, n_per_cat + 1)]}
            for c in cats]
    return {"id": 7, "kind": "evening", "window_start": ts(2026, 10, 29, 8), "window_end": ts(2026, 10, 29, 20),
            "total": total or n_per_cat * len(cats), "sections": secs, "ai_points": None, "ai_error": None}


def test_render_formats():
    d = _issue()
    text = "\n\n".join(t for _, t in digest.units(d, "text", 2, "https://news.me/i/7?t=abc"))
    assert text.startswith("我的新闻 · 晚报 · 10月29日 周四\n共 6 条，来自 2 个分类，每个分类最多列 2 条")
    assert "【科技】（共 3 条）" in text and "1. 科技标题<1> — 源\n   摘要" in text and "   https://x.com/科技/1" in text
    assert "科技标题<3>" not in text and text.endswith("查看全部 6 条 → https://news.me/i/7?t=abc")
    html = "\n".join(t for _, t in digest.units(d, "html", 5))
    assert '<a href="https://x.com/科技/1">科技标题&lt;1&gt;</a>' in html
    md = "\n".join(t for _, t in digest.units(d, "md", 5))
    assert "**【科技】**" in md and "[科技标题<1>](https://x.com/科技/1)" in md
    slack = "\n".join(t for _, t in digest.units(d, "slack", 5))
    assert "<https://x.com/科技/1|科技标题&lt;1&gt;>" in slack
    # 没有单独标题栏的渠道才在正文里放报头
    assert not digest.units(d, "text", 5, with_header=False)[0][1].startswith("我的新闻")


def test_split_long_issue_keeps_section_heads():
    d = _issue(n_per_cat=40)
    us = digest.units(d, "text", 40)
    parts = digest.split(us, (1900, "bytes"), "text")
    assert len(parts) > 3 and all(len(p.encode()) <= 1900 for p in parts)
    joined = "\n\n".join(parts)
    for c in ("科技", "国际"):
        for i in range(1, 41):
            assert f"{c}标题<{i}>" in joined
    cont = [p for p in parts[1:] if not p.startswith("【")]
    assert all(p.startswith("【") for p in parts[1:]) or cont == []
    assert any("（续）" in p.splitlines()[0] for p in parts[1:])
    whole = digest.split(us, None, "text")[0]
    assert "【科技】\n1. 科技标题<1>" in whole and "\n\n【国际】" in whole   # 段内紧挨，段间空行
    md = digest.split(digest.units(d, "md", 40), None, "md")[0]
    assert "**【科技】**\n\n1. [科技标题<1>]" in md                          # Markdown 要空行才换行


def test_messages_numbering(db):
    setup_prefs(db, per_category=40)
    d = _issue(n_per_cat=40)
    msgs = digest.messages(d, "wecom", {"msg_type": "text"})
    assert len(msgs) > 1 and msgs[1][0].endswith(f"（2/{len(msgs)}）") and msgs[1][1].startswith(f"（2/{len(msgs)}）")
    one = digest.messages(d, "email", {})
    assert len(one) == 1 and one[0][0] == "我的新闻 · 晚报 · 10月29日 周四" and not one[0][1].startswith("我的新闻")


# ---------------- AI ----------------
def test_ai_points(db, sent):
    setup_prefs(db)
    enable_telegram(db)
    prefs.put(db, "ai", {"enabled": True, "base_url": "https://ai.example.com/v1", "api_key": "sk-test", "model": "m"})
    db.commit()
    fake = FakeFreshRSS([item(1, ts(2026, 10, 29, 9), title="甲"), item(2, ts(2026, 10, 29, 9, 5), title="乙", cat="国际")])
    t = ai_transport()
    digest.sync(db, ts(2026, 10, 29, 0), fake.client())
    data = digest.build(db, "manual", ts(2026, 10, 29, 0), ts(2026, 10, 29, 12), ai_transport=t)
    assert t.seen["auth"] == "Bearer sk-test" and t.seen["body"]["model"] == "m"
    assert data["ai_points"][0]["text"] == "要点一：重要进展" and len(data["ai_points"][0]["refs"]) == 1
    assert data["ai_points"][1]["refs"] and all(r["url"] for p in data["ai_points"] for r in p["refs"])   # 编号 99 越界丢掉
    text = "\n".join(x for _, x in digest.units({**data, "id": 1}, "text", 10))
    assert "【今日要点】\n1. 要点一：重要进展\n   https://news.example.com/" in text

    bad = digest.build(db, "manual", ts(2026, 10, 29, 0), ts(2026, 10, 29, 12), ai_transport=ai_transport(status=429))
    assert bad["ai_points"] is None and "429" in bad["ai_error"]
    text = "\n".join(x for _, x in digest.units({**bad, "id": 1}, "text", 10))
    assert "AI 要点生成失败" in text and "甲" in text


def test_ai_parse_fallback():
    from app import ai
    assert ai.parse_points("```json\n[{\"text\": \"a\", \"refs\": [\"2\", 5]}]\n```", 3) == [{"text": "a", "refs": [2]}]
    assert ai.parse_points("1. 第一条\n2、第二条\n- 第三条", 3) == [{"text": "第一条", "refs": []}, {"text": "第二条", "refs": []},
                                                                {"text": "第三条", "refs": []}]


# ---------------- 清理 ----------------
def test_cleanup(db):
    prefs.put(db, "site", {"public_url": "", "retention_days": 10})
    old = int(time.time()) - 11 * 86400
    db.add(Article(id="a1", title="旧", crawled=old))
    db.add(Article(id="a2", title="新", crawled=int(time.time())))
    it = Issue(kind="manual", window_start=old, window_end=old, created=old, total=1, content=json.dumps({"sections": []}))
    db.add(it)
    db.flush()
    db.add(Delivery(issue_id=it.id, channel="telegram", ok=1))
    db.commit()
    assert digest.cleanup(db) == {"issues": 1, "deliveries": 1, "articles": 1}
    assert [a.id for a in db.query(Article)] == ["a2"]
