# -*- coding: utf-8 -*-
"""
User Profile 生成器
====================
基于 LLM 生成多样化的用户画像（user profile），保存到 Outputs/profiles 目录。

输出格式：
• 每个用户画像包含：基本信息、生活喜好、学习工作喜好、常用工具、常用网站、Query 示例

• 文件名格式：user_profile_序号_职业_时间戳.json

"""

import os, sys, json, argparse
from pathlib import Path
from datetime import datetime

# 支持中文字符显示
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ─── 项目路径设置 ───────────────────────────────────────────────────────────────
_CONTROL_CENTER = Path(__file__).parent
_PROJECT_ROOT = _CONTROL_CENTER.parent
# profiles 目录放在项目根目录的 Outputs 下
_OUTPUTS_DIR = _PROJECT_ROOT / "Outputs"
_PROFILES_DIR = _OUTPUTS_DIR / "profiles"

# ─── LLM API 配置（参考 openai_api_v2.py）────────────────────────────────────────
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-U2BkWhBzdLcJn01ovsXXESVO2nboXEjKqjj8WxECS6Dom5UZ")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.gptplus5.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5.2")
LLM_PROXY = os.getenv("LLM_PROXY", "http://10.90.91.193:3127")

# ─── 用户画像生成提示词 ─────────────────────────────────────────────────────────
PROFILE_GENERATION_PROMPT = """请生成三个完全不同的用户档案，记录用户的基本信息，如姓名，性别，年龄，性格，职业，家庭身体情况，生活与学习中的喜好，常用的电脑软件工具与网站等，每份档案各项信息差别要大。
同时根据他的生活和学习喜好各生成3条需要使用电脑完成的query，比如查股票行情，进行数据操作等。已知电脑可以实现的操作如下：
•	网络/本地信息操作：网络搜索，数据库操作，调研与推荐
•	邮件操作
•	定时任务：闹钟，提醒，任务管理。。。
•	各种项目开发：脚本构建，跨软件自动化，快捷键定制。。。
•	内容整合：图表生成，摘要，数据清洗，合规校验等
•	形式化展示：网页，ppt，海报，文档格式转换。。。
•	浏览器操作：社区互动，资料爬取，资料上传，github管理。。。
•	题目解答
•	各类工作流
•	系统操作管理
•	常用app或软件操作
•	生活技能：出行订改，购物选品，地图查询，计算，健康管理，理财。。。
•	多模态交互与处理：语音，图像，视频，文字的编辑，转换，识别，截取，生成，分析；代表场景娱乐创作：视频剪辑，文学创作，歌曲生成等。

（重要！！）生成的query可以是上述独立的功能或这些功能的组合，完全具体、可直接执行、无模糊信息、无任何歧义、符合电脑真实操作场景的Query。Query内如果使用文件路径需要使用相对路径，严禁宽泛性query，如"对xxx图片进行剪裁"，不知道要剪裁成什么样导致无法执行。

输出为json格式，用list包含多个档案信息。档案格式示例：
{
  "基本信息": {
    "姓名": "林辰",
    "性别": "男",
    "年龄": 26,
    "性格": "理性严谨、注重效率、喜欢探索新技术、做事有条理、乐于钻研、温和内敛",
"职业": "互联网行业AI算法/软件开发工程师"
"家庭情况": "已经结婚，夫妻关系融洽，暂无子女但有计划",
"身体情况": "无慢性疾病，但感冒次数多。身高178，体重130偏轻。睡眠情况不理想",
  },
  "生活喜好": [
    "关注数码科技、智能产品与AI前沿动态",
    "喜欢高效规划生活，注重健康管理与时间安排",
"对理财、资讯整理、影音创作有轻度兴趣",
"每周至少一次游泳和慢跑，参加过马拉松比赛，",
"对冒险类电影非常热爱",
"喜欢动作类电子游戏",
    "习惯用电脑/工具提升生活效率，拒绝繁琐手动操作"
  ],
  "学习工作喜好": [
    "专注AI大模型、算法、编程开发、技术部署",
    "喜欢做结构化资料整理、数据处理、内容输出",
    "热衷自动化工具、脚本、工作流优化",
    "常需要做演示文档、技术调研、项目开发与调试"
  ],
  "常用电脑工具": "办公类软件，PDF阅读器，理财类软件，批图软件，新闻查询软件，健康监督软件，VS-code。",
  "常用网站": "github，Arxiv，Stack Overflow，ProcessOn，豆包，Hugging Face，豆瓣电影，Bilibili，NGA",
  "生活类电脑操作Query": [
    "根据'health'目录中的个人健康数据（睡眠、运动、饮食等），进行数据清洗+图表生成+健康分析，生成周健康报告",
"查看广发汽车指数C和华宝价值基金A以及塞力斯近一周的走势，根据我的投资情况生成可视化报表，用pdf格式保存，然后用Adobe pdf阅读器打开。",
" 对photo/2025_travel下的IMG_001.jpg、IMG_002.jpg、IMG_003.jpg进行批量裁剪、滤镜处理，去除路人和车辆，图片要改为暗色调。"
  ],
  "学习类电脑操作Query": [
    "进行网络调研+资料爬取+内容摘要+数据整合，生成一份AI领域技术趋势调研报告",
"Openclaw加载新的技能要怎么做，帮我做一个演示示例",
" 对doc/AI_research文件夹下的paper1.pdf、paper2.pdf、paper3.pdf提取文本、生成摘要并整合为一份 Markdown 文档。"
  ]}"""


