# OpenClawDataPipeline — User Simulator Agent

基于 LLM 的 Windows 模拟环境生成管线。给定用户画像描述文本，自动生成完整的 Windows 文件系统（目录 + 真实文档）、`env_config.json` 环境配置，以及 `user_queries.json` 用户查询集。

---

## 项目结构

```
user_simulator_agent/
├── config/
│   ├── baseline.yaml          # 脱敏配置模板（需改名为 baseline_using.yaml 使用）
│   └── config_loader.py       # YAML 配置加载 & prompt 路径解析
│
├── shared/
│   ├── llm_caller.py          # OpenAI 兼容的 LLM 调用客户端（带重试）
│   └── topic_search_skills.py # 根据 topic 搜索匹配 skills
│
├── prompts/                   # 所有 Prompt 模板（Markdown 文件）
│
├── ControlCenter/             # 批量编排入口
│   ├── generate_user_profile.py              # Step A: LLM 批量生成用户画像
│   ├── batch_generate.py                     # Step B: 从画像批量生成模拟环境
│   ├── query_gen_with_topic_skill_profile.py # Step C: 基于 topic+skills+profile+env(Optional) 生成 query
│   ├── standard_format.py                    # Step D: 标准化打包输出
│   ├── check_env.py                          # [即将废止] 环境校验辅助（被 batch_generate 内部调用）
│   ├── query_generate.py                     # [即将废止] 旧版 query 生成
│   └── uquery_generate.py                    # [即将废止] 旧版 query 生成
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
    ├── environments/          # 生成的模拟环境
    ├── topics.txt             # topic 列表（query 生成的输入）
    ├── queries_with_skills/   # query 生成中间结果
    ├── standard_output/       # 标准化打包输出（纯 skills 模式）
    └── skill_localize/        # skills 库
        └── skills_library/
```

---

## 快速开始

```bash
# 安装依赖
pip install -r user_simulator_agent/WorkingSpace/requirements.txt
```

完整的批量数据生成流程分 4 步依次执行：

```bash
cd user_simulator_agent

# Step A: 生成用户画像
python ControlCenter/generate_user_profile.py

# Step B: 从画像批量生成模拟环境
python ControlCenter/batch_generate.py

# Step C: 基于 topic + skills + profile 生成 query
python ControlCenter/query_gen_with_topic_skill_profile.py

# Step D: 标准化打包输出
python ControlCenter/standard_format.py
```

> **注意**：ControlCenter 下的所有脚本，运行时的相对路径起点均为 `user_simulator_agent/` 目录。

---

## 配置

1. **`config/baseline.yaml` 是脱敏的配置模板**，仅作为格式示例，其中不包含真实的 API 密钥，无法直接运行，代码也不会读取该文件。需要运行时，请找开发者获取含有密钥的 `baseline_using.yaml` 配置文件并放置在 `config/` 目录下；或者自行补充密钥后，将 `baseline.yaml` 改名为 `baseline_using.yaml`。代码只会读取命名为 `baseline_using.yaml` 的配置文件。

2. **建议将所有配置修改集中在 `baseline_using.yaml` 中完成**，不建议使用环境变量覆盖或在代码中修改默认值。

---

## ControlCenter 脚本详细说明

### Step A: generate_user_profile.py — 批量生成用户画像

基于 LLM 生成多样化的用户画像。随机组合性别、年龄、职业（75+ 预置职业），调用 LLM 生成包含基本信息、生活喜好、工作习惯等的结构化用户画像。

**运行方式：**

```bash
python ControlCenter/generate_user_profile.py
```

> 无命令行参数，所有配置从 `config/baseline_using.yaml` 的 `generate_user_profile_config` 段读取。

**配置项（baseline_using.yaml）：**

| 配置键 | 说明 | 默认值 |
|--------|------|--------|
| `generate_user_profile_config.profiles_dir` | 输出目录 | `Outputs/profiles` |
| `generate_user_profile_config.count` | 生成画像数量 | `3` |
| `generate_user_profile_config.PROFILE_GENERATION_PROMPT` | Prompt 模板路径 | `prompts/profile_generation_prompt.md` |

**输入：**

- 无外部输入文件。程序内部随机生成人物属性（性别、年龄、职业），结合 Prompt 模板调用 LLM。

**输出：**

