# -*- coding: utf-8 -*-
"""
Step 2 — Computer Spec Designer
设计完整的 Windows 电脑环境：深层目录结构 + 丰富文件列表（目标 55-70 个文件）。

文件类型说明：
  type = "downloadable"  → 网络上可公开获取
    sub_type: "pdf"      → 直接下载 .pdf 二进制
               "html"    → 下载并保存为 .html 页面
               "excel"   → 搜索并下载 .xlsx/.xls
               "csv"     → 搜索并下载 .csv
  type = "generated"    → 由 LLM 生成内容
    format: csv / xlsx / docx / txt / md / pptx / py / json

设计策略：多次分类调用，每次仅生成一个类别的文件列表，避免单次输出被截断。
"""
import json
import threading
import concurrent.futures
from utils.llm_client import LLMClient

SYSTEM = "你是一名专业的IT环境模拟专家。你的任务是设计一个高度真实的Windows用户电脑环境。只输出合法JSON，不要有任何注释或多余文字。"

PROMPT_DIRS = """
根据以下用户画像，设计一个真实的 Windows 10 电脑目录结构。

--- 用户画像 ---
{profile_json}
--- end ---

请生成至少 35 个目录，按工作习惯深层分级，例如：
  D/研究资料/车企财报/比亚迪/2022/
  D/研究资料/车企财报/比亚迪/2023/
  D/工作文档/深度报告/2024/Q1/
  C/Users/{username}/Desktop/
  C/Users/{username}/Downloads/
  ...

输出 JSON：
{{
  "directories": [
    "D/研究资料/车企财报/比亚迪/2022",
    "D/研究资料/车企财报/比亚迪/2023",
    ...（至少35个）
  ]
}}
"""

PROMPT_PDF = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **20个** 可从公网下载的真实PDF文件。
包含：上市车企年报（比亚迪/理想/蔚来/小鹏/广汽/上汽/吉利/长城/长安，多年份）、
行业政策文件、券商研报、招股书。

每个文件的 search_query 必须精准，能搜到真实可下载的PDF。

输出 JSON（只有files数组，不要其他键）：
{{
  "files": [
    {{
      "path": "D/研究资料/车企财报/比亚迪/2023/比亚迪2023年度报告.pdf",
      "type": "downloadable",
      "sub_type": "pdf",
      "description": "比亚迪股份有限公司2023年度报告（H股，港交所披露）",
      "search_query": "比亚迪 2023年度报告 site:hkexnews.hk filetype:pdf"
    }},
    ...（共20个）
  ]
}}
"""

PROMPT_HTML = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **10个** 可从公网下载保存的HTML网页文件。
包含：重大行业新闻页、政策通知原文页、公司投资者关系页、行业数据统计页。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/网页存档/财经新闻/比亚迪2023年销量创历史记录.html",
      "type": "downloadable",
      "sub_type": "html",
      "description": "比亚迪2023年全年销量创历史新高相关新闻页面",
      "search_query": "比亚迪 2023年销量 302万辆 历史记录"
    }},
    ...（共10个）
  ]
}}
"""

PROMPT_EXCEL_CSV = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **6个** 可从公网下载的Excel/CSV数据文件。
包含：CAAM或乘联会月度销量数据、政府能源局统计数据、上交所/深交所数据。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/数据分析/Wind导出/乘联会2023年月度销量.csv",
      "type": "downloadable",
      "sub_type": "csv",
      "description": "乘联会2023年新能源乘用车月度零售销量数据",
      "search_query": "乘联会 新能源汽车 月度销量 2023 filetype:csv"
    }},
    ...（共6个）
  ]
}}
"""

PROMPT_DOCX = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **12个** 由用户自己创作的Word/文本文档文件（type=generated）。
包含：财报分析笔记、会议纪要、调研记录、行业观察周报、内部汇报材料、联系人整理等。
format 可以是 docx 或 txt。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "C/Users/{username}/Documents/工作笔记/比亚迪2023财报精读笔记.docx",
      "type": "generated",
      "format": "docx",
      "description": "比亚迪2023年报精读笔记，含财务指标分析和投资要点",
      "content_prompt": "生成一篇比亚迪2023年报精读笔记，包含：营收增长分析、毛利率变化、新车型销量贡献、海外市场拓展进展、主要投资风险。约1500字，专业券商研究风格。"
    }},
    ...（共12个）
  ]
}}
"""

