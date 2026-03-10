# OpenClawDataPipeline — User Simulator Agent

基于 LLM 的 Windows 模拟环境生成管线。给定用户画像描述文本，自动生成完整的 Windows 文件系统（目录 + 真实文档）、`env_config.json` 环境配置，以及 `user_queries.json` 用户查询集。

---

## 项目结构

```
user_simulator_agent/
├── config/
│   ├── baseline.yaml          # 中央配置（API 密钥、路径、模型、并发参数）
│   └── config_loader.py       # YAML 配置加载 & prompt 路径解析
│
├── shared/
│   └── llm_caller.py          # OpenAI 兼容的 LLM 调用客户端（带重试）
│
├── prompts/                   # 所有 Prompt 模板（Markdown 文件）
│   ├── profile_analyzer_prompt.md
│   ├── profile_generation_prompt.md
│   ├── computer_spec_dirs.md
│   ├── computer_spec_file_counts.md
│   ├── computer_spec_pdf.md / html.md / excel_csv.md / ...
│   ├── computer_spec_envconfig.md
│   └── user_agent_builder_prompt.md
│
├── ControlCenter/             # 批量编排入口
│   ├── generate_user_profile.py   # LLM 批量生成用户画像
│   └── batch_generate.py          # 遍历画像文件，逐一调用管线
│
├── WorkingSpace/              # 单次管线执行目录
│   ├── main.py                # 4-Step 管线主入口
│   ├── user_profile.txt       # 默认输入：自由文本用户画像
│   ├── requirements.txt
│   ├── agents/                # 各步骤 Agent 实现
│   │   ├── profile_analyzer.py
│   │   ├── computer_spec_designer.py
│   │   ├── file_processor.py
│   │   ├── user_agent_builder.py
│   │   └── user_query_generate.py
│   ├── utils/
│   │   ├── llm_client.py      # 双后端 LLM 封装（OpenAI + Anthropic）
│   │   └── web_tools.py       # Serper 搜索 / 文件下载 / Jina Reader
│   └── output/                # 默认输出目录
│
└── Outputs/                   # 批量输出
    ├── profiles/              # 生成的用户画像 JSON
    └── environments/          # 生成的模拟环境
```

---

## 快速开始

```bash
# 安装依赖
pip install -r user_simulator_agent/WorkingSpace/requirements.txt

# 单次生成（从 user_profile.txt）
cd user_simulator_agent/WorkingSpace
python main.py

# 批量：先生成用户画像
python ../ControlCenter/generate_user_profile.py --output-dir ../Outputs/profiles --count 3

# 批量：从画像批量生成环境
python ../ControlCenter/batch_generate.py --profiles-dir ../Outputs/profiles --envs-dir ../Outputs/environments --skip-existing
```

---

## 配置

所有配置集中在 `config/baseline.yaml`，可通过环境变量覆盖：

| 环境变量 | 用途 | 默认值 |
|---------|------|--------|
| `LLM_BACKEND` | LLM 后端：`"openai"` 或 `"anthropic"` | `"openai"` |
| `LLM_API_KEY` | OpenAI 兼容 API Key | baseline.yaml 内置 |
| `LLM_BASE_URL` | OpenAI 兼容端点 | `https://api.gptplus5.com/v1` |
| `LLM_MODEL` | 模型名称 | baseline.yaml 内置 |
| `ANTHROPIC_API_KEY` | Anthropic 密钥（backend=anthropic 时需要） | — |
| `SERPER_KEY` | Google Serper 搜索 API Key | baseline.yaml 内置 |
| `JINA_KEY` | Jina Reader 网页提取 API Key | baseline.yaml 内置 |
| `MAX_WORKERS` | 文件下载/生成并发线程数 | `8` |
| `MAX_LLM_CALLS` | LLM 并发请求上限 | `4` |
| `MAX_SEARCHES` | Serper 并发搜索上限 | `5` |

---

## 管线详细流程

