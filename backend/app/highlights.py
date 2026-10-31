"""本地分类精选：保守归并相似标题，选代表事件，不生成事实或调用外部服务。"""
import html
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from urllib.parse import urlsplit

PER_CATEGORY = 8
_PROMO = re.compile(r"广告|推广|赞助|优惠券|限时优惠|买一送一|领福利|点击领取|点击查看|好物推荐|限时抢购")
_EMPTY = re.compile(r"^(今日资讯|每日新闻|新闻汇总|点击查看|阅读全文|精彩内容|早报|晚报)[！!。\s]*$")
_ACTIONS = (r"增长|上涨|上升", r"下降|下跌|减少", r"发布|宣布|推出|上线", r"召回|撤回", r"取消|终止", r"批准|通过", r"拒绝|否认")


def clean_title(title: str, source: str = "") -> str:
    title = html.unescape(title or "")
    title = re.sub(r"</?[a-zA-Z][^>]*>", "", title)
    title = re.sub(r"^\s*[【\[](快讯|速报|广告|推广|赞助)[】\]]\s*", "", title)
    if source:
        source = source.strip()
        title = re.sub(r"\s*(?:[-—|｜_]\s*" + re.escape(source) + r"|[【\[]" + re.escape(source) + r"[】\]])\s*$", "", title)
    return re.sub(r"\s+", " ", title).strip()


def _norm(title):
    value = re.sub(r"[^\w.%]+|_", "", unicodedata.normalize("NFKC", title).casefold())
    return re.sub(r"(?<!\d)\.|\.(?!\d)", "", value)


def _grams(title):
    return {title[i:i + 3] for i in range(len(title) - 2)}


def _same(a, b):
    if a == b:
        return True
    if min(len(a), len(b)) < 10:
        return False
    if re.findall(r"\d+(?:\.\d+)?", a) != re.findall(r"\d+(?:\.\d+)?", b):
        return False
    if {i for i, p in enumerate(_ACTIONS) if re.search(p, a)} != {i for i, p in enumerate(_ACTIONS) if re.search(p, b)}:
        return False
    # 主体和否定词不同，不因其余措辞相似而合并；宁可漏合并，也不混淆不同事件。
    verb = "|".join(_ACTIONS)
    subject_a = re.sub(r"(正式|今日|今天|最新|刚刚|现已)$", "", re.split(verb, a, maxsplit=1)[0])
    subject_b = re.sub(r"(正式|今日|今天|最新|刚刚|现已)$", "", re.split(verb, b, maxsplit=1)[0])
    if re.search(verb, a) and subject_a != subject_b:
        return False
    if bool(re.search(r"未|不|没有|否认", a)) != bool(re.search(r"未|不|没有|否认", b)):
        return False
    ga, gb = _grams(a), _grams(b)
    return len(ga & gb) / max(len(ga | gb), 1) >= 0.5 and SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.82


def _publisher(item):
    try:
        host = (urlsplit(item.get("url") or "").hostname or "").lower().rstrip(".")
    except ValueError:
        host = ""
    if host:
        parts = host.split(".")
        count = 3 if ".".join(parts[-2:]) in {"com.cn", "net.cn", "org.cn", "co.uk", "com.au"} else 2
        return ".".join(parts[-count:])
    return _norm(item.get("source") or "")


def _quality(item):
    title = item["clean"]
    original = item["raw"].get("title") or ""
    score = min(len(_norm(title)), 40) / 20
    score -= 8 if _PROMO.search(original) else 0
    score -= 4 if not title or _EMPTY.match(title) else 0
    return score


def _stamp(item, end):
    # 异常的未来时间不能挤占正常新闻的名额。
    return min(int(item.get("published") or item.get("crawled") or 0), end)


def select(sections: list[dict], end: int) -> list[dict]:
    """每类最多 8 个事件；输入及全部文章不变，输出只包含代表标题、链接与统计。"""
    result = []
    for section in sections:
        groups, anchors, by_url, by_title = [], [], {}, {}
        index = defaultdict(list)
        rows = sorted(section["items"], key=lambda x: (-_stamp(x, end), str(x.get("id", ""))))
        for raw in rows:
            title = clean_title(raw.get("title") or "", raw.get("source") or "")
            norm = _norm(title)
            if not norm:
                continue
            grams = _grams(norm)
            url = (raw.get("url") or "").split("#", 1)[0].rstrip("/")
            # 只检查稀有片段的有限候选，避免万条相似模板标题产生平方级比较。
            buckets = sorted((index[g] for g in sorted(grams) if index[g]), key=len)
            candidates = Counter(i for bucket in buckets[:6] for i in bucket[:128])
            group = by_url.get(url) if url else None
            if group is None:
                group = by_title.get(norm)
            if group is None:
                group = next((i for i, _ in candidates.most_common(12) if _same(norm, anchors[i])), None)
            if group is None:
                group = len(groups)
                groups.append([])
                anchors.append(norm)
                for gram in grams:
                    index[gram].append(group)
            groups[group].append({"raw": raw, "clean": title})
            by_title[norm] = group
            if url:
                by_url[url] = group

        ranked = []
        for group in groups:
            representative = max(group, key=lambda x: (_quality(x), _stamp(x["raw"], end), x["clean"]))
            raw = representative["raw"]
            sources = {_publisher(x["raw"]) for x in group} - {""}
            age = max(0, end - max(_stamp(x["raw"], end) for x in group))
            freshness = 2 * max(0, 1 - age / 86400)
            score = _quality(representative) + 2 * min(max(len(sources) - 1, 0), 3) + freshness
            point = {"id": raw.get("id"), "title": representative["clean"], "url": raw.get("url") or "",
                     "reports": len(group), "sources": len(sources)}
            ranked.append((score, _stamp(raw, end), point))
        ranked.sort(key=lambda x: (-x[0], -x[1], str(x[2]["id"])))
        result.append({"category": section["category"], "items": [x[2] for x in ranked[:PER_CATEGORY]]})
    return result