```
Outputs/profiles/
├── user_profile_1_程序员_20260312_210000.json
├── user_profile_2_教师_20260312_210005.json
└── user_profile_3_律师_20260312_210010.json
```

每个 JSON 文件的结构：

```json
{
  "基本信息": {
    "姓名": "林辰",
    "性别": "男",
    "年龄": 26,
    "职业": "程序员",
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

**退出码：** 成功 `0`，全部失败 `1`。

---

### Step B: batch_generate.py — 从画像批量生成模拟环境

遍历画像目录下的所有 JSON 文件，为每个画像调用 4-Step 管线（`WorkingSpace/main.py`）生成完整的模拟 Windows 环境，并生成文件路径映射表。支持并行处理。

**运行方式：**

```bash
# 使用默认配置
python ControlCenter/batch_generate.py

# 指定目录
python ControlCenter/batch_generate.py \
    --profiles-dir Outputs/profiles \
    --envs-dir Outputs/environments

# 覆盖已有环境（默认跳过）
python ControlCenter/batch_generate.py --overwrite-existing
```

**命令行参数：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--profiles-dir` | 用户画像 JSON 所在目录 | `Outputs/profiles`（可由 baseline_using.yaml 覆盖） |
| `--envs-dir` | 环境输出目录 | `Outputs/environments`（可由 baseline_using.yaml 覆盖） |
| `--overwrite-existing` | 覆盖已生成的环境（默认：已有 zip 则跳过） | `False` |

**输入：**

- `--profiles-dir` 下的 `*.json` 文件（`generate_user_profile.py` 的输出）

**输出：**

```
Outputs/environments/
├── 林辰_程序员/
│   ├── 林辰_程序员/              # 模拟 Windows 文件系统
│   │   ├── env_config.json
│   │   ├── README.md            # 文件清单和目录结构
│   │   ├── C/Users/linchen/     # C 盘
│   │   └── D/...                # D 盘
│   ├── 林辰_程序员.zip           # 整个文件系统的 ZIP 打包
│   ├── user_agent.py            # 用户模拟 Agent 脚本
│   ├── pipeline_meta.json       # 元信息（源画像路径等）
│   ├── MAP_Windows.json         # 文件路径映射（C/→C:\）
│   └── MAP_Linux.json           # 文件路径映射（C/→~/）
├── 王芳_教师/
│   └── ...
└── ...
```

**日志：** 自动在 `Log/{HHMMSS}.log` 记录完整日志（同时输出到终端）。

**跳过逻辑：** 默认情况下，若 `{env_name}.zip` 已存在则跳过该画像。若 zip 不存在但目录存在，视为上次未完成，自动清理后重新生成。

**控制文件数量**：如果需要控制生成文件的数量，需要首先在`computer_spec_file_counts.md`中修改提示词要求设计的最大文件数量；然后在`computer_spec_designer.py`中修改`categories`变量获取的默认值。

**退出码：** 全部成功 `0`，有失败 `1`。

---

### Step C: query_gen_with_topic_skill_profile.py — 生成用户查询

根据 topic 列表、skills 库和用户画像的排列组合，调用 LLM 为每组组合生成多条用户查询（query）。支持两种模式：

- **配置query_gen_with_topic_skill_profile_config指导**
`envs_dir`: 设置为null则生成的query不依赖文件环境；设置为有效路径则依赖文件环境。
`use_match_skills`: True则生成的query会依赖skills，False则不依赖
`PROMPT_TMPL/PROMPT_TMPL_ENV/PROMPT_TMPL_ENV_LINUX`: 提示词后缀是_nointernet的，表示生成的query不依赖网络环境。建议不依赖网络环境的提示词搭配“envs_dir存在”和"use_match_skills=False"使用。

**运行方式：**

```bash
# 纯模式（默认）
python ControlCenter/query_gen_with_topic_skill_profile.py

# 指定参数
python ControlCenter/query_gen_with_topic_skill_profile.py \
    --topics-txt Outputs/topics.txt \
    --profiles-dir Outputs/profiles \
    --output-dir Outputs/queries_with_skills \
    --queries-per-combination 5

# 环境模式（额外读取用户文件结构）
python ControlCenter/query_gen_with_topic_skill_profile.py \
    --envs-dir Outputs/environments

# 跳过已生成的 topic
python ControlCenter/query_gen_with_topic_skill_profile.py --skip-existing
```

