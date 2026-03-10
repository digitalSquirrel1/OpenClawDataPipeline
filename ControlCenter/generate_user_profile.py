# -*- coding: utf-8 -*-
"""
User Profile 生成器
====================
基于 LLM 生成多样化的用户画像（user profile），保存到 Outputs/profiles 目录。

输出格式：
• 每个用户画像包含：基本信息、生活喜好、学习工作喜好、常用工具、常用网站、Query 示例

• 文件名格式：user_profile_序号_职业_时间戳.json

"""

import os, sys, json
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

# ─── 加载配置 ──────────────────────────────────────────────────────────────────
sys.path.insert(0, str(_PROJECT_ROOT))
from config.config_loader import load_config, get_prompt
from shared.llm_caller import chat_with_retry

_cfg = load_config()
_api_cfg = _cfg.get("api_config", {})
_gen_cfg = _cfg.get("generate_user_profile_config", {})

# ─── LLM API 配置 ────────────────────────────────────────────────────────────
LLM_API_KEY  = os.getenv("LLM_API_KEY",  _api_cfg.get("LLM_API_KEY",  "sk-U2BkWhBzdLcJn01ovsXXESVO2nboXEjKqjj8WxECS6Dom5UZ"))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", _api_cfg.get("LLM_BASE_URL", "https://api.gptplus5.com/v1"))
LLM_MODEL    = os.getenv("LLM_MODEL",    _api_cfg.get("LLM_MODEL",    "gpt-5.2"))
LLM_PROXY    = os.getenv("LLM_PROXY",    _api_cfg.get("LLM_PROXY",    None))

# ─── 用户画像生成提示词（从配置文件读取） ────────────────────────────────────────
_prompt_path = _gen_cfg.get("PROFILE_GENERATION_PROMPT")
PROFILE_GENERATION_PROMPT = get_prompt(_prompt_path) if _prompt_path else ""


class ProfileGenerator:
    """用户画像生成器"""

    def __init__(self, model: str):
        self.model = model

    def generate_profiles(self) -> list[dict]:
        """生成用户画像（批量），通过 chat_with_retry 调用 LLM"""
        import time
        print(f"  [LLM] 正在调用 {self.model} 生成用户画像...")

        start_time = time.time()

        content = chat_with_retry(
            messages=[{"role": "user", "content": PROFILE_GENERATION_PROMPT}],
            model=self.model,
        )

        elapsed = time.time() - start_time
        print(f"  [LLM] 请求完成，耗时 {elapsed:.1f} 秒")

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


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  User Profile 生成器")
    print("=" * 60)

    # 从配置读取输出目录和数量（不再使用 parse_args）
    _output_dir_str = _gen_cfg.get("output_dir")
    output_dir = Path(_output_dir_str) if _output_dir_str else _PROFILES_DIR

    count = _gen_cfg.get("count")
    if count is None:
        count = 3

    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  输出目录: {output_dir}")
    print(f"  生成数量: {count}")

    # 初始化生成器
    generator = ProfileGenerator(model=LLM_MODEL)

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