### main.py — 4-Step 管线

```
user_profile.txt / profile.json
        │
        ▼
┌─────────────────────────────┐
│  Step 1: ProfileAnalyzer    │
│  解析用户画像 → 结构化 JSON   │
└──────────────┬──────────────┘
               │ profile dict
               ▼
┌─────────────────────────────┐
│  Step 2: ComputerSpecDesigner│
│  设计目录树 + 文件清单        │
└──────────────┬──────────────┘
               │ spec dict
               ▼
┌─────────────────────────────┐
│  Step 3: FileProcessor      │
│  创建目录 & 下载/生成文件     │
└──────────────┬──────────────┘
               │ created files list
               ▼
┌─────────────────────────────┐
│  Step 4: UserQueryGenerator  │
│  生成 user_queries.json 查询集│
└─────────────────────────────┘
               │
               ▼
        output/
        ├── computer_profile/
        │   ├── env_config.json
        │   ├── README.md
        │   ├── C/ D/ ...
        │   └── (所有生成的文件)
        ├── computer_profile.zip
        └── user_queries.json
```

#### Step 1: ProfileAnalyzer

| | 说明 |
|---|---|
| **输入** | 自由文本用户画像（中/英文），可以是 `.txt` 纯文本或 `.json` 文件 |
| **处理** | 加载 `profile_analyzer_prompt.md`，调用 LLM 将非结构化文本解析为结构化 JSON |
| **输出** | `profile` 字典，包含以下字段 |

```json
{
  "name": "陈志远",
  "gender": "男",
  "age": 32,
  "role": "投资分析师",
  "industry": "金融",
  "company": "XX 证券研究所",
  "department": "研究部",
  "os": "Windows 10 专业版",
  "username": "chenzhiyuan",
  "hostname": "CHEN-RESEARCH",
  "drive_layout": ["C", "D"],
  "core_tools": ["Excel", "Wind", "Python"],
  "file_types": ["PDF", "XLSX", "DOCX"],
  "work_focus": ["行业研究", "财务建模"],
  "file_organization_style": "按项目和日期组织",
  "personality": ["严谨", "高效"],
  "domain_keywords": ["新能源", "估值模型"],
  "task_description": "完成某公司季度财报分析报告（200字内）",
  "task_context": "总监要求本周五前提交（100字内）"
}
```

#### Step 2: ComputerSpecDesigner

| | 说明 |
|---|---|
| **输入** | Step 1 产出的 `profile` 字典 |
| **处理** | 分 5 个子步骤（部分并行），多次调用 LLM |
| **输出** | `spec` 字典，包含 `directories`、`files`、`env_config` |

**子步骤：**

1. **目录设计** — LLM 生成 35+ 个 Windows 层级目录（`computer_spec_dirs.md`）
2. **文件数量估算** — LLM 按类别返回文件数（`computer_spec_file_counts.md`）
3. **分类别文件设计**（3 线程并行，共 9 个类别）：
   - 可下载类：PDF / HTML / Excel+CSV / 图片 / 视频 / 音频
   - 生成类：Word / Excel / Markdown
4. **文件去重** — 按路径去重，保持类别顺序
5. **env_config 设计** — LLM 生成环境元数据（`computer_spec_envconfig.md`）

输出 `files` 列表中每个文件的结构：

```json
{
  "path": "D/Research/Companies/Tesla_2023.pdf",
  "type": "downloadable",       // 或 "generated"
  "sub_type": "pdf",            // pdf/html/xlsx/docx/md/py/json/csv/...
  "description": "特斯拉 2023 年年报",
  "search_query": "Tesla annual report 2023 filetype:pdf",
  "content_prompt": "..."       // generated 类型时使用
}
```

#### Step 3: FileProcessor

| | 说明 |
|---|---|
| **输入** | Step 2 的 `spec` + Step 1 的 `profile` |
| **处理** | 创建所有目录，8 线程并行下载/生成文件 |
| **输出** | 成功创建的文件路径列表 |