class ProfileGenerator:
    """用户画像生成器"""

    def __init__(self, api_key: str, base_url: str, model: str, proxy: str = None):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.proxy = proxy
        self._init_client()

    def _init_client(self):
        """初始化 LLM 客户端"""
        import httpx
        from openai import OpenAI
        import ssl

        # 设置代理（如果需要）
        if self.proxy:
            httpx_client = httpx.Client(verify=False, proxy=self.proxy)
        else:
            httpx_client = httpx.Client(verify=False)

        # 忽略 SSL 证书验证（仅用于开发/测试）
        ssl._create_default_https_context = ssl._create_unverified_context

        # 设置环境变量
        os.environ["OPENAI_API_KEY"] = self.api_key
        os.environ["OPENAI_BASE_URL"] = self.base_url

        self.client = OpenAI(http_client=httpx_client)

    def generate_profiles(self) -> list[dict]:
        """生成用户画像（批量）"""
        print(f"  [LLM] 正在调用 {self.model} 生成用户画像...")

        start_time = __import__("time").time()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": PROFILE_GENERATION_PROMPT}
            ]
        )

        elapsed = __import__("time").time() - start_time
        print(f"  [LLM] 请求完成，耗时 {elapsed:.1f} 秒")

        # 解析响应
        content = response.choices[0].message.content

        # 尝试提取 JSON（可能包含在 markdown 代码块中）
        import re
        json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = content

        # 解析 JSON
        try:
            profiles = json.loads(json_str)
            print(f"  [OK] 成功生成 {len(profiles)} 个用户画像")
            return profiles
        except json.JSONDecodeError as e:
            print(f"  [Error] JSON 解析失败: {e}")
            print(f"  [Debug] 响应内容: {content[:200]}...")
            return []

    def save_profiles(self, profiles: list[dict], output_dir: Path) -> list[Path]:
        """保存用户画像到 JSON 文件"""
        saved_files = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for idx, profile in enumerate(profiles, 1):
            basic = profile.get("基本信息", {})
            name = basic.get("姓名", f"User{idx}")
            role = basic.get("职业", "Unknown").replace(" ", "_").replace("/", "_")

            # 生成文件名（仅 JSON 格式）
            filename = f"user_profile_{idx}_{role}_{timestamp}.json"
            filepath = output_dir / filename

            # 保存为 JSON 格式
            filepath.write_text(
                json.dumps(profile, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            saved_files.append(filepath)
            print(f"  [Save] {filename}")

        return saved_files


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="生成多样化的用户画像（user profile）"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(_PROFILES_DIR),
        help=f"输出目录（默认: {_PROFILES_DIR}）"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="生成的用户画像数量（默认: 3）"
    )
    return parser.parse_args()


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  User Profile 生成器")
    print("=" * 60)

    # 解析参数
    args = parse_args()
    output_dir = Path(args.output_dir)

    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  输出目录: {output_dir}")

    # 初始化生成器
    generator = ProfileGenerator(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        proxy=LLM_PROXY if LLM_PROXY else None
    )

    # 生成用户画像
    print("\n[步骤 1/2] 生成用户画像")
    profiles = generator.generate_profiles()

    if not profiles:
        print("\n[Error] 生成用户画像失败，请检查 API 配置")
        return 1

    # 保存文件
    print("\n[步骤 2/2] 保存用户画像")
    saved_files = generator.save_profiles(profiles, output_dir)

    # 完成
    print("\n" + "=" * 60)
    print("  完成")
    print("=" * 60)
    print(f"\n  生成数量: {len(profiles)}")
    for f in saved_files:
        print(f"  - {f}")
    print()
    return 0


if __name__ == "__main__":
    exit(main())