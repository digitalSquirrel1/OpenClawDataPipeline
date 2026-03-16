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

请为该用户设计 **{file_count}个** 可从公网下载的真实PDF文件。

每个文件的 search_query 必须精准，能搜到真实可下载的PDF。

输出 JSON（只有files数组，不要其他键）：
{{
  "files": [
    {{
      "path": "D/研究资料/车企财报/比亚迪/2023/比亚迪2023年度报告.pdf",
      "type": "downloadable",
      "sub_type": "pdf",
      "description": "比亚迪股份有限公司2023年度报告（H股，港交所披露），包含公司财务状况、经营成果、现金流量表、股东权益变动表等完整财务信息，以及管理层讨论与分析部分，详细阐述了新能源汽车业务的发展战略和市场前景展望。",
      "search_query": "比亚迪 2023年度报告 site:hkexnews.hk filetype:pdf"
    }},
    ...（共{file_count}个）
  ]
}}
"""

PROMPT_HTML = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **{file_count}个** 可从公网下载保存的HTML网页文件。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/网页存档/财经新闻/比亚迪2023年销量创历史记录.html",
      "type": "downloadable",
      "sub_type": "html",
      "description": "比亚迪2023年全年销量创历史记录相关新闻页面，报道了比亚迪新能源汽车销量突破300万辆大关，创下中国汽车行业新纪录，详细分析了市场份额增长、产品线扩张以及国际化战略的成功实施情况。",
      "search_query": "比亚迪 2023年销量 302万辆 历史记录"
    }},
    ...（共{file_count}个）
  ]
}}
"""

PROMPT_EXCEL_CSV = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **{file_count}个** 可从公网下载的Excel/CSV数据文件。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/数据分析/Wind导出/乘联会2023年月度销量.csv",
      "type": "downloadable",
      "sub_type": "csv",
      "description": "乘联会2023年新能源乘用车月度零售销量数据统计表，包含各月份销量数据、环比同比变化、细分市场占比分析，以及新能源汽车市场渗透率趋势图表，帮助分析行业发展动态和竞争格局。",
      "search_query": "乘联会 新能源汽车 月度销量 2023 filetype:csv"
    }},
    ...（共{file_count}个）
  ]
}}
"""

PROMPT_DOCX = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **{file_count}个** 由用户自己创作的Word/文本文档文件（type=generated）。
format 可以是 docx 或 txt。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "C/Users/{username}/Documents/工作笔记/比亚迪2023财报精读笔记.docx",
      "type": "generated",
      "format": "docx",
      "description": "比亚迪2023年报精读笔记，含财务指标分析和投资要点，详细剖析了公司营收结构、利润增长来源、新能源汽车销量贡献度、供应链优化成效，以及未来产能扩张计划和潜在投资风险评估。",
      "content_prompt": "生成一篇比亚迪2023年报精读笔记，包含：营收增长分析、毛利率变化、新车型销量贡献、海外市场拓展进展、主要投资风险。约1500字，专业券商研究风格。"
    }},
    ...（共{file_count}个）
  ]
}}
"""

PROMPT_XLSX = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **{file_count}个** 由用户整理的Excel/CSV数据表文件（type=generated）。
format 可以是 xlsx 或 csv。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/数据分析/Wind导出/新能源汽车月度销量2024.xlsx",
      "type": "generated",
      "format": "xlsx",
      "description": "2024年1-11月中国新能源乘用车各品牌月度销量数据汇总表，包含比亚迪、特斯拉中国、理想、问界、小鹏、蔚来等主要品牌销量数据、月度环比增长率、年度累计销量对比，以及市场份额变化趋势分析。",
      "content_prompt": "生成2024年1-11月中国新能源乘用车月度销量数据，列：月份,品牌,销量(辆),同比增速(%)。品牌包括：比亚迪,特斯拉中国,理想,问界,小鹏,蔚来,零跑,哪吒,埃安。数据要合理真实。"
    }},
    ...（共{file_count}个）
  ]
}}
"""

PROMPT_MD = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **{file_count}个** 正在撰写的深度报告草稿和分析笔记文件（type=generated，format=md）。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/工作文档/深度报告/2024/Q1/新能源乘用车2024Q1行业深度报告草稿.md",
      "type": "generated",
      "format": "md",
      "description": "2024年Q1新能源乘用车行业深度报告（在研草稿，约3000字），全面分析了第一季度市场表现、各品牌销量数据、竞争格局演变、新能源补贴政策影响，以及未来行业发展趋势和投资机会评估。",
      "content_prompt": "生成一篇2024年Q1新能源乘用车行业深度报告草稿，包含：市场概述、各品牌销量分析、竞争格局变化、政策影响、投资建议。约3000字，专业券商研究报告风格。"
    }},
    ...（共{file_count}个）
  ]
}}
"""

PROMPT_IMAGE = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **{file_count}个** 可从公网下载的真实图片文件。
sub_type 可以是 jpg, png, jpeg 等。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/资源文件/产品图片/比亚迪/比亚迪汉EV官方产品图.jpg",
      "type": "downloadable",
      "sub_type": "jpg",
      "description": "比亚迪汉EV新能源汽车官方产品图高清展示，包含车辆外观、内饰设计、配置参数、技术亮点等全方位视觉呈现，帮助用户了解比亚迪旗舰轿车的产品特色和市场定位。",
      "search_query": "比亚迪汉EV 官方产品图 site:byd.com"
    }},
    ...（共{file_count}个）
  ]
}}
"""

PROMPT_VIDEO = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **{file_count}个** 可从公网下载的真实视频文件。
sub_type 可以是 mp4, mkv, avi 等。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/资源文件/视频资源/行业会议/2024新能源汽车论坛主题演讲.mp4",
      "type": "downloadable",
      "sub_type": "mp4",
      "description": "2024新能源汽车行业论坛中关于市场趋势的主题演讲视频，演讲嘉宾详细分析了新能源汽车市场发展现状、未来技术趋势、政策环境变化，以及产业链上下游的投资机会和挑战。",
      "search_query": "2024新能源汽车论坛 市场趋势 演讲视频"
    }},
    ...（共{file_count}个）
  ]
}}
"""