**处理逻辑按文件类型分流：**

| 文件类型 | 处理流程 |
|---------|---------|
| **媒体文件**（图片/视频/音频） | 仅下载，不回退到 LLM 生成。最多 6 次搜索尝试 |
| **可下载文件**（PDF/HTML/Excel/CSV） | Serper 搜索 → 二进制下载（含 magic-byte 校验）→ Jina Reader 回退 → LLM 生成回退 |
| **生成文件**（DOCX/XLSX/MD/PY/JSON/TXT） | LLM 生成内容 → 对应格式库写入（openpyxl / python-docx 等） |

**并发控制：**
- 文件处理线程：`MAX_WORKERS`（默认 8）
- LLM 并发信号量：`MAX_LLM_CALLS`（默认 4）
- 搜索并发信号量：`MAX_SEARCHES`（默认 5）

**下载验证：**
- PDF 文件校验 `%PDF` magic bytes
- 媒体文件校验最小大小（1KB）
- Content-Type 白名单校验
- 视频超时 120s，音频 60s，其他 30-60s

#### Step 4: UserQueryGenerator

| | 说明 |
|---|---|
| **输入** | Step 1 的 `profile` + Step 2 的 `spec`（文件类型分布 + 文件路径示例） |
| **处理** | LLM 生成 5 条与用户画像和文件环境相关的自然语言查询 |
| **输出** | `user_queries.json`，保存到输出目录 |

生成的 `user_queries.json` 包含：

```json
{
  "queries": ["查询1", "查询2", "..."],
  "profile": { ... },
  "spec_summary": {
    "directories_count": 42,
    "files_count": 65,
    "file_types": {"pdf": 10, "xlsx": 8, ...}
  }
}
```

#### 管线最终输出

```
output/
├── computer_profile/          # 模拟 Windows 文件系统
│   ├── env_config.json        # 环境元数据（用户信息、系统配置、工具列表）
│   ├── README.md              # 文件清单和目录结构说明
│   ├── C/Users/{username}/    # C 盘用户目录
│   └── D/...                  # D 盘工作目录
├── computer_profile.zip       # 整个环境的 ZIP 打包
└── user_queries.json          # 用户查询集（JSON）
```

管线返回值：

```python
{
  "profile_dir_name": "陈志远_投资分析师",
  "profile": { ... },          # Step 1 结构化画像
  "created_files": [ ... ],    # Step 3 创建的文件列表
  "output_dir": "/path/to/output"
}
```

---

## batch_generate.py 运行逻辑

```
Outputs/profiles/*.json          # 输入：用户画像 JSON 文件
        │
        ▼
┌───────────────────────────┐
│  1. 初始化 Tee 日志        │    stdout/stderr 同时输出到终端和 Log/{HHMMSS}.log
└──────────┬────────────────┘
           │
           ▼
┌───────────────────────────┐
│  2. 扫描 profiles 目录     │    glob 匹配 pattern（默认 *.json）
└──────────┬────────────────┘
           │ ThreadPoolExecutor 并行（max_concurrency，默认 3）
           │ 每个 task 日志自动加 [profile名] 前缀
           ▼
┌───────────────────────────┐
│  3. 提取画像信息           │    读取 JSON → 提取 姓名 + 职业
│     生成目录名             │    → "{姓名}_{职业}" 作为子目录名
└──────────┬────────────────┘
           │
           ▼
┌───────────────────────────┐
│  4. 跳过检查               │    若 --skip-existing 且目标目录已存在 → 跳过
└──────────┬────────────────┘
           │
           ▼
┌───────────────────────────┐
│  5. 调用 run_pipeline()    │    直接导入 main.py 的 run_pipeline()
│     传入 profile_path,     │    执行完整 4-Step 管线
│     output_dir,            │
│     profile_dir_name       │
└──────────┬────────────────┘
           │
           ▼
┌───────────────────────────┐
│  6. 统计结果               │    记录 成功/失败/跳过 数量
│     返回退出码             │    全部成功 → 0，有失败 → 1
└───────────────────────────┘
```

