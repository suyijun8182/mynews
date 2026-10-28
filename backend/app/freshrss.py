"""FreshRSS 客户端：Google Reader 兼容 API（FreshRSS 设置 → 账户 → API 密码，和登录密码分开）。

只读：登录、读分类、按“进入 FreshRSS 的时间”拉文章。不改已读 / 星标状态。

- ClientLogin：POST {api}/accounts/ClientLogin，Email + Passwd，返回 Auth=…
- 分类：GET {api}/reader/api/0/tag/list?output=json，取 user/-/label/<名字>
- 文章：GET {api}/reader/api/0/stream/contents/reading-list?output=json&n=…&ot=<秒>&c=<续页>
  ot 是“比这个时间新”，FreshRSS 按条目 ID（即入库时间，微秒）比较；条目里的 crawlTimeMsec 也是入库时间
"""
import html
import re
import time

import httpx

LABEL = "user/-/label/"
PAGE = 500           # 每页条数
MAX_PAGES = 20       # 一次最多拉 1 万条，防止异常数据把内存撑爆
SUMMARY_CHARS = 120


class FreshRSSError(RuntimeError):
    pass


def api_base(url: str) -> str:
    """用户填的可以是 FreshRSS 首页，也可以直接是 …/api/greader.php"""
    u = (url or "").strip().rstrip("/")
    if not u:
        raise FreshRSSError("没有填写 FreshRSS 地址")
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    if u.endswith("/api/greader.php"):
        return u
    if u.endswith("/i"):            # 从浏览器地址栏复制来的 …/i/
        u = u[:-2]
    return u + "/api/greader.php"


class Client:
    def __init__(self, url: str, username: str, api_password: str, timeout: float = 20.0, transport=None):
        self.base = api_base(url)
        self.username = username
        self.password = api_password
        self._auth = ""
        self._http = httpx.Client(timeout=timeout, follow_redirects=True, transport=transport,
                                  headers={"User-Agent": "mynews"})

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def login(self) -> None:
        if not self.username or not self.password:
            raise FreshRSSError("没有填写 FreshRSS 用户名或 API 密码")
        try:
            r = self._http.post(f"{self.base}/accounts/ClientLogin", data={"Email": self.username, "Passwd": self.password})
        except httpx.HTTPError as e:
            raise FreshRSSError(f"连不上 FreshRSS：{type(e).__name__}: {str(e)[:120]}") from e
        if r.status_code in (401, 403):
            raise FreshRSSError("登录失败：用户名或 API 密码不对（API 密码在 FreshRSS 设置 → 账户 → API 管理里设置，不是登录密码）")
        if r.status_code == 404:
            raise FreshRSSError("找不到 Google Reader API：检查地址，并在 FreshRSS 设置 → 认证 里打开「允许 API 访问」")
        if r.status_code >= 400:
            raise FreshRSSError(f"登录失败：HTTP {r.status_code}")
        m = re.search(r"^Auth=(\S+)", r.text, re.M)
        if not m:
            raise FreshRSSError("登录失败：返回内容里没有 Auth（地址是不是 FreshRSS？）")
        self._auth = m.group(1)

    def _get(self, path: str, params: dict | None = None) -> dict:
        if not self._auth:
            self.login()
        try:
            r = self._http.get(f"{self.base}/reader/api/0/{path}", params={"output": "json", **(params or {})},
                               headers={"Authorization": f"GoogleLogin auth={self._auth}"})
        except httpx.HTTPError as e:
            raise FreshRSSError(f"读取 FreshRSS 失败：{type(e).__name__}: {str(e)[:120]}") from e
        if r.status_code in (401, 403):
            raise FreshRSSError("FreshRSS 拒绝访问：API 密码可能已修改")
        if r.status_code >= 400:
            raise FreshRSSError(f"读取 FreshRSS 失败：HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError as e:
            raise FreshRSSError("FreshRSS 返回的不是 JSON") from e

    def categories(self) -> list[str]:
        tags = self._get("tag/list").get("tags") or []
        return [t["id"][len(LABEL):] for t in tags if str(t.get("id", "")).startswith(LABEL)]

    def items_since(self, since: int) -> list[dict]:
        """入库时间晚于 since（秒）的全部文章，已整理成 Article 的字段"""
        out, cont = [], None
        for _ in range(MAX_PAGES):
            params = {"n": PAGE, "ot": int(since)}
            if cont:
                params["c"] = cont
            data = self._get("stream/contents/reading-list", params)
            out += [parse_item(x) for x in data.get("items") or []]
            cont = data.get("continuation")
            if not cont:
                break
        return [x for x in out if x and x["crawled"] > since]


def _short_id(long_id: str) -> str:
    """tag:google.com,2005:reader/item/0005f2b3c4d5e6f7 → 0005f2b3c4d5e6f7"""
    return str(long_id).rsplit("/", 1)[-1][:64]


def clean_text(s: str, limit: int = SUMMARY_CHARS) -> str:
    """HTML 正文 → 一段纯文本摘要"""
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", html.unescape(s)).strip()
    return s if len(s) <= limit else s[:limit].rstrip() + "…"


def parse_item(x: dict) -> dict | None:
    if not isinstance(x, dict) or not x.get("id"):
        return None
    link = ""
    for k in ("canonical", "alternate"):
        for v in x.get(k) or []:
            if isinstance(v, dict) and v.get("href"):
                link = v["href"]
                break
        if link:
            break
    cats = [c[len(LABEL):] for c in x.get("categories") or [] if str(c).startswith(LABEL)]
    crawled = int(x.get("crawlTimeMsec") or 0) // 1000 or int(x.get("timestampUsec") or 0) // 1_000_000 \
        or int(x.get("published") or 0) or int(time.time())
    content = (x.get("summary") or x.get("content") or {}).get("content") or ""
    title = clean_text(x.get("title") or "", 500) or "（无标题）"
    body = clean_text(content, 2000)
    if body.startswith(title):   # 很多源的正文开头就是标题，摘要里不再重复
        body = body[len(title):].lstrip(" ：:。.，,-—|")
    return {
        "id": _short_id(x["id"]),
        "title": title,
        "url": link[:1000],
        "source": ((x.get("origin") or {}).get("title") or "")[:255],
        "category": (cats[0] if cats else "")[:255],
        "summary": body if len(body) <= SUMMARY_CHARS else body[:SUMMARY_CHARS].rstrip() + "…",
        "crawled": crawled,
        "published": int(x.get("published") or 0) or None,
    }