**命令行参数：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--topics-txt` | topic 列表文件路径 | `Outputs/topics.txt` |
| `--profiles-dir` | 用户画像目录 | `Outputs/profiles` |
| `--envs-dir` | 用户环境目录（为空则纯模式） | `None` |
| `--output-dir` | 输出目录 | `Outputs/queries_with_skills` |
| `--num-user-per-topic` | 每个 topic 最多使用多少个 profile | `None`（全部） |
| `--queries-per-combination` | 每组 (topic, profile) 生成的 query 数量 | `5` |
| `--skip-existing` | 跳过输出文件中已包含该 topic 的组合 | `True` |

**输入：**

1. **topics.txt** — 每行一个 topic，格式为 `关键词：描述`（取冒号前部分作为 topic）
   ```
   1. 习题求解：针对各学科习题提供解答思路
   2. 编程问题解答：解决各类编程和开发问题
   3. 文档撰写：辅助撰写各类文档和报告
   ```

2. **profiles 目录** — `generate_user_profile.py` 输出的 `*.json` 画像文件

3. **environments 目录**（环境模式可选） — `batch_generate.py` 输出的环境目录，通过 `pipeline_meta.json` 关联回 profile

**输出：**

```
Outputs/queries_with_skills/
├── user_profile_1_程序员_20260312_210000_queries.json
├── user_profile_2_教师_20260312_210005_queries.json
└── ...
```

每个输出文件的结构：

```json
{
  "profile_rel_path": "user_profile_1_程序员_20260312_210000.json",
  "env_rel_path": "林辰_程序员",        // 仅环境模式存在
  "generated_at": "2026-03-12T21:00:00",
  "results": [
    {
      "topic": "编程问题解答",
      "skills": [
        { "skill名称": "Python编程", "skill目录": "coding-agents-and-ides/..." }
      ],
      "queries": [
        {"queries": "如何优化 Python 列表推导式的性能？", "required_skills": ["Python编程"]},
        {"queries": "Django REST framework 如何实现分页？", "required_skills": []},
        ...
      ]
    },
    {
      "topic": "文档撰写",
      "skills": [...],
      "queries": [...]
    }
  ]
}
```

**Skills 查询：** 每个 (topic, profile) 组合独立调用 `search_skills_by_topic()` 查询匹配的 skills（利用查询接口的随机性获得多样性）。

**退出码：** 全部成功 `0`，有失败 `1`。

---

### Step D: standard_format.py — 标准化打包输出

将 `query_gen_with_topic_skill_profile.py` 的输出整理为标准化的打包文件夹。支持两种模式：

- **纯 skills 模式**：为每组 (profile, topic) 创建独立的打包文件夹
- **env + skills 模式**：将 query 和 profile 写入已有的环境目录

**运行方式：**

```bash
# 纯 skills 模式（默认）
python ControlCenter/standard_format.py

# 指定输出目录
python ControlCenter/standard_format.py \
    --info-dir Outputs/queries_with_skills \
    --output-dir Outputs/standard_output

# env + skills 模式（JSON 中含 env_rel_path 时使用）
python ControlCenter/standard_format.py \
    --info-dir Outputs/queries_with_skills \
    --envs-dir Outputs/environments
```

**命令行参数：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--info-dir` | 输入目录（`query_gen_with_topic_skill_profile.py` 的输出） | `Outputs/queries_with_skills` |
| `--output-dir` | 输出目录（纯 skills 模式） | `Outputs/standard_output` |
| `--envs-dir` | 环境目录（env + skills 模式） | `None` |
| `--profiles-dir` | 用户画像源目录（用于复制 profile 文件） | `Outputs/profiles` |
| `--skills-dir` | skills 库目录（用于验证 skill 路径存在性） | `Outputs/skill_localize/skills_library` |

> `--output-dir` 和 `--envs-dir` 二选一：纯 skills 模式使用 `--output-dir`，env + skills 模式使用 `--envs-dir`。两者不可同时指定。

**输入：**

- `--info-dir` 下的 `*.json` 文件（`query_gen_with_topic_skill_profile.py` 的输出）

**输出 — 纯 skills 模式：**