**输入格式**（generate_user_profile.py 生成的 JSON）：

```json
{
  "基本信息": {
    "姓名": "林辰",
    "性别": "男",
    "年龄": 26,
    "职业": "AI算法工程师",
    "家庭情况": "未婚",
    ...
  },
  "生活喜好": ["健身", "摄影"],
  "学习工作喜好": ["深度学习", "开源社区"],
  "常用电脑工具": "VS Code, PyCharm, Docker...",
  "常用网站": "GitHub, ArXiv, Stack Overflow...",
  "生活类电脑操作Query": ["...", "..."],
  "学习类电脑操作Query": ["...", "..."]
}
```

**输出结构**（每个画像一个子目录）：

```
Outputs/environments/
├── 林辰_AI工程师/
│   ├── 林辰_AI工程师/          # 模拟文件系统
│   │   ├── env_config.json
│   │   ├── README.md
│   │   ├── C/ D/ ...
│   ├── 林辰_AI工程师.zip
│   └── user_queries.json
├── 王芳_产品经理/
│   └── ...
└── ...
```

---

## generate_user_profile.py — 画像生成

```
LLM 调用（profile_generation_prompt.md）
        │
        ▼
  生成 N 个多样化用户画像（默认 3 个）
        │
        ▼
  保存为 JSON 文件
  Outputs/profiles/user_profile_{idx}_{职业}_{timestamp}.json
```

通过 `--count` 参数控制生成数量，`--output-dir` 指定输出目录。

---

## 工具模块

### LLMClient (`utils/llm_client.py`)

双后端 LLM 封装，支持 OpenAI 兼容 API 和 Anthropic 原生 API。

| 方法 | 说明 |
|------|------|
| `chat(messages, ...)` | 底层对话接口，路由到对应后端 |
| `generate(prompt, system, ...)` | 便捷接口，自动构建 messages |
| `generate_json(prompt, system, ...)` | 生成 JSON 并解析，带正则回退 |

重试策略：最多 5 次，间隔 3s。

### WebTools (`utils/web_tools.py`)

| 方法 | 说明 |
|------|------|
| `search(query)` | Serper API 搜索，返回标题/链接/摘要 |
| `search_for_pdf(query)` | PDF 专用搜索，优先可信域名，过滤 JS 重站点 |
| `search_for_filetype(query, exts)` | 按文件类型搜索 |
| `download_binary(url, path)` | 流式下载 + Content-Type/magic-byte 校验 |
| `download_html(url)` | 下载网页 HTML |
| `read_url(url)` | Jina Reader 提取网页 → Markdown（上限 25k 字符） |
| `search_and_fetch(query)` | 搜索 + Jina 读取一站式接口 |

### ConfigLoader (`config/config_loader.py`)

- `load_config()` → 加载并缓存 `baseline.yaml`
- `get_prompt(path)` → 读取 prompt 模板文件内容

### llm_caller (`shared/llm_caller.py`)

全局单例 OpenAI 客户端，`chat_with_retry()` 提供带重试的 LLM 调用。

---

## 设计原则

1. **显性错误处理** — 异常直接报错并中断，不降级或抑制
2. **并行处理** — Step 2 分类别设计、Step 3 文件处理均使用 ThreadPoolExecutor
3. **信号量限流** — LLM 并发（4）和搜索并发（5）通过信号量控制
4. **回退链** — 可下载文件：搜索下载 → Jina Reader → LLM 生成
5. **媒体严格下载** — 图片/视频/音频仅下载，不回退到 LLM 生成
6. **Magic-Byte 校验** — PDF 文件校验 `%PDF` 头部
7. **配置驱动** — 所有路径、密钥、Prompt 集中在 `baseline.yaml`
8. **代码复用优先** — 优先复用项目内已有代码，减少新增