PROMPT_XLSX = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **10个** 由用户整理的Excel/CSV数据表文件（type=generated）。
包含：多车企财务指标对比、销量数据汇总、市场份额计算、DCF估值模型、Wind导出整理数据。
format 可以是 xlsx 或 csv。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/数据分析/Wind导出/新能源汽车月度销量2024.xlsx",
      "type": "generated",
      "format": "xlsx",
      "description": "2024年1-11月中国新能源乘用车各品牌月度销量数据",
      "content_prompt": "生成2024年1-11月中国新能源乘用车月度销量数据，列：月份,品牌,销量(辆),同比增速(%)。品牌包括：比亚迪,特斯拉中国,理想,问界,小鹏,蔚来,零跑,哪吒,埃安。数据要合理真实。"
    }},
    ...（共10个）
  ]
}}
"""

PROMPT_MD = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **8个** 正在撰写的深度报告草稿和分析笔记文件（type=generated，format=md）。
包含：行业深度报告草稿、投资策略报告、季度市场分析、专题研究报告等。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/工作文档/深度报告/2024/Q1/新能源乘用车2024Q1行业深度报告草稿.md",
      "type": "generated",
      "format": "md",
      "description": "2024年Q1新能源乘用车行业深度报告（在研草稿，约3000字）",
      "content_prompt": "生成一篇2024年Q1新能源乘用车行业深度报告草稿，包含：市场概述、各品牌销量分析、竞争格局变化、政策影响、投资建议。约3000字，专业券商研究报告风格。"
    }},
    ...（共8个）
  ]
}}
"""

PROMPT_ENVCONFIG = """
为以下用户生成详细的 Windows 10 电脑环境配置 JSON。

用户信息：
- 姓名：{name}
- 职业：{role}
- 单位：{company}
- 系统用户名：{username}
- 电脑名：{hostname}
- 核心工具：{tools}

请生成如下 JSON 结构（所有字段完整填写，不得省略）：
{{
  "system": {{
    "os": "Windows 10 专业版",
    "os_version": "22H2 (19045.3803)",
    "username": "{username}",
    "display_name": "{name}",
    "hostname": "{hostname}",
    "timezone": "China Standard Time (UTC+8)",
    "language": "zh-CN",
    "install_date": "2022-03-10",
    "last_boot": "2024-11-18 08:47:22",
    "product_key_partial": "XXXXX-XXXXX-XXXXX-XXXXX-X7B3K"
  }},
  "hardware": {{
    "cpu": "Intel Core i7-12700 @ 2.10GHz (12C/20T)",
    "ram_gb": 32,
    "storage": [
      {{"drive": "C:", "label": "系统", "type": "NVMe SSD", "size_gb": 512, "free_gb": 178}},
      {{"drive": "D:", "label": "数据", "type": "SATA HDD", "size_gb": 2000, "free_gb": 1156}},
      {{"drive": "E:", "label": "备份", "type": "SATA HDD", "size_gb": 4000, "free_gb": 3210}}
    ],
    "display": "2560x1440 @60Hz Dell 27英寸 IPS",
    "gpu": "NVIDIA GeForce RTX 3060 12GB",
    "network_adapters": ["Intel Wi-Fi 6 AX201", "Realtek PCIe GbE Family Controller"]
  }},
  "installed_software": [
    至少20个软件，每个包含name/version/install_date/category/publisher字段
  ],
  "browser": {{
    "default": "Google Chrome",
    "version": "120.0.6099.130",
    "bookmarks": [至少20个书签],
    "extensions": ["至少5个插件"],
    "history_summary": "最近访问的网站类别统计"
  }},
  "recent_files": [最近打开的10个文件路径],
  "desktop_shortcuts": [至少12个桌面快捷方式],
  "startup_programs": [开机自启程序，至少8个],
  "scheduled_tasks": [定时任务，至少3个],
  "network": {{
    "hostname": "{hostname}",
    "ip_address": "192.168.1.105",
    "dns": ["114.114.114.114", "8.8.8.8"],
    "wifi_profiles": ["公司内网", "CHEN-home-5G", "手机热点"],
    "proxy": {{"enabled": true, "host": "proxy.securities.com", "port": 8080}}
  }},
  "environment_variables": {{
    "USERPROFILE": "C:\\\\Users\\\\{username}",
    "APPDATA": "C:\\\\Users\\\\{username}\\\\AppData\\\\Roaming",
    "PYTHON_HOME": "C:\\\\Python39",
    "WIND_HOME": "C:\\\\Wind\\\\Wind.NET.Client\\\\WindNET"
  }},
  "registry_notes": "已安装的COM组件、字体等简要说明",
  "windows_features": ["已启用的Windows功能列表，至少5个"]
}}
"""


