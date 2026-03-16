# -*- coding: utf-8 -*-
"""
Step 4 — User Query Generator
生成用户日常可能会询问的query，基于用户profile和电脑文件内容。

生成的query类型包括：
  - 生活相关：日程安排、娱乐、健康、个人理财等
  - 学习相关：知识问询、技能学习、数据分析、行业研究等
"""
import json
from utils.llm_client import LLMClient

PROMPT_USER_QUERIES = """
根据以下用户画像和用户电脑中的文件/目录结构，生成5个用户日常可能会询问的使用计算机工具解决的自然语言queries。

--- 用户画像 ---
{profile_json}
--- end ---

--- 用户电脑文件结构摘要 ---
目录数量：{dir_count}个
文件类型分布：
{file_types_summary}
文件样例：
{file_samples}
--- end ---

请生成5个自然、真实的用户query，反映该用户在学习、生活中可能提出的问题，不要涉及工作相关的内容。

已知计算机常用的操作包括但不限于：

- **文件管理**：查找、整理、重命名、删除、批量处理等
- **数据处理**：数据清洗、分析、可视化、模型训练等
- **文档编辑**：撰写、修改、格式调整、内容生成等
- **网络/本地信息操作**：
  - 网络搜索、数据库操作
  - 调研与推荐
- **通信与日程**：
  - 邮件操作
  - 定时任务（闹钟、提醒、任务管理）
- **内容整合**：
  - 图表生成
  - 摘要撰写
  - 数据清洗
  - 合规校验
- **形式化展示**：
  - 网页、PPT、海报制作
  - 文档格式转换
- **浏览器操作**：
  - 社区互动
  - 资料爬取与上传
  - 网站项目管理
- **题目解答**
- **各类工作流**
- **系统操作管理**
- **常用应用/软件操作**
- **生活技能**：
  - 出行订改、购物选品
  - 地图查询、计算
  - 健康管理、理财
- **多模态交互与处理**：
  - 语音、图像、视频、文字的编辑、转换、识别、截取、生成、分析
  - 娱乐创作场景：视频剪辑、文学创作、歌曲生成等

生成的query可以是上述独立的功能或这些功能的组合，完全具体、可直接执行、无模糊信息、无任何歧义、符合电脑真实操作场景的Query。
严禁宽泛性query，如“对xxx图片进行剪裁”，不知道要剪裁成什么样导致无法执行，query种类尽量多样，不要全部是同一领域。

query类型可包括：
1. 个人生活助手
（聚焦个人非工作、非学习的日常场景，覆盖生活琐事、居家、健康、出行、财务、娱乐等，提升生活舒适度与趣味性）
    娱乐兴趣与资讯推荐
    出行与订购
    日常事务与日程提醒
    其他（健康与习惯养成，个人理财，家居控制等）
2. 学习与知识管理（面向个人学习成长、个性化教育、知识沉淀、学术研究等场景，实现学习资料和课程内容的自动获取与管理）
    知识搜索与研究
    学习与研究资料管理
    学习计划与课程管理
    其他（习题练习与错题复盘等）

输出JSON格式（只有queries数组，无其他内容）：
{{
  "queries": [
    "查询1：对photo/2025_travel下的IMG_001.jpg、IMG_002.jpg、IMG_003.jpg进行批量裁剪、滤镜处理，去除路人和车辆，图片要改为暗色调。",
    "查询2：...",
    "查询3：...",
    "查询4：...",
    "查询5：..."
  ]
}}
"""


class UserQueryGenerator:
    """根据用户profile和电脑环境生成用户query"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def _build_file_types_summary(self, spec: dict) -> str:
        """构建文件类型摘要"""
        files = spec.get("files", [])
        
        # 按类型统计
        type_counts = {}
        for f in files:
            sub_type = f.get("sub_type", f.get("format", "unknown"))
            type_counts[sub_type] = type_counts.get(sub_type, 0) + 1
        
        # 格式化输出
        summary_lines = []
        for file_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            summary_lines.append(f"  - {file_type}: {count}个文件")
        
        return "\n".join(summary_lines) if summary_lines else "  无文件类型统计"

    def _build_file_samples(self, spec: dict) -> str:
        """收集文件样例"""
        files = spec.get("files", [])
        
        # 取前20个文件作为样例
        samples = []
        for f in files:
            path = f.get("path", "")
            description = f.get("description", "").replace("\n", " ")
            samples.append(f"  - {path}")
            if description:
                samples.append(f"    → {description}")
        
        return "\n".join(samples) if samples else "  无文件样例"

    def generate(self, profile: dict, spec: dict) -> dict:
        """生成用户query"""
        profile_json = json.dumps(profile, ensure_ascii=False, indent=2)
        directories = spec.get("directories", [])
        files = spec.get("files", [])
        
        print("[Step 4] 生成用户日常查询...")
        
        # 构建prompt所需的信息
        file_types_summary = self._build_file_types_summary(spec)
        file_samples = self._build_file_samples(spec)
        
        prompt = PROMPT_USER_QUERIES.format(
            profile_json=profile_json,
            dir_count=len(directories),
            file_types_summary=file_types_summary,
            file_samples=file_samples,
        )
        
        try:
            result = self.llm.generate_json(
                prompt,
                system="你是一名专业的用户行为分析专家。基于用户的工作特征和文件环境，生成真实、自然的用户查询。只输出合法JSON，不要有任何注释或多余文字。",
                max_tokens=2000
            )
            queries = result.get("queries", [])
            print(f"  → 生成 {len(queries)} 个user query")
            return {
                "queries": queries,
                "profile": profile,
                "spec_summary": {
                    "directories_count": len(directories),
                    "files_count": len(files),
                    "file_types": self._get_file_types(spec),
                }
            }
        except Exception as e:
            print(f"  [!] User query生成失败: {e}")
            return {
                "queries": [],
                "profile": profile,
                "error": str(e),
            }

    def _get_file_types(self, spec: dict) -> dict:
        """获取文件类型统计"""
        files = spec.get("files", [])
        type_counts = {}
        for f in files:
            sub_type = f.get("sub_type", f.get("format", "unknown"))
            type_counts[sub_type] = type_counts.get(sub_type, 0) + 1
        return type_counts
