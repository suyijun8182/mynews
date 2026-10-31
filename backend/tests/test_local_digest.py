import json

import pytest

from app import ai, digest, prefs
from app.models import Article, Issue
from fake import FakeFreshRSS, item


NOW = 1_800_000_000


def test_build_retains_every_article_and_never_calls_ai(db, monkeypatch):
    prefs.put(db, "ai", {"enabled": True, "api_key": "old-key", "model": "old-model"})
    db.commit()
    monkeypatch.setattr(ai, "summarize", lambda *a, **kw: pytest.fail("local digests must never call AI"))
    fake = FakeFreshRSS([item(i, NOW - 60, title="央行宣布降准0.5个百分点", source=f"新闻源{i}") for i in range(12)])
    digest.sync(db, NOW - 3600, fake.client())
    data = digest.build(db, "manual", NOW - 3600, NOW)
    assert data["total"] == 12 and len(data["sections"][0]["items"]) == 12
    assert len(data["highlights"][0]["items"]) == 1
    assert data["ai_points"] is None and data["ai_error"] is None
    saved = digest.save(db, data)
    db.commit()
    assert db.query(Article).filter(Article.first_issue == saved.id).count() == 12
    recovered = digest.issue_dict(saved)
    assert recovered["highlights"] == data["highlights"]
    assert len(recovered["sections"][0]["items"]) == 12


@pytest.mark.parametrize("fmt", ["text", "html", "md", "slack"])
def test_push_contains_only_eight_headlines_and_links(db, fmt):
    prefs.put(db, "schedule", {"per_category": 50})
    db.commit()
    rows = [{"id": str(i), "title": f"第{i}号卫星成功进入预定轨道", "url": f"https://news.example/{i}",
             "source": "不附来源", "summary": "不附正文", "crawled": NOW - i} for i in range(12)]
    data = {"kind": "manual", "window_end": NOW, "total": 12,
            "sections": [{"category": "科技", "items": rows}],
            "ai_points": [{"text": "旧AI要点", "refs": []}]}
    rendered = "\n".join(text for _, text in digest.units(data, fmt, 50))
    assert rendered.count("号卫星成功进入预定轨道") == 8
    assert "不附来源" not in rendered and "不附正文" not in rendered and "旧AI要点" not in rendered
    assert "https://news.example/" in rendered
    assert len(data["sections"][0]["items"]) == 12


def test_repush_old_issue_generates_local_highlights(db):
    sections = [{"category": "国内", "items": [
        {"id": "1", "title": "央行宣布降准0.5个百分点", "url": "https://a.example/1"},
        {"id": "2", "title": "央行宣布降准0.5个百分点", "url": "https://b.example/2"}]}]
    old = Issue(kind="manual", created=NOW, window_start=NOW - 3600, window_end=NOW,
                total=2, content=json.dumps({"sections": sections}), status="sent")
    db.add(old)
    db.flush()
    data = digest.issue_dict(old)
    assert len(data["highlights"][0]["items"]) == 1
    assert len(data["sections"][0]["items"]) == 2
