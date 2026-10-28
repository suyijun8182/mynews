"""AI「今日要点」：OpenAI 兼容的 /chat/completions（DeepSeek、通义千问、Kimi、Ollama 等都能用）。

把本期文章编号后交给模型，要它挑 5～8 条要点，每条带上依据的文章编号，用来在消息里附原文链接。
模型没按格式回答时，按行拆成要点、不带链接；调用失败抛 AIError，由调用方在消息里注明后照常推送。
"""
import json
import re

import httpx

MAX_INPUT = 150      # 最多给模型多少条（按分类轮流取，免得被某一个大分类占满）
TIMEOUT = 90.0

PROMPT = """你是新闻编辑。下面是本期从订阅源收集的新闻，每行格式为「编号. [分类] 标题 —— 摘要」。
请提炼 5 到 8 条「今日要点」：合并重复报道，优先重要、影响面广的事件，每条用一两句中文概括。
只输出 JSON 数组，不要任何其他文字，格式：[{"text": "要点", "refs": [依据的新闻编号]}]"""


class AIError(RuntimeError):
    pass


def _pick(articles: list[dict]) -> list[dict]:
    by_cat: dict[str, list] = {}
    for a in articles:
        by_cat.setdefault(a.get("category") or "", []).append(a)
    out, i = [], 0
    while len(out) < MAX_INPUT and any(i < len(v) for v in by_cat.values()):
        for v in by_cat.values():
            if i < len(v) and len(out) < MAX_INPUT:
                out.append(v[i])
        i += 1
    return out


def parse_points(text: str, n: int) -> list[dict]:
    """解析模型输出：优先 JSON；不是 JSON 时按行拆。refs 只保留 1..n 范围内的编号"""
    s = (text or "").strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    m = re.search(r"\[.*\]", s, re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            pts = []
            for x in data:
                if isinstance(x, dict) and str(x.get("text") or "").strip():
                    refs = [int(r) for r in x.get("refs") or [] if str(r).isdigit() and 1 <= int(r) <= n]
                    pts.append({"text": str(x["text"]).strip()[:300], "refs": refs[:3]})
            if pts:
                return pts[:8]
        except (ValueError, TypeError):
            pass
    lines = [re.sub(r"^\s*(\d+[.、)]|[-*•])\s*", "", ln).strip() for ln in s.splitlines()]
    return [{"text": ln[:300], "refs": []} for ln in lines if ln][:8]


def summarize(cfg: dict, articles: list[dict], transport=None) -> tuple[list[dict], list[dict]]:
    """返回 (要点, 交给模型的文章列表)：要点里的 refs 是这个列表的 1 起编号"""
    if not cfg.get("base_url") or not cfg.get("api_key") or not cfg.get("model"):
        raise AIError("AI 摘要没有配置完整（接口地址、API Key、模型）")
    picked = _pick(articles)
    if not picked:
        return [], []
    lines = [f"{i}. [{a.get('category') or '未分类'}] {a['title']} —— {a.get('summary') or ''}"[:300]
             for i, a in enumerate(picked, 1)]
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    try:
        with httpx.Client(timeout=TIMEOUT, transport=transport) as c:
            r = c.post(url, headers={"Authorization": f"Bearer {cfg['api_key']}"}, json={
                "model": cfg["model"], "temperature": 0.3,
                "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": "\n".join(lines)}]})
    except httpx.HTTPError as e:
        raise AIError(f"连不上 AI 接口：{type(e).__name__}") from e
    if r.status_code >= 400:
        raise AIError(f"AI 接口返回 HTTP {r.status_code}：{r.text[:150]}")
    try:
        content = r.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise AIError("AI 接口返回格式不对（是 OpenAI 兼容接口吗？）") from e
    points = parse_points(content, len(picked))
    if not points:
        raise AIError("AI 没有给出要点")
    return points, picked