PROMPT_AUDIO = """
用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 **{file_count}个** 可从公网下载的真实音频文件。
sub_type 可以是 mp3, wav, m4a 等。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/资源文件/音频资源/播客/新能源行业周报第42期.mp3",
      "type": "downloadable",
      "sub_type": "mp3",
      "description": "新能源汽车行业周报播客第42期：市场动态分析，主持人邀请行业专家深度解读近期新能源汽车销量数据、市场份额变化、新车型发布情况，以及政策利好对行业发展的推动作用。",
      "search_query": "新能源汽车行业周报 播客 第42期"
    }},
    ...（共{file_count}个）
  ]
}}
"""

PROMPT_FILE_COUNTS = """
根据以下用户画像，分析用户的职业特征、工作习惯和数据需求，为每个文件类别确定合适的文件数量（5-30个之间）。

--- 用户画像 ---
{profile_json}
--- end ---

请分析：
- 用户的职位级别（初级/中级/高级/总监等）
- 工作内容复杂度
- 公司规模
- 核心工具数量
- 行业特点

为以下9个文件类别确定文件数量：
1. PDF文件(可下载) - 行业报告、财报、政策文件等
2. HTML网页(可下载) - 新闻、公司页面、数据统计页等  
3. Excel/CSV(可下载) - 公开数据文件
4. 图片文件(可下载) - 产品图、市场图表等
5. 视频文件(可下载) - 发布会、演讲视频等
6. 音频文件(可下载) - 播客、会议录音等
7. Word/文本(生成) - 笔记、报告、会议纪要等
8. Excel/CSV(生成) - 数据分析表、模型等
9. Markdown报告(生成) - 深度分析报告草稿

输出 JSON：
{{
  "file_counts": {{
    "PDF文件(可下载)": xx,
    "HTML网页(可下载)": xx,
    "Excel/CSV(可下载)": xx,
    "图片文件(可下载)": xx,
    "视频文件(可下载)": xx,
    "音频文件(可下载)": xx,
    "Word/文本(生成)": xx,
    "Excel/CSV(生成)": xx,
    "Markdown报告(生成)": xx
  }}
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

        # ── Step 2: file counts ─────────────────────────────────────────────
        print("[Step 3] 确定各类文件数量...")
        counts_spec = self.llm.generate_json(
            PROMPT_FILE_COUNTS.format(profile_json=profile_json),
            max_tokens=2000
        )
        file_counts = counts_spec.get("file_counts", {})
        print(f"  -> 文件数量配置: {file_counts}")

        # ── Step 3: files per category（并行调用，3个worker避免API限速）────────
        all_files: list[dict] = []
        results_lock = threading.Lock()
        cat_results: dict[str, list] = {}

        categories = [
            ("PDF文件(可下载)",     PROMPT_PDF,       3000, file_counts.get("PDF文件(可下载)", 15)),
            ("HTML网页(可下载)",    PROMPT_HTML,      2500, file_counts.get("HTML网页(可下载)", 10)),
            ("Excel/CSV(可下载)",   PROMPT_EXCEL_CSV, 2000, file_counts.get("Excel/CSV(可下载)", 6)),
            ("图片文件(可下载)",     PROMPT_IMAGE,     2500, file_counts.get("图片文件(可下载)", 12)),
            ("视频文件(可下载)",     PROMPT_VIDEO,     2500, file_counts.get("视频文件(可下载)", 6)),
            ("音频文件(可下载)",     PROMPT_AUDIO,     2500, file_counts.get("音频文件(可下载)", 5)),
            ("Word/文本(生成)",     PROMPT_DOCX,      3000, file_counts.get("Word/文本(生成)", 20)),
            ("Excel/CSV(生成)",     PROMPT_XLSX,      2500, file_counts.get("Excel/CSV(生成)", 15)),
            ("Markdown报告(生成)",  PROMPT_MD,        2500, file_counts.get("Markdown报告(生成)", 8)),
        ]

        print(f"[Step 4] 并行设计 {len(categories)} 个文件类别...")

        def design_category(cat_name, tmpl, max_tok, file_count):
            try:
                prompt = tmpl.format(
                    profile_json=profile_json,
                    dirs_json=dirs_json,
                    username=username,
                    file_count=file_count,
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
                executor.submit(design_category, cat_name, tmpl, max_tok, file_count): cat_name
                for cat_name, tmpl, max_tok, file_count in categories
            }
            # 按类别顺序合并（保证路径去重稳定）
            ordered_results = {}
            for future in concurrent.futures.as_completed(futures):
                cat_name, files = future.result()
                ordered_results[cat_name] = files

        # 按原始顺序合并，去重
        seen_paths: set[str] = set()
        for cat_name, _, _, _ in categories:
            for f in ordered_results.get(cat_name, []):
                path = f.get("path", "")
                if path and path not in seen_paths:
                    seen_paths.add(path)
                    all_files.append(f)

        print(f"[Step 4] 文件规划完成，共 {len(all_files)} 个文件，{len(directories)} 个目录")

        # ── Step 4: env_config ───────────────────────────────────────────────
        print("[Step 5] 设计电脑环境配置（env_config）...")
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
