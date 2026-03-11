# -*- coding: utf-8 -*-
"""
测试 FileProcessor 各下载方法。

策略：
  - 绕过 Serper 搜索，直接把已知 URL 注入到 _search_for_pdf / _search_for_filetype / _search。
  - 禁用所有 fallback（_jina_fallback / _llm_fallback / _gen_*），防止 LLM=None 崩溃。
  - 每种方法准备 3 个候选 URL，有 1 个通过即视为 PASS。

Run:
    conda activate datapipe
    python user_simulator_agent/tests/test_file_processor_dl.py
"""

import sys
import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent      # user_simulator_agent/
_WS   = _ROOT / "WorkingSpace"
for _p in (str(_WS), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config.config_loader import load_config
from utils.web_tools import WebTools
from agents.file_processor import FileProcessor

# ── 加载配置 & 初始化 WebTools ───────────────────────────────────────────────
cfg = load_config()
web_cfg = cfg["web_tools_config"]
web = WebTools(
    serper_key=web_cfg.get("SERPER_KEY", ""),
    jina_key=web_cfg.get("JINA_KEY", ""),
)

# ── 测试用 URL（各 3 条，有 1 条可下载即可）───────────────────────────────────
PDF_URLS = [
    "https://arxiv.org/pdf/1706.03762",                          # Attention is All You Need
    "https://www.irs.gov/pub/irs-pdf/f1040.pdf",                 # IRS 表格
    "https://www.w3.org/WAI/WCAG21/WCAG21.pdf",                  # W3C 规范
]

XLSX_URLS = [
    "https://file-examples.com/wp-content/storage/2017/02/file_example_XLSX_10.xlsx",
    "https://www.learningcontainer.com/wp-content/uploads/2020/08/sample-xlsx-file.xlsx",
    "https://github.com/SheetJS/test_files/raw/master/xlsx/test.xlsx",
]

CSV_URLS = [
    "https://raw.githubusercontent.com/plotly/datasets/master/iris.csv",
    "https://raw.githubusercontent.com/datasets/gdp/master/data/gdp.csv",
    "https://people.sc.fsu.edu/~jburkardt/data/csv/addresses.csv",
]

HTML_URLS = [
    "https://example.com",
    "https://httpbin.org/html",
    "https://www.python.org",
]

GENERIC_URLS = [
    "https://raw.githubusercontent.com/plotly/datasets/master/iris.csv",
    "https://httpbin.org/bytes/1024",
    "https://www.rfc-editor.org/rfc/rfc2616.txt",
]

# ── 测试框架 ─────────────────────────────────────────────────────────────────
_results: dict[str, tuple[bool, str | None, int]] = {}

def run_test(name: str, fn, url_count: int):
    print(f"\n{'─'*50}")
    print(f"[TEST] {name}")
    ok, err = False, None
    try:
        ok = bool(fn())
    except Exception as e:
        err = str(e)
    _results[name] = (ok, err, url_count)
    status = "PASS" if ok else "FAIL"
    suffix = f"  -- {err}" if err else ""
    print(f"[{status}] {name}{suffix}")


# ── 主测试逻辑 ────────────────────────────────────────────────────────────────
_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
tmpdir = Path(__file__).parent / "dl_output" / _ts
tmpdir.mkdir(parents=True)
tmpdir = str(tmpdir)

fp = FileProcessor(llm=None, web=web, output_dir=tmpdir)

# 禁用所有 fallback / 生成方法，防止 LLM=None 崩溃
fp._jina_fallback = lambda *_, **__: False
fp._llm_fallback  = lambda *_, **__: False
fp._gen_xlsx      = lambda *_, **__: False
fp._gen_csv       = lambda *_, **__: False
fp._gen_text      = lambda *_, **__: False

fspec   = {"description": "test file", "search_query": "test"}
profile = {"role": "tester", "company": "test-corp"}

# ── _dl_pdf ───────────────────────────────────────────────────────────────
fp._search_for_pdf = lambda *_, **__: PDF_URLS

def _test_pdf():
    p = Path(tmpdir) / "dl_test.pdf"
    return fp._dl_pdf(fspec, p, profile)

run_test("_dl_pdf", _test_pdf, len(PDF_URLS))

# ── _dl_excel ─────────────────────────────────────────────────────────────
fp._search_for_filetype = lambda *_, **__: XLSX_URLS

def _test_excel():
    p = Path(tmpdir) / "dl_test.xlsx"
    return fp._dl_excel(fspec, p, profile)

run_test("_dl_excel", _test_excel, len(XLSX_URLS))

# ── _dl_csv_web ───────────────────────────────────────────────────────────
fp._search_for_filetype = lambda *_, **__: CSV_URLS

def _test_csv_web():
    p = Path(tmpdir) / "dl_test.csv"
    return fp._dl_csv_web(fspec, p, profile)

run_test("_dl_csv_web", _test_csv_web, len(CSV_URLS))

# ── _dl_html ──────────────────────────────────────────────────────────────
fp._search = lambda *_, **__: [{"link": u} for u in HTML_URLS]

def _test_html():
    p = Path(tmpdir) / "dl_test.html"
    return fp._dl_html(fspec, p, profile)

run_test("_dl_html", _test_html, len(HTML_URLS))

# ── _dl_generic ───────────────────────────────────────────────────────────
fp._search = lambda *_, **__: [{"link": u} for u in GENERIC_URLS]

def _test_generic():
    p = Path(tmpdir) / "dl_test_generic.bin"
    return fp._dl_generic(fspec, p, profile)

run_test("_dl_generic", _test_generic, len(GENERIC_URLS))

# ── 汇总 ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 50)
passed = sum(1 for ok, *_ in _results.values() if ok)
print(f"结果: {passed}/{len(_results)} 通过\n")
for name, (ok, err, total) in _results.items():
    ratio = f"{'1' if ok else '0'}/{total}"
    detail = f"  ({err})" if err else ""
    print(f"  {ratio} {name}{detail}")
print()

sys.exit(0 if passed == len(_results) else 1)
