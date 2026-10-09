"""数据抓取器抽象层 (借鉴 AIMedia spider_all.py + article-gen RSS 哲学)

提供统一接口 BaseFetcher,支持:
- RSSFetcher: 抓取 RSS 订阅源 (最稳定)
- APIFetcher: 抓取 GitHub 等 API 接口
- HTMLFetcher: 抓取 HTML 页面 (预留扩展点)
- BrowserFetcher: 浏览器自动化 (二期实现)
"""
from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime, timedelta
import requests
import feedparser

from services.news.field_extractor import extract_all, announce_type_from_title


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
    # 商机字段 (由 field_extractor 从详情页提取)
    bid_deadline: str = ""
    amount: Optional[float] = None
    region: str = ""
    owner_org: str = ""
    project_code: str = ""
    announce_type: str = "tender"  # tender/award/change/failed
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
                    # 从详情正文提取商机字段
                    biz = extract_all(detail_content)
                    if biz.get("bid_deadline"):
                        item.bid_deadline = biz["bid_deadline"]
                    if biz.get("amount"):
                        item.amount = biz["amount"]
                    if biz.get("region"):
                        item.region = biz["region"]
                    if biz.get("owner_org"):
                        item.owner_org = biz["owner_org"]
                    if biz.get("project_code"):
                        item.project_code = biz["project_code"]

            item.announce_type = announce_type_from_title(item.title or "")
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
    RE_COMPACT_DATE = None

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
            HTMLFetcher.RE_COMPACT_DATE = _re.compile(r'/(\d{4})(\d{2})(\d{2})/')

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
        import re
        import httpx
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True, headers=self._headers(),
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                if resp.charset_encoding:
                    return resp.content.decode(resp.charset_encoding, errors="replace")
                # Content-Type 未声明 charset 时从 HTML meta 嗅探(httpx 不做 meta
                # 嗅探,政府/招标站点多为 GBK/GB2312,按默认 utf-8 解码会乱码)
                m = re.search(rb'charset\s*=\s*["\']?([A-Za-z0-9_\-]+)',
                              resp.content[:4096], re.I)
                encoding = m.group(1).decode("ascii", "ignore") if m else "utf-8"
                try:
                    return resp.content.decode(encoding, errors="replace")
                except LookupError:  # meta 里是无效 charset 名
                    return resp.content.decode("utf-8", errors="replace")
        except Exception:
            return None

    async def fetch(self, source_config: dict) -> List[NewsItem]:
        url = source_config.get("url", "")
        if not url:
            return []
        cfg = source_config.get("config") or {}
        max_items = int(cfg.get("max_items", 12))
        # include_pattern: href 必须匹配的正则, 过滤导航/统计等噪声链接
        # (如 ggzy 首页混有 ">>更多"/交易量统计等非公告链接)
        include_re = None
        if cfg.get("include_pattern"):
            try:
                import re as _re
                include_re = _re.compile(cfg["include_pattern"])
            except _re.error:
                pass

        html = await self._get(url)
        if not html:
            raise FetchError(f"HTML 抓取失败: {url}")

        entries = self._parse_list_page(html, url, include_re=include_re)[:max_items]
        items: List[NewsItem] = []
        for e in entries:
            content = await self._get(e["url"]) if e["url"] else None
            text = self._extract_content(content) if content else ""
            # 从详情正文提取商机字段 (截止时间/金额/地域/采购人/项目编号)
            biz_fields = extract_all(text)
            items.append(NewsItem(
                title=e["title"],
                url=e["url"],
                source=source_config.get("name", ""),
                pub_date=e.get("pub_date", ""),
                content=text[:5000],
                source_code=source_config.get("code", ""),
                industry_code=source_config.get("industry", ""),
                bid_deadline=biz_fields.get("bid_deadline", ""),
                amount=biz_fields.get("amount"),
                region=biz_fields.get("region", ""),
                owner_org=biz_fields.get("owner_org", ""),
                project_code=biz_fields.get("project_code", ""),
                announce_type=announce_type_from_title(e["title"]),
                extra={"fetch_type": "crawl"},
            ))
        return items

    def _parse_list_page(self, html: str, base_url: str, include_re=None) -> List[dict]:
        from urllib.parse import urljoin

        items: List[dict] = []
        seen = set()
        for attrs, inner in self.RE_ANCHOR.findall(html):
            # 标题优先取 title 属性(如新疆平台 title=公告名, 内嵌 span 装饰文本)
            hm = self.RE_HREF.search(attrs)
            if not hm:
                continue
            href = hm.group(1)
            if include_re is not None and not include_re.search(href):
                continue
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
            else:
                # 紧凑日期段: ggzy.gov.cn href 形如 /.../20261009/xxx.html
                m2 = self.RE_COMPACT_DATE.search(href)
                if m2 and 1 <= int(m2.group(2)) <= 12 and 1 <= int(m2.group(3)) <= 31:
                    pub_date = f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"

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
        # 反爬壳页(如千里马)正文常是 JS 脚本, 先剔除 script/style/noscript 再匹配/兜底
        html = self.RE_SCRIPT.sub(' ', html)
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

    RE_SCRIPT = re.compile(
        r'<(script|style|noscript)\b[^>]*>.*?</\1\s*>', re.DOTALL | re.IGNORECASE
    )


