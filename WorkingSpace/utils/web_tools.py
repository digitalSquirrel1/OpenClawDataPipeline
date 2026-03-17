# -*- coding: utf-8 -*-
"""
Web tools: Serper (search) + direct binary download + Jina Reader (fallback).

PDF 下载策略（优先级从高到低）：
  1. search_for_pdf()  → 从搜索结果中提取直链 PDF URL
  2. download_binary() → 直接下载 binary，验证 PDF magic bytes
  3. read_url()        → Jina Reader 抓取网页文本（fallback，保存为 .md）
"""
import io, os, re, time
import requests
from urllib.parse import quote, urlparse


# 常见 PDF 直链域名（可信度高，优先尝试）
_TRUSTED_PDF_DOMAINS = {
    "hkexnews.hk", "cninfo.com.cn", "szse.cn", "sse.com.cn",
    "csrc.gov.cn", "file.finance.sina.com.cn",
    "ndrc.gov.cn", "miit.gov.cn", "gov.cn",
    "spgchinaratings.cn", "assets-ir.tesla.com",
    "ir.lixiang.com", "ir.nio.com", "ir.xpeng.com",
}

# 已知需要 JS 渲染或登录的域（跳过直接下载，只用 Jina）
_SKIP_DIRECT_DOWNLOAD = {
    "pdf.dfcfw.com",     # 返回 HTML 脚本页
    "eastmoney.com",
    "10jqka.com.cn",
    "xueqiu.com",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/pdf,application/xhtml+xml,*/*",
}


class WebTools:
    def __init__(self, serper_key: str, jina_key: str):
        self.serper_key = serper_key
        self.jina_key   = jina_key
        self._sess = requests.Session()
        self._sess.headers.update(_HEADERS)

    # ──────────────────────────────────────────────────────────────────────────
    # Serper
    # ──────────────────────────────────────────────────────────────────────────
    def search(self, query: str, num: int = 5) -> list[dict]:
        """Return list of {title, link, snippet}. 含重试（最多 3 次）。"""
        import http.client, json as _json
        last_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                conn = http.client.HTTPSConnection("google.serper.dev", timeout=15)
                conn.request(
                    "POST", "/search",
                    body=_json.dumps({"q": query, "num": num, "hl": "zh-cn", "gl": "cn"}),
                    headers={"X-API-KEY": self.serper_key, "Content-Type": "application/json"},
                )
                data = conn.getresponse().read()
                return _json.loads(data).get("organic", [])
            except Exception as e:
                last_exc = e
                if attempt < 3:
                    time.sleep(1 * attempt)
                    continue
        print(f"  [Serper Error] {last_exc}")
        return []

    def search_for_pdf(self, query: str, num: int = 6) -> list[str]:
        """
        Search for direct PDF URLs.
        Returns list of candidate PDF URLs sorted by trustworthiness.
        """
        # Two searches: with and without filetype:pdf
        all_results = (
            self.search(f"{query} filetype:pdf", num=num) +
            self.search(query, num=num)
        )
        pdf_urls: list[str] = []
        seen: set[str] = set()
        for r in all_results:
            url = r.get("link", "")
            if not url or url in seen:
                continue
            seen.add(url)
            u_lower = url.lower()
            domain = urlparse(url).netloc.lstrip("www.")
            # Skip known JS-gated domains
            if any(sd in domain for sd in _SKIP_DIRECT_DOWNLOAD):
                continue
            # Direct PDF link
            if ".pdf" in u_lower:
                if any(td in domain for td in _TRUSTED_PDF_DOMAINS):
                    pdf_urls.insert(0, url)   # trusted → front of list
                else:
                    pdf_urls.append(url)
        return pdf_urls

    # ──────────────────────────────────────────────────────────────────────────
    # Direct binary download (for PDF / Excel / etc.)
    # ──────────────────────────────────────────────────────────────────────────
    def download_binary(self, url: str, save_path: str,
                        timeout: int = 60, max_mb: int = 50) -> bool:
        """
        Download a file as binary and save to save_path.
        Validates PDF magic bytes (%PDF) for .pdf targets.
        Returns True on success.
        """
        try:
            parsed  = urlparse(url)
            referer = f"{parsed.scheme}://{parsed.netloc}/"
            hdrs    = {**_HEADERS, "Referer": referer,
                       "Accept": "application/pdf,application/octet-stream,*/*"}
            resp = self._sess.get(url, headers=hdrs, timeout=timeout,
                                  stream=True, allow_redirects=True)
            if resp.status_code != 200:
                return False
            ct = resp.headers.get("content-type", "").lower()
            # Must be PDF-ish
            if not any(k in ct for k in ("pdf", "octet-stream", "download",
                                          "binary", "msword", "spreadsheet",
                                          "excel", "zip")):
                # If content-type is HTML, it's not a real file
                if "html" in ct or "text" in ct:
                    return False

            # Stream download with size cap
            buf = io.BytesIO()
            max_bytes = max_mb * 1024 * 1024
            for chunk in resp.iter_content(8192):
                buf.write(chunk)
                if buf.tell() > max_bytes:
                    print(f"    [Download] file exceeds {max_mb}MB, truncating")
                    break
            raw = buf.getvalue()
            if len(raw) < 512:
                return False
            # Validate PDF magic
            if save_path.lower().endswith(".pdf") and not raw.startswith(b"%PDF"):
                print(f"    [Download] not a valid PDF (magic={raw[:4]})")
                return False

            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(raw)
            return True
        except Exception as e:
            print(f"  [Download Error] {e}")
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # Jina Reader (text fallback)
    # ──────────────────────────────────────────────────────────────────────────
    def read_url(self, url: str, timeout: int = 30) -> str | None:
        """Fetch URL content as markdown via Jina Reader."""
        try:
            resp = self._sess.get(
                f"https://r.jina.ai/{url}",
                headers={
                    "Authorization": f"Bearer {self.jina_key}",
                    "X-Return-Format": "markdown",
                },
                timeout=timeout,
            )
            if resp.status_code == 200 and len(resp.text) > 100:
                return resp.text[:25000]   # cap at 25k chars
        except Exception as e:
            print(f"  [Jina Error] {e}")
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # HTML page download
    # ──────────────────────────────────────────────────────────────────────────
    def download_html(self, url: str, timeout: int = 30, max_mb: int = 10) -> bytes | None:
        """
        Download a web page as raw HTML bytes.
        Returns bytes on success, None on failure.
        """
        try:
            parsed  = urlparse(url)
            referer = f"{parsed.scheme}://{parsed.netloc}/"
            hdrs    = {**_HEADERS, "Referer": referer,
                       "Accept": "text/html,application/xhtml+xml,*/*"}
            resp = self._sess.get(url, headers=hdrs, timeout=timeout,
                                  stream=True, allow_redirects=True)
            if resp.status_code != 200:
                return None
            ct = resp.headers.get("content-type", "").lower()
            if "html" not in ct and "text" not in ct and ct != "":
                # accept unknown content-type too, but reject binary blobs
                if any(k in ct for k in ("pdf", "octet-stream", "zip", "excel")):
                    return None
            buf = io.BytesIO()
            max_bytes = max_mb * 1024 * 1024
            for chunk in resp.iter_content(8192):
                buf.write(chunk)
                if buf.tell() > max_bytes:
                    break
            raw = buf.getvalue()
            return raw if len(raw) > 200 else None
        except Exception as e:
            print(f"  [HTML Download Error] {e}")
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # Filetype search (Excel / CSV / etc.)
    # ──────────────────────────────────────────────────────────────────────────
    def search_for_filetype(self, query: str, exts: list[str],
                            num: int = 6) -> list[str]:
        """
        Search for URLs ending with one of the given extensions (e.g. xlsx, csv).
        Returns list of candidate URLs.
        """
        urls: list[str] = []
        seen: set[str] = set()
        ext_str = " OR ".join(f"filetype:{e}" for e in exts)
        all_results = (
            self.search(f"{query} ({ext_str})", num=num) +
            self.search(query, num=num)
        )
        for r in all_results:
            url = r.get("link", "")
            if not url or url in seen:
                continue
            seen.add(url)
            u_lower = url.lower()
            if any(u_lower.endswith(f".{e}") or f".{e}?" in u_lower
                   or f"/{e}" in u_lower for e in exts):
                domain = urlparse(url).netloc.lstrip("www.")
                if not any(sd in domain for sd in _SKIP_DIRECT_DOWNLOAD):
                    urls.append(url)
        return urls

    # ──────────────────────────────────────────────────────────────────────────
    # Convenience: full pipeline search → best result
    # ──────────────────────────────────────────────────────────────────────────
    def search_and_fetch(self, query: str, num: int = 3) -> tuple[str, str]:
        """
        Search → Jina-read first usable HTML result.
        Returns (source_url, markdown_content) or ("", "").
        """
        results = self.search(query, num=num)
        for r in results:
            url = r.get("link", "")
            if not url or ".pdf" in url.lower():
                continue  # skip PDF links; use download_binary for those
            print(f"  [Jina] fetching {url}")
            content = self.read_url(url)
            if content and len(content) > 300:
                return url, content
            time.sleep(0.5)
        return "", ""
