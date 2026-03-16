# -*- coding: utf-8 -*-
"""
User Profile 生成器
====================
基于 LLM 生成多样化的用户画像（user profile），保存到 Outputs/profiles 目录。

输出格式：
- 每个用户画像包含：基本信息、生活喜好、学习工作喜好、常用工具、常用网站、Query 示例
- 文件名格式：user_profile_序号_职业_时间戳.json
"""

import os, sys, json, argparse
from pathlib import Path
from datetime import datetime
import httpx, ssl
from openai import OpenAI
import time
import random

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
# ─── 维护的职业列表 ─────────────────────────────────────────────────────────
OCCUPATIONS = [
    # 一、国家机关 / 政务类
    "公务员", "民警", "法官", "检察官", "军人", 
    # 二、教育类
    "教师", "大学教授", "体育教练", "企业培训师",
    # 三、医疗健康类
    "主治医师", "护士", "药师", "牙医", "兽医",
    # 四、商业 / 金融类
    "会计师", "银行柜员", "证券分析师", "保险顾问", "企业家",
    # 五、IT / 互联网 / 技术类
    "程序员", "UI设计师", "产品经理", "运维工程师", "数据分析师", "网络工程师",
    # 六、文化传媒 / 艺术类
    "记者", "编辑", "主持人", "演员", "歌手", "摄影师", "作家",
    # 七、服务行业类
    "厨师", "餐厅服务员", "网约车司机", "导游", "美发师", "物业管理员",
    # 八、工程 / 建筑类
    "建筑师", "土木工程师", "施工员", "技术员",
    # 九、生产 / 制造业类
    "工厂操作工", "车间技术员", "质检员",
    # 十、农业 / 林业类
    "农民", "农业技术员", "护林员",
    # 十一、法律类
    "律师", "法务专员",
    # 十二、销售 / Market类
    "销售代表", "市场策划专员"
]