```
Outputs/standard_output/
├── user_profile_1_程序员_20260312_210000_编程问题解答/
│   ├── user_profile_1_程序员_20260312_210000.json   # 原始 profile 副本
│   └── user_queries.json                             # 标准化 query 文件
├── user_profile_1_程序员_20260312_210000_文档撰写/
│   ├── user_profile_1_程序员_20260312_210000.json
│   └── user_queries.json
└── ...
```

**输出 — env + skills 模式：**

直接写入已有的环境目录：

```
Outputs/environments/林辰_程序员/
├── user_profile_1_程序员_20260312_210000.json   # 覆盖写入
├── user_queries.json                             # 覆盖写入
├── 林辰_程序员/                                   # 已有的模拟文件系统
│   └── ...
└── ...
```

**user_queries.json 结构（两种模式输出格式一致）：**

```json
[
  {
    "topic": "编程问题解答",
    "system_type": "windows",
    "queries": [
      "如何优化 Python 列表推导式的性能？",
      "Django REST framework 如何实现分页？"
    ],
    "skills": [
      "coding-agents-and-ides/some-skill",
      "cli-utilities/another-skill"
    ],
    "required_skills": [
      ["Python编程"],
      []
    ]
  }
]
```

- `queries`: 纯字符串列表，每条 query 的文本
- `required_skills`: `list[list[str]]`，与 `queries` 一一对应，记录每条 query 依赖的 skill 名称
- `skills`: 相对于 `--skills-dir` 的路径列表。程序会验证每个 skill 目录的存在性，不存在则报错

---

## 端到端流程总览

```
┌──────────────────────────────────────┐
│  Step A: generate_user_profile.py    │
│  生成用户画像 JSON                     │
│  输出 → Outputs/profiles/*.json      │
└──────────────┬───────────────────────┘
               │
       ┌───────┴───────┐
       ▼               ▼
┌──────────────┐  ┌────────────────────────────────────────┐
│  Step B:     │  │  Step C:                               │
│  batch_      │  │  query_gen_with_topic_skill_profile.py │
│  generate.py │  │  topic + skills + profile → query      │
│  画像→环境    │  │  输出 → Outputs/queries_with_skills/   │
│  输出 →      │  └──────────────┬─────────────────────────┘
│  Outputs/    │                 │
│  environments│                 ▼
└──────────────┘  ┌────────────────────────────────────────┐
                  │  Step D: standard_format.py            │
                  │  标准化打包                              │
                  │  输出 → Outputs/standard_output/       │
                  │    或写入 Outputs/environments/         │
                  └────────────────────────────────────────┘
```

> Step B 和 Step C 可并行执行（互不依赖）。Step D 依赖 Step C 的输出；若使用 env + skills 模式，还依赖 Step B 的输出。

---

## 管线详细流程（WorkingSpace/main.py）

`batch_generate.py` 内部调用的 4-Step 管线：

```
user_profile.txt / profile.json
        │
        ▼
┌─────────────────────────────┐
│  Step 1: ProfileAnalyzer    │  解析用户画像 → 结构化 JSON
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│  Step 2: ComputerSpecDesigner│  设计目录树 + 文件清单（55-70 个文件）
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│  Step 3: FileProcessor      │  创建目录 & 下载/生成文件
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│  Step 4: UserAgentBuilder   │  生成 user_agent.py
└─────────────────────────────┘
```

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
| `search_for_pdf(query)` | PDF 专用搜索，优先可信域名 |
| `search_for_filetype(query, exts)` | 按文件类型搜索 |
| `download_binary(url, path)` | 流式下载 + Content-Type/magic-byte 校验 |
| `read_url(url)` | Jina Reader 提取网页 → Markdown（上限 25k 字符） |

### ConfigLoader (`config/config_loader.py`)

- `load_config()` → 加载并缓存 `baseline_using.yaml`
- `get_prompt(path)` → 读取 prompt 模板文件内容

### llm_caller (`shared/llm_caller.py`)

全局单例 OpenAI 客户端，`chat_with_retry()` 提供带重试的 LLM 调用。

---

## 设计原则

1. **显性错误处理** — 异常直接报错并中断，不降级或抑制
2. **并行处理** — 文件处理、LLM 调用均使用 ThreadPoolExecutor
3. **信号量限流** — LLM 并发和搜索并发通过信号量/线程池控制
4. **配置驱动** — 所有路径、密钥、Prompt 集中在 `baseline_using.yaml`
5. **代码复用优先** — 优先复用项目内已有代码，减少新增
