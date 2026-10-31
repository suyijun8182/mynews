import copy

import pytest

from app import highlights


NOW = 1_800_000_000


def story(n, title, source="新闻社", age=0, **extra):
    return {"id": str(n), "title": title, "source": source,
            "url": f"https://{source}.example/{n}", "summary": "不应出现在推送中的正文",
            "crawled": NOW - age, "published": NOW - age, **extra}


def selected(items):
    return highlights.select([{"category": "科技", "items": items}], NOW)[0]["items"]


def test_clean_title_preserves_facts():
    assert highlights.clean_title("【快讯】央行宣布降准0.5个百分点 - 财经日报", "财经日报") == "央行宣布降准0.5个百分点"
    assert highlights.clean_title("美国 - 加拿大达成协议", "国际日报") == "美国 - 加拿大达成协议"


def test_merge_event_and_choose_informative_headline():
    rows = [story(1, "央行宣布降准0.5个百分点，释放长期资金", "甲报"),
            story(2, "央行正式宣布降准0.5个百分点，释放长期资金", "乙报")]
    events = selected(rows)
    assert len(events) == 1 and events[0]["reports"] == 2 and events[0]["sources"] == 2
    assert events[0]["title"] in [s["title"] for s in rows]
    assert "summary" not in events[0]


@pytest.mark.parametrize("titles", [
    ("苹果发布新款MacBook Pro笔记本电脑", "苹果召回旧款MacBook Pro笔记本电脑"),
    ("央行宣布降准0.5个百分点", "央行宣布降准0.25个百分点"),
    ("甲公司第三季度净利润增长20%", "甲公司第三季度净利润下降20%"),
    ("新闻标题 1", "新闻标题 2"),
    ("甲公司发布第三季度财务报告", "乙公司发布第三季度财务报告"),
    ("甲公司宣布收购乙公司全部股权", "甲公司未宣布收购乙公司全部股权"),
    ("甲公司净利润增长1.2亿元", "甲公司净利润增长12亿元"),
])
def test_related_but_different_events_stay_separate(titles):
    assert len(selected([story(i, title) for i, title in enumerate(titles)])) == 2


def test_independent_sources_outrank_reposts_and_ads():
    rows = [story(i, "央行宣布降准0.5个百分点，释放长期资金", source)
            for i, source in enumerate(["甲报", "乙报", "丙报"])]
    rows += [story(20 + i, "限时优惠！领取优惠券，买一送一", "商城") for i in range(20)]
    assert selected(rows)[0]["title"].startswith("央行")
    assert selected(rows)[0]["sources"] == 3
    assert next(x for x in selected(rows) if "优惠" in x["title"])["sources"] == 1


def test_informative_and_fresh_news_outrank_empty_and_stale():
    rows = [story(1, "点击查看", age=0), story(2, "卫星成功发射进入预定轨道", age=86400),
            story(3, "火箭成功发射进入预定轨道", age=0)]
    assert selected(rows)[0]["id"] == "3"
    assert selected(rows)[-1]["id"] == "1"


def test_each_category_has_at_most_eight_and_input_is_unchanged():
    rows = [story(i, f"第{i}号卫星成功进入预定轨道") for i in range(12)]
    sections = [{"category": "科技", "items": rows}, {"category": "国内", "items": rows[:2]}]
    original = copy.deepcopy(sections)
    result = highlights.select(sections, NOW)
    assert [len(s["items"]) for s in result] == [8, 2]
    assert sections == original
    assert highlights.select(list(reversed(sections)), NOW)[1] == result[0]
    assert selected(list(reversed(rows))) == result[0]["items"]


def test_same_link_is_one_event_even_with_different_headlines():
    rows = [story(1, "火星探测任务取得进展", url="https://news.example/1"),
            story(2, "探测器完成既定科学任务", url="https://news.example/1#top")]
    assert len(selected(rows)) == 1


def test_same_publisher_subdomains_are_one_source():
    rows = [story(1, "火星探测器完成既定科学任务", url="https://news.example.com/1"),
            story(2, "火星探测器完成既定科学任务", url="https://tech.example.com/2")]
    assert selected(rows)[0]["sources"] == 1


def test_identical_short_titles_still_merge():
    assert len(selected([story(1, "降准"), story(2, "降准")])) == 1
