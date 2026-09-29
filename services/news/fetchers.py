"""数据抓取器抽象层 (借鉴 AIMedia spider_all.py + article-gen RSS 哲学)

提供统一接口 BaseFetcher,支持:
- RSSFetcher: 抓取 RSS 订阅源 (最稳定)
- APIFetcher: 抓取 GitHub 等 API 接口
- HTMLFetcher: 抓取 HTML 页面 (预留扩展点)
- BrowserFetcher: 浏览器自动化 (二期实现)
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime, timedelta
import requests
import feedparser


@dataclass
class NewsItem:
    """统一抓取结果"""
    title: str = ""
    url: str = ""
    source: str = ""
    pub_date: str = ""
    content: str = ""
    source_code: str = ""
    industry_code: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v or k == "title"}


class FetchError(Exception):
    """抓取失败"""
    pass


class BaseFetcher(ABC):
    """抓取器基类"""
    @abstractmethod
    async def fetch(self, source_config: dict) -> List[NewsItem]:
        """根据源配置抓取,返回 NewsItem 列表"""
        raise NotImplementedError


class RSSFetcher(BaseFetcher):
    """RSS 抓取器 (借鉴 article-generation-skill)

    - 第一步:抓取 RSS feed 获取 title/url/pub_date/summary
    - 第二步 (可选):抓取详情页正文,丰富 content 字段
    """

    def __init__(self, max_age_hours: int = 168, max_items: int = 30, fetch_detail: bool = True):
        self.max_age_hours = max_age_hours
        self.max_items = max_items
        self.fetch_detail = fetch_detail

    async def fetch(self, source_config: dict) -> List[NewsItem]:
        url = source_config.get("url", "")
        if not url:
            return []

        try:
            # requests 是同步库,必须放线程池执行,否则会阻塞整个事件循环(单 worker 时拖死全部接口)
            resp = await asyncio.to_thread(
                requests.get,
                url,
                timeout=15,
                headers={"User-Agent": "BidMaster-Pro/1.0 (Tender Monitor)"},
            )
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            raise FetchError(f"RSS 抓取超时: {url}")
        except requests.exceptions.RequestException as e:
            raise FetchError(f"RSS 抓取失败: {e}")

        feed = feedparser.parse(resp.content)
        items: List[NewsItem] = []
        cutoff = datetime.now() - timedelta(hours=self.max_age_hours)

        for entry in feed.entries[: self.max_items]:
            published = entry.get("published_parsed")
            if published:
                pub_time = datetime(*published[:6])
            else:
                pub_time = datetime.now()

            if pub_time < cutoff:
                continue

            entry_url = entry.get("link", "").strip()
            summary = (entry.get("summary", "") or "")[:500]

            # 第一步:基础信息
            item = NewsItem(
                title=entry.get("title", "").strip(),
                url=entry_url,
                source=source_config.get("name", ""),
                pub_date=pub_time.isoformat(),
                content=summary,
                source_code=source_config.get("code", ""),
                industry_code=source_config.get("industry", ""),
                extra={"fetch_type": "rss"},
            )

            # 第二步:抓取详情页正文(借鉴 AIMedia spider_all.py)
            if self.fetch_detail and entry_url:
                detail_content = await self._fetch_detail_content(entry_url, summary)
                if detail_content and len(detail_content) > len(summary):
                    item.content = detail_content
                    item.extra["detail_fetched"] = True
                    item.extra["content_length"] = len(detail_content)

            items.append(item)

        return items

    async def _fetch_detail_content(self, url: str, fallback: str) -> str:
        """抓取详情页正文(借鉴 NewsCrawlerSkill._extract_content)

        优先尝试 article / content / news 正文容器,
        失败时回退到 RSS summary。
        """
        try:
            resp = await asyncio.to_thread(
                requests.get,
                url,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            resp.raise_for_status()
            html = resp.text
        except Exception:
            return fallback

        # 借鉴 NewsCrawlerSkill 的 EXTRACT_PATTERNS
        import re
        extract_patterns = [
            r'<article[^>]*>(.*?)</article>',
            r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*article[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*id="[^"]*content[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*detail[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*news[^"]*"[^>]*>(.*?)</div>',
        ]
        re_tag = re.compile(r'<[^>]+>')
        re_ws = re.compile(r'\s+')

        for pattern in extract_patterns:
            try:
                matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            except re.error:
                continue
            if matches:
                longest = max(matches, key=len)
                text = re_tag.sub('', longest)
                text = re_ws.sub(' ', text).strip()
                if len(text) > 200:
                    return text[:8000]

        # 兜底:RSS summary
        return fallback


class APIFetcher(BaseFetcher):
    """API 抓取器 (GitHub Search API 等)"""

    async def fetch(self, source_config: dict) -> List[NewsItem]:
        code = source_config.get("code", "")
        if code == "github_tender":
            return await self._fetch_github_trending(source_config)
        return []

    async def _fetch_github_trending(self, config: dict) -> List[NewsItem]:
        cfg = config.get("config") or config.get("extra_config") or {}
        languages = " ".join(
            f"language:{lang}" for lang in cfg.get("languages", ["python"])
        )
        topics = " ".join(f"topic:{t}" for t in cfg.get("topics", []))
        query = f"{languages} {topics} stars:>={cfg.get('min_stars', 5)}"

        try:
            resp = await asyncio.to_thread(
                requests.get,
                config.get("url", "https://api.github.com/search/repositories"),
                params={"q": query, "sort": "stars", "per_page": cfg.get("max_results", 20)},
                timeout=30,
                headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
        except Exception as e:
            raise FetchError(f"GitHub API 抓取失败: {e}")

        data = resp.json()
        items: List[NewsItem] = []
        cutoff = datetime.now() - timedelta(hours=168)

        # 排除自身仓库 (避免 GitHub 自我命中)
        # 读取 source_config 顶层 exclude_repos 或 cfg.exclude_repos
        exclude_repos = (
            config.get("exclude_repos")
            or cfg.get("exclude_repos")
            or ["bidmaster-pro", "BidMaster-Pro", "bidmaster_pro"]  # 默认排除本项目
        )
        # 排除关键字 (title/url 中包含则过滤)
        exclude_keywords = (
            config.get("exclude_keywords")
            or cfg.get("exclude_keywords")
            or ["bidmaster"]
        )

        for repo in data.get("items", []):
            try:
                updated = datetime.strptime(repo["updated_at"], "%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                updated = datetime.now()
            if updated < cutoff:
                continue

            full_name = (repo.get("full_name") or "").lower()
            html_url = (repo.get("html_url") or "").lower()
            name = (repo.get("name") or "").lower()
            desc = (repo.get("description") or "").lower()

            # 过滤: 仓库名命中排除列表
            if any(ex.lower() in full_name or ex.lower() in name for ex in exclude_repos):
                continue
            # 过滤: 关键字命中
            if any(kw.lower() in name or kw.lower() in html_url or kw.lower() in desc for kw in exclude_keywords):
                continue

            items.append(
                NewsItem(
                    title=repo["name"],
                    url=repo["html_url"],
                    source="GitHub Trending",
                    pub_date=updated.isoformat(),
                    content=(repo.get("description") or "")[:500],
                    source_code=config.get("code", ""),
                    industry_code="12",
                    extra={
                        "fetch_type": "api",
                        "stars": repo.get("stargazers_count", 0),
                        "language": repo.get("language", ""),
                    },
                )
            )
        return items


class HTMLFetcher(BaseFetcher):
    """HTML 列表页抓取器 (crawl 类型)

    政府招标站点普遍无 RSS 且搜索接口反爬,但公告列表页可直接访问
    (2026-09 实测 ccgp.gov.cn 列表页 200)。通用解析:
    提取 <a href> + 标题(含中文或日期) → 逐条抓详情页正文。
    """

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    RE_ANCHOR = None
    RE_HREF = None
    RE_TITLE_ATTR = None
    RE_TAG = None
    RE_WS = None
    RE_DATE = None

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        import re as _re
        if HTMLFetcher.RE_ANCHOR is None:
            HTMLFetcher.RE_ANCHOR = _re.compile(r'<a\s([^>]*)>(.*?)</a>', _re.DOTALL)
            HTMLFetcher.RE_HREF = _re.compile(r'href=["\']([^"\']+)["\']')
            HTMLFetcher.RE_TITLE_ATTR = _re.compile(r'title=["\']([^"\']+)["\']')
            HTMLFetcher.RE_TAG = _re.compile(r'<[^>]+>')
            HTMLFetcher.RE_WS = _re.compile(r'\s+')
            HTMLFetcher.RE_DATE = _re.compile(r'(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})[日号]?')

    def _headers(self) -> dict:
        import random
        return {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
        }

    async def _get(self, url: str) -> str | None:
        import httpx
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True, headers=self._headers(),
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.text
        except Exception:
            return None

    async def fetch(self, source_config: dict) -> List[NewsItem]:
        url = source_config.get("url", "")
        if not url:
            return []
        cfg = source_config.get("config") or {}
        max_items = int(cfg.get("max_items", 12))

        html = await self._get(url)
        if not html:
            raise FetchError(f"HTML 抓取失败: {url}")

        entries = self._parse_list_page(html, url)[:max_items]
        items: List[NewsItem] = []
        for e in entries:
            content = await self._get(e["url"]) if e["url"] else None
            text = self._extract_content(content) if content else ""
            items.append(NewsItem(
                title=e["title"],
                url=e["url"],
                source=source_config.get("name", ""),
                pub_date=e.get("pub_date", ""),
                content=text[:5000],
                source_code=source_config.get("code", ""),
                industry_code=source_config.get("industry", ""),
                extra={"fetch_type": "crawl"},
            ))
        return items

    def _parse_list_page(self, html: str, base_url: str) -> List[dict]:
        from urllib.parse import urljoin

        items: List[dict] = []
        seen = set()
        for attrs, inner in self.RE_ANCHOR.findall(html):
            # 标题优先取 title 属性(如新疆平台 title=公告名, 内嵌 span 装饰文本)
            hm = self.RE_HREF.search(attrs)
            if not hm:
                continue
            href = hm.group(1)
            tm = self.RE_TITLE_ATTR.search(attrs)
            title = (tm.group(1).strip() if tm else "") or self.RE_TAG.sub('', inner).strip()
            title = self.RE_WS.sub(' ', title).strip()
            if len(title) < 10 or len(title) > 200:
                continue
            # 只保留含中文的链接(过滤导航/英文页脚)
            if not any('一' <= ch <= '鿿' for ch in title):
                continue
            full_url = urljoin(base_url, href.strip())
            if not full_url.startswith("http"):
                continue
            # 公告详情一般是 .htm/.html 静态页,过滤栏目页/锚点
            if not any(full_url.split("?")[0].endswith(ext) for ext in (".htm", ".html", ".shtml")):
                continue
            if full_url in seen:
                continue
            seen.add(full_url)

            pub_date = ""
            m = self.RE_DATE.search(title) or self.RE_DATE.search(href)
            if m:
                pub_date = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"

            items.append({"title": title[:150], "url": full_url, "pub_date": pub_date})
        return items

    _CONTENT_PATTERNS = None

    def _content_patterns(self):
        import re as _re
        if HTMLFetcher._CONTENT_PATTERNS is None:
            HTMLFetcher._CONTENT_PATTERNS = [
                _re.compile(p, _re.DOTALL | _re.IGNORECASE) for p in (
                    r'<article[^>]*>(.*?)</article>',
                    r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
                    r'<div[^>]*id="[^"]*content[^"]*"[^>]*>(.*?)</div>',
                    r'<div[^>]*class="[^"]*detail[^"]*"[^>]*>(.*?)</div>',
                    r'<div[^>]*class="[^"]*news[^"]*"[^>]*>(.*?)</div>',
                    r'<div[^>]*class="[^"]*TRS_Editor[^"]*"[^>]*>(.*?)</div>',
                    r'<div[^>]*class="[^"]*text[^"]*"[^>]*>(.*?)</div>',
                )
            ]
        return HTMLFetcher._CONTENT_PATTERNS

    def _extract_content(self, html: str) -> str:
        for pattern in self._content_patterns():
            matches = pattern.findall(html)
            if matches:
                longest = max(matches, key=len)
                text = self.RE_TAG.sub('', longest)
                text = self.RE_WS.sub(' ', text).strip()
                if len(text) > 100:
                    return text[:8000]
        text = self.RE_TAG.sub('', html)
        return self.RE_WS.sub(' ', text).strip()[:5000]


class BrowserFetcher(BaseFetcher):
    """浏览器自动化抓取器 (二期实现)"""

    async def fetch(self, source_config: dict) -> List[NewsItem]:
        return []


FETCHER_REGISTRY = {
    "rss": RSSFetcher,
    "api": APIFetcher,
    "html": HTMLFetcher,
    "crawl": HTMLFetcher,  # 同 HTML
    "browser": BrowserFetcher,
}


def get_fetcher(source_type: str) -> BaseFetcher:
    fetcher_cls = FETCHER_REGISTRY.get(source_type)
    if not fetcher_cls:
        raise FetchError(f"不支持的抓取类型: {source_type}")
    return fetcher_cls()
