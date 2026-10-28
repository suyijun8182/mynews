"""测试用的假 FreshRSS（Google Reader API）和假 AI 接口：httpx.MockTransport"""
import json
import time

import httpx

from app import freshrss


def item(n: int, crawled: int, title: str | None = None, cat: str | None = "科技", url: str | None = None,
         source: str = "示例源", summary: str = "<p>这是 <b>正文</b> 开头。</p>") -> dict:
    return {
        "id": f"tag:google.com,2005:reader/item/{n:016x}",
        "crawlTimeMsec": str(crawled * 1000),
        "timestampUsec": str(crawled * 1_000_000),
        "published": crawled - 60,
        "title": title or f"新闻标题 {n}",
        "canonical": [{"href": url if url is not None else f"https://news.example.com/{n}"}],
        "categories": ["user/-/state/com.google/reading-list"] + ([f"user/-/label/{cat}"] if cat else []),
        "origin": {"streamId": "feed/1", "title": source},
        "summary": {"content": summary},
    }


class FakeFreshRSS:
    """记住收到的请求；items 按 crawl 时间新到旧返回，每页 page 条"""

    def __init__(self, items: list[dict], cats=("科技", "国内", "国际"), password="apipass", page=2):
        self.items = sorted(items, key=lambda x: -int(x["crawlTimeMsec"]))
        self.cats = cats
        self.password = password
        self.page = page
        self.calls: list[str] = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req.url.path)
        if req.url.path.endswith("/accounts/ClientLogin"):
            form = dict(x.split("=", 1) for x in req.content.decode().split("&"))
            if form.get("Passwd") != self.password:
                return httpx.Response(401, text="Error=BadAuthentication")
            return httpx.Response(200, text="SID=x\nLSID=x\nAuth=tok123\n")
        if req.headers.get("authorization") != "GoogleLogin auth=tok123":
            return httpx.Response(401)
        if req.url.path.endswith("/tag/list"):
            return httpx.Response(200, json={"tags": [{"id": "user/-/state/com.google/starred"}] +
                                             [{"id": f"user/-/label/{c}", "type": "folder"} for c in self.cats]})
        if "/stream/contents/reading-list" in req.url.path:
            ot = int(req.url.params.get("ot", 0))
            start = int(req.url.params.get("c", 0))
            rows = [x for x in self.items if int(x["crawlTimeMsec"]) // 1000 > ot]
            page = rows[start:start + self.page]
            body = {"items": page}
            if start + self.page < len(rows):
                body["continuation"] = str(start + self.page)
            return httpx.Response(200, json=body)
        return httpx.Response(404)

    def client(self, password="apipass") -> freshrss.Client:
        return freshrss.Client("https://rss.example.com", "me", password, transport=httpx.MockTransport(self.handler))


def ai_transport(content: str | None = None, status: int = 200):
    """假 OpenAI 兼容接口：回 content；没给就回两条要点"""
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(req.content)
        seen["auth"] = req.headers.get("authorization")
        if status != 200:
            return httpx.Response(status, text="quota exceeded")
        text = content if content is not None else json.dumps(
            [{"text": "要点一：重要进展", "refs": [1]}, {"text": "要点二：另一件事", "refs": [2, 99]}], ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})
    t = httpx.MockTransport(handler)
    t.seen = seen
    return t


def now() -> int:
    return int(time.time())