class ComputerSpecDesigner:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def design(self, profile: dict) -> dict:
        profile_json = json.dumps(profile, ensure_ascii=False, indent=2)
        username = profile.get("username", "user")

        # ── Step 1: directories ──────────────────────────────────────────────
        print("[Step 2] 设计目录结构...")
        dirs_spec = self.llm.generate_json(
            PROMPT_DIRS.format(profile_json=profile_json, username=username),
            max_tokens=3000
        )
        directories = dirs_spec.get("directories", [])
        print(f"  -> {len(directories)} 个目录")
        dirs_json = json.dumps(directories, ensure_ascii=False)

        # ── Step 2: files per category（并行调用，3个worker避免API限速）────────
        all_files: list[dict] = []
        results_lock = threading.Lock()
        cat_results: dict[str, list] = {}

        categories = [
            ("PDF文件(可下载)",     PROMPT_PDF,       3000),
            ("HTML网页(可下载)",    PROMPT_HTML,      2500),
            ("Excel/CSV(可下载)",   PROMPT_EXCEL_CSV, 2000),
            ("Word/文本(生成)",     PROMPT_DOCX,      3000),
            ("Excel/CSV(生成)",     PROMPT_XLSX,      2500),
            ("Markdown报告(生成)",  PROMPT_MD,        2500),
        ]

        print(f"[Step 2] 并行设计 {len(categories)} 个文件类别...")

        def design_category(cat_name, tmpl, max_tok):
            try:
                prompt = tmpl.format(
                    profile_json=profile_json,
                    dirs_json=dirs_json,
                    username=username,
                )
                result = self.llm.generate_json(prompt, max_tokens=max_tok)
                files = result.get("files", [])
                print(f"  -> [{cat_name}] +{len(files)} 个文件")
                return cat_name, files
            except Exception as e:
                print(f"  [!] {cat_name} 设计失败: {e}")
                return cat_name, []

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(design_category, cat_name, tmpl, max_tok): cat_name
                for cat_name, tmpl, max_tok in categories
            }
            # 按类别顺序合并（保证路径去重稳定）
            ordered_results = {}
            for future in concurrent.futures.as_completed(futures):
                cat_name, files = future.result()
                ordered_results[cat_name] = files

        # 按原始顺序合并，去重
        seen_paths: set[str] = set()
        for cat_name, _, _ in categories:
            for f in ordered_results.get(cat_name, []):
                path = f.get("path", "")
                if path and path not in seen_paths:
                    seen_paths.add(path)
                    all_files.append(f)

        print(f"[Step 2] 文件规划完成，共 {len(all_files)} 个文件，{len(directories)} 个目录")

        # ── Step 3: env_config ───────────────────────────────────────────────
        print("[Step 2] 设计电脑环境配置（env_config）...")
        prompt_env = PROMPT_ENVCONFIG.format(
            name=profile.get("name", "用户"),
            role=profile.get("role", ""),
            company=profile.get("company", ""),
            username=username,
            hostname=profile.get("hostname", "PC"),
            tools=", ".join(profile.get("core_tools", [])),
        )
        try:
            env_config = self.llm.generate_json(prompt_env, max_tokens=4096)
        except Exception as e:
            print(f"  [!] env_config 生成失败: {e}")
            env_config = {}

        return {
            "directories": directories,
            "files": all_files,
            "env_config": env_config,
        }