class EpointFetcher(BaseFetcher):
    """Epoint WebBuilder 政务平台 ES 检索接口抓取器 (epoint 类型)

    新疆/宁夏等公共资源交易平台基于 Epoint WebBuilder: 栏目页是 JS 壳,
    静态抓取只能拿到占位符,真实数据来自 ES 全文检索 REST 接口
    (getFullTextDataNew)。分类过滤必须用 condition/unionCondition 携带
    叶子分类号——cnum 字段只对顶级分类生效 (2026-09 实测)。

    source_config:
      url: 栏目页地址 (用于派生 Origin/Referer 和拼接详情链接)
      config.api_path: ES 接口路径
      config.categories: 叶子分类号列表 (unionCondition OR 关系)
      config.max_items: 最多返回条数 (默认 12)
    """

    async def fetch(self, source_config: dict) -> List[NewsItem]:
        import httpx
        from urllib.parse import urljoin

        page_url = source_config.get("url", "")
        cfg = source_config.get("config") or {}
        api_path = cfg.get("api_path", "")
        categories = [c for c in (cfg.get("categories") or []) if c]
        max_items = int(cfg.get("max_items", 12))
        if not page_url or not api_path or not categories:
            raise FetchError("Epoint 源缺少 url/api_path/categories 配置")

        base = "/".join(page_url.split("/", 3)[:3])  # scheme://host
        api_url = base + api_path
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json",
            "Origin": base,
            "Referer": page_url,
        }
        payload = {
            "token": "", "pn": 0, "rn": max_items, "sdt": "", "edt": "",
            "wd": "", "inc_wd": "", "exc_wd": "",
            "fields": "title",
            "cnum": "",
            "sort": '{"webdate":"0"}',  # 按发布时间降序
            "ssort": "title", "cl": 500, "terminal": "",
            "condition": "[]", "time": None, "highlights": "",
            "statistics": None,
            "unionCondition": EpointFetcher._category_condition(categories),
            "accuracy": "100", "noParticiple": "0",
            "searchRange": None, "isBusiness": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=25, verify=False, headers=headers) as client:
                resp = await client.post(api_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            raise FetchError(f"Epoint 检索接口失败: {api_url} {e}")

        records = (data.get("result") or {}).get("records") or []
        items: List[NewsItem] = []
        for rec in records:
            title = str(rec.get("title") or "").strip()
            if not title:
                continue
            link = str(rec.get("linkurl") or "").strip()
            content = str(rec.get("content") or "").strip()
            item = NewsItem(
                title=title[:150],
                url=urljoin(page_url, link) if link else "",
                source=source_config.get("name", ""),
                pub_date=str(rec.get("webdate") or "")[:10],
                content=content[:800],
                source_code=source_config.get("code", ""),
                industry_code=source_config.get("industry", ""),
                extra={"fetch_type": "epoint",
                       "categorynum": str(rec.get("categorynum") or "")},
            )
            # Epoint 接口的 content 常是详情页正文片段, 尝试提取商机字段
            biz = extract_all(content)
            item.bid_deadline = biz.get("bid_deadline", "") or item.bid_deadline
            item.amount = biz.get("amount") or item.amount
            item.region = biz.get("region", "") or item.region
            item.owner_org = biz.get("owner_org", "") or item.owner_org
            item.project_code = biz.get("project_code", "") or item.project_code
            item.announce_type = announce_type_from_title(title)
            items.append(item)
        return items

    @staticmethod
    def _category_condition(categories: List[str]) -> str:
        import json as _json
        return _json.dumps([
            {"equal": c, "equalList": None, "fieldName": "categorynum",
             "notEqual": None, "notEqualList": None}
            for c in categories
        ], separators=(",", ":"))

    USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


class BrowserFetcher(BaseFetcher):
    """JS 渲染抓取器 (browser 类型, 基于 crawl4ai 无头浏览器)

    用于反爬加密壳站 — cebpubservice 全站挂 interfaceacting/antidom 混淆 JS,
    静态 httpx 只能拿到混淆壳, 必须由浏览器执行壳 JS 后从渲染 DOM 提取数据。
    依赖: pip install crawl4ai && playwright install chromium

    source_config:
      url: 列表页地址, 支持 {today} 占位符 (YYYY-MM-DD, 用于 searchDate 参数)
      config.max_items: 最多返回条数 (默认 15)
    """

    # 渲染后的列表行为 markdown 表格:
    # | [标题截断](javascript:urlOpen\('uuid'\) "完整标题") | 行业 | 【地区】 | 来源 | 日期 |
    RE_ROW = None
    RE_DATE = None
    RE_REGION = None

    DETAIL_URL = "https://ctbpsp.com/#/bulletinDetail?uuid={uuid}&inpvalue=&dataSource=0&tenderAgency="

    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        import re as _re
        if BrowserFetcher.RE_ROW is None:
            BrowserFetcher.RE_ROW = _re.compile(
                r'\|\s*\[([^\]]+)\]\(javascript:urlOpen[^\']*\'([0-9a-f]{16,40})\'[^"]*\"([^\"]*)\"'
            )
            BrowserFetcher.RE_DATE = _re.compile(r"(\d{4}-\d{2}-\d{2})")
            BrowserFetcher.RE_REGION = _re.compile(r"【([^】]{1,12})】")

    async def fetch(self, source_config: dict) -> List[NewsItem]:
        url = source_config.get("url", "").replace(
            "{today}", datetime.now().strftime("%Y-%m-%d"))
        if not url:
            return []
        cfg = source_config.get("config") or {}
        max_items = int(cfg.get("max_items", 15))

        try:
            from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
        except ImportError:
            raise FetchError(
                "browser 类型需要 crawl4ai: pip install crawl4ai && playwright install chromium")

        # chromium 二进制装在共享路径 (部署时 playwright install 到 /opt/ms-playwright,
        # 容器内应用用户 999 与安装用户 root 的 HOME 不同, 必须显式指定)
        import os
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/ms-playwright")

        try:
            # 每源新建 chromium 实例 (启动约 1-2s), 简单可靠
            async with AsyncWebCrawler(verbose=False, headless=True) as crawler:
                result = await crawler.arun(
                    url, config=CrawlerRunConfig(page_timeout=self.timeout * 1000))
        except Exception as e:
            raise FetchError(f"JS 渲染抓取失败: {url} ({str(e)[:120]})")

        items = self._parse_markdown(result.markdown or "", source_config)[:max_items]
        if not items:
            raise FetchError(f"JS 渲染完成但未解析到公告条目: {url}")
        return items

    def _parse_markdown(self, md: str, source_config: dict) -> List[NewsItem]:
        items: List[NewsItem] = []
        seen = set()
        for line in md.splitlines():
            m = self.RE_ROW.search(line)
            if not m:
                continue
            truncated, uuid, full_title = m.group(1).strip(), m.group(2), m.group(3).strip()
            title = BrowserFetcher._clean_md(full_title or truncated)
            if len(title) < 8 or uuid in seen:
                continue
            seen.add(uuid)
            # 地区取链接之后的表格列 (标题内也可能含【】, 不能从标题取)
            region_m = self.RE_REGION.search(line[m.end():])
            date_m = self.RE_DATE.search(line[m.end():])
            items.append(NewsItem(
                title=title[:150],
                url=self.DETAIL_URL.format(uuid=uuid),
                source=source_config.get("name", ""),
                pub_date=date_m.group(1) if date_m else datetime.now().strftime("%Y-%m-%d"),
                content="",
                source_code=source_config.get("code", ""),
                industry_code=source_config.get("industry", ""),
                region=region_m.group(1) if region_m else "",
                announce_type=announce_type_from_title(title),
                extra={"fetch_type": "browser"},
            ))
        return items

    @staticmethod
    def _clean_md(s: str) -> str:
        import re as _re
        return _re.sub(r"\s+", " ", s.replace("\\", "")).strip()


FETCHER_REGISTRY = {
    "rss": RSSFetcher,
    "api": APIFetcher,
    "html": HTMLFetcher,
    "crawl": HTMLFetcher,  # 同 HTML
    "epoint": EpointFetcher,
    "browser": BrowserFetcher,
}


def get_fetcher(source_type: str) -> BaseFetcher:
    fetcher_cls = FETCHER_REGISTRY.get(source_type)
    if not fetcher_cls:
        raise FetchError(f"不支持的抓取类型: {source_type}")
    return fetcher_cls()