# ─── 用户画像生成提示词模板 ─────────────────────────────────────────────────────────
# 注意：使用 {gender}, {age}, {occupation} 作为占位符，每次生成前注入随机属性
PROFILE_GENERATION_PROMPT_TEMPLATE = """请生成一个用户档案，记录用户的基本信息，如姓名，性别，年龄，性格，职业，家庭身体情况，生活与学习中的喜好，常用的电脑软件工具与网站等。

【强制人物设定】（请务必基于以下设定进行合理扩展）
- 性别：{gender}
- 年龄：{age}岁
- 职业：{occupation}

已知电脑可以实现的操作如下：
• 网络/本地信息操作：网络搜索，数据库操作，调研与推荐
• 定时任务：闹钟，提醒，任务管理。。。
• 各种项目开发：脚本构建，跨软件自动化，快捷键定制。。。
• 内容整合：图表生成，摘要，数据清洗，合规校验等。。。
• 形式化展示：网页，ppt，海报，文档格式转换。。。
• 浏览器操作：社区互动，资料爬取，资料上传，github管理。。。
• 题目解答
• 各类工作流
• 系统操作管理
• 常用app或软件操作
• 生活技能：出行订改，购物选品，地图查询，计算，健康管理，理财。。。
• 多模态交互与处理：语音，图像，视频，文字的编辑，转换，识别，截取，生成，分析；代表场景娱乐创作：视频剪辑，文学创作，歌曲生成等。

输出为严格的JSON格式，档案格式示例：
{{
  "基本信息": {{
    "姓名": "林辰",
    "性别": "男",
    "年龄": 26,
    "性格": "理性严谨、注重效率、喜欢探索新技术、做事有条理、乐于钻研、温和内敛",
    "职业": "互联网行业AI算法/软件开发工程师",
    "家庭情况": "已经结婚，夫妻关系融洽，暂无子女但有计划",
    "身体情况": "无慢性疾病，但感冒次数多。身高178，体重130偏轻。睡眠情况不理想"
  }},
  "生活喜好": [
    "关注数码科技、智能产品与AI前沿动态",
    "喜欢高效规划生活，注重健康管理与时间安排",
    "对理财、资讯整理、影音创作有轻度兴趣",
    "每周至少一次游泳和慢跑，参加过马拉松比赛",
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
  "常用电脑工具": [
    "Google Chrome",
    "微信/企业微信（PC）",
    "WPS Office",
    "Notion",
    "Obsidian",
    "Evernote（历史资料）",
    "Adobe Premiere Pro",
    "DaVinci Resolve",
    "Adobe Audition",
    "Adobe Photoshop / Lightroom",
    "剪映专业版",
    "Final Draft（或国产剧本工具）",
    "Xmind",
    "Canva",
    "百度网盘/阿里云盘",
    "VLC",
    "讯飞听见（转写）",
    "日历与提醒（系统/滴答清单）"
  ],
  "常用网站": [
    "小红书（穿搭/妆造/通告信息）",
    "微博（行业动态/剧组信息）",
    "Bilibili（表演课、拉片、剪辑教程）",
    "豆瓣电影（片单与口碑）",
    "IMDb（对标作品）",
    "时光网",
    "站酷（海报/视觉参考）",
    "Canva网页版",
    "腾讯文档",
    "猫眼/淘票票（票房与宣发观察）",
    "高德地图/Google Maps",
    "携程/飞猪（出行预订）"
  ]
}}"""


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
        if self.proxy:
            httpx_client = httpx.Client(verify=False, proxy=self.proxy)
        else:
            httpx_client = httpx.Client(verify=False)

        ssl._create_default_https_context = ssl._create_unverified_context
        os.environ["OPENAI_API_KEY"] = self.api_key
        os.environ["OPENAI_BASE_URL"] = self.base_url
        self.client = OpenAI(http_client=httpx_client)

    def _get_random_attributes(self):
        """生成随机的性别、年龄和职业"""
        # 性别：均匀分布
        gender = random.choice(["男", "女"])
        
        # 年龄：正态分布 (均值35，标准差8)。
        # 使用 max 和 min 将年龄限制在 18 到 65 岁之间，确保符合职场逻辑
        age_raw = random.gauss(35, 8)
        age = max(18, min(65, int(age_raw)))
        
        # 职业：均匀分布
        occupation = random.choice(OCCUPATIONS)
        
        return gender, age, occupation

    def generate_profiles(self, count: int = 3, output_dir: Path = None) -> list[Path]:
        """生成用户画像并成功后立即保存"""
        saved_files = []

        for i in range(count):
            print(f"\n  [LLM] 生成第 {i+1}/{count} 个用户画像...")

            # 1. 触发随机引擎
            rand_gender, rand_age, rand_occupation = self._get_random_attributes()
            print(f"  [引擎] 本次随机设定 -> 性别: {rand_gender}, 年龄: {rand_age}, 职业: {rand_occupation}")

            # 2. 将随机设定注入提示词
            current_prompt = PROFILE_GENERATION_PROMPT_TEMPLATE.format(
                gender=rand_gender,
                age=rand_age,
                occupation=rand_occupation
            )

            max_retries = 3
            retry_delay = 2
            response = None

            for retry in range(max_retries):
                try:
                    start_time = time.time()
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "user", "content": current_prompt}
                        ]
                    )
                    elapsed = time.time() - start_time
                    print(f"  [LLM] 请求完成，耗时 {elapsed:.1f} 秒")
                    break  
                except Exception as e:
                    if retry < max_retries - 1:
                        wait_time = retry_delay * (retry + 1)
                        print(f"  [Retry] 请求失败，{wait_time}秒后重试 ({retry + 1}/{max_retries})...")
                        print(f"    错误: {e}")
                        time.sleep(wait_time)
                    else:
                        print(f"  [Error] 第 {i+1} 个画像生成失败（已重试{max_retries}次）: {e}")
                        response = None
                        continue  

            if response is None:
                continue
            # 如果请求失败，跳过本次
            if response is None:
                continue

            # 解析响应
            content = response.choices[0].message.content

            # 尝试提取 JSON（可能包含在 markdown 代码块中）
            import re
            # 方法1: 从 markdown 代码块中提取完整内容
            code_block_match = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
            if code_block_match:
                json_str = code_block_match.group(1).strip()
            else:
                first_brace = content.find("{")
                last_brace = content.rfind("}")
                if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                    json_str = content[first_brace:last_brace + 1]
                else:
                    json_str = content

            # 解析并保存 JSON
            try:
                profile = json.loads(json_str)
                basic = profile.get("基本信息", {})
                name = basic.get("姓名", "Unknown")
                role = basic.get("职业", rand_occupation)
                
                print(f"  [OK] 生成成功: {name} ({role})")

                # 生成成功后立马保存（原代码逻辑保留并优化文件命名）
                if output_dir:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_role = role.replace(' ', '_').replace('/', '_')
                    filename = f"user_profile_{i+1}_{safe_role}_{timestamp}.json"
                    filepath = output_dir / filename
                    filepath.write_text(
                        json.dumps(profile, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                    saved_files.append(filepath)
                    print(f"  [Save] 立即保存: {filename}")

                print(f"  [Wait] 休息 2 秒...")
                time.sleep(2)

            except json.JSONDecodeError as e:
                print(f"  [Error] 第 {i+1} 个画像解析失败: {e}")
                print(f"  [Debug] 提取的 JSON: {json_str[:200]}..." if len(json_str) > 200 else f"  [Debug] 提取的 JSON: {json_str}")

        print(f"\n  [Summary] 成功生成 {len(saved_files)}/{count} 个用户画像")
        return saved_files


def parse_args():
    parser = argparse.ArgumentParser(description="生成多样化的用户画像（user profile）")
    parser.add_argument("--output-dir", type=str, default=str(_PROFILES_DIR), help=f"输出目录（默认: {_PROFILES_DIR}）")
    parser.add_argument("--count", type=int, default=10, help="生成的用户画像数量（默认: 10）")
    return parser.parse_args()


def main():
    print("\n" + "=" * 60)
    print("  User Profile 生成器 (加入随机正态引擎版)")
    print("=" * 60)

    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  输出目录: {output_dir}")

    generator = ProfileGenerator(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        proxy=LLM_PROXY if LLM_PROXY else None
    )

    print("\n[步骤 1/2] 开始随机生成用户画像")
    saved_files = generator.generate_profiles(args.count, output_dir)

    if not saved_files:
        print("\n[Error] 生成用户画像失败，请检查 API 配置或网络连通性")
        return 1

    print("\n" + "=" * 60)
    print("  完成")
    print("=" * 60)
    print(f"\n  共生成并保存了 {len(saved_files)} 份文件:")
    for f in saved_files:
        print(f"  - {f}")
    print()
    return 0


if __name__ == "__main__":
    exit(main())
