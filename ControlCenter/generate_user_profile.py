# -*- coding: utf-8 -*-
"""
User Profile 生成器
====================
基于 LLM 生成多样化的用户画像（user profile），保存到 Outputs/profiles 目录。

输出格式：
• 每个用户画像包含：基本信息、生活喜好、学习工作喜好、常用工具、常用网站、Query 示例

• 文件名格式：user_profile_序号_职业_时间戳.json

"""

import os, sys, json, re, time, math, random
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

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

# ─── 每次 LLM 调用生成的画像数量 ───────────────────────────────────────────────
PROFILES_PER_CALL = 3

# ─── 并行线程数（复用 pipeline_config.MAX_WORKERS 或默认 4）─────────────────────
_pipeline_cfg = _cfg.get("pipeline_config", {})
MAX_WORKERS = int(os.getenv("MAX_LLM_CALLS", _pipeline_cfg.get("MAX_LLM_CALLS", 4)))

# ─── 维护的职业列表 ──────────────────────────────────────────────────────────────
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


class ProfileGenerator:
    """用户画像生成器"""

    def __init__(self, model: str):
        self.model = model
        # 从配置读取 prompt 模板
        prompt_path = _gen_cfg.get("PROFILE_GENERATION_PROMPT", "prompts/profile_generation_prompt.md")
        self.prompt_template = get_prompt(prompt_path)

    def _get_random_attributes(self):
        """生成随机的性别、年龄和职业"""
        gender = random.choice(["男", "女"])
        age = max(18, min(65, int(random.gauss(35, 8))))
        occupation = random.choice(OCCUPATIONS)
        return gender, age, occupation

    def _build_identity_block(self, n: int) -> str:
        """构建 n 个人物设定的文本块"""
        lines = []
        for i in range(n):
            g, a, o = self._get_random_attributes()
            lines.append(f"人物{i+1}：性别 {g}，年龄 {a}岁，职业 {o}")
        return "\n".join(lines)

    def _call_llm_batch(self, batch_index: int, need: int) -> list[dict]:
        """
        单次 LLM 调用，生成 need 个画像（need <= PROFILES_PER_CALL）。
        返回解析出的 profile 字典列表。
        """
        identity_block = self._build_identity_block(need)
        prompt = self.prompt_template.replace("{identity_assignments}", identity_block)

        start_time = time.time()
        content = chat_with_retry(
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
        )
        elapsed = time.time() - start_time
        print(f"  [LLM] 批次 {batch_index} 完成，耗时 {elapsed:.1f}s")

        # 提取 JSON
        code_block = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
        if code_block:
            json_str = code_block.group(1).strip()
        else:
            first_bracket = content.find("[")
            last_bracket = content.rfind("]")
            if first_bracket != -1 and last_bracket > first_bracket:
                json_str = content[first_bracket:last_bracket + 1]
            else:
                first_brace = content.find("{")
                last_brace = content.rfind("}")
                if first_brace != -1 and last_brace > first_brace:
                    json_str = content[first_brace:last_brace + 1]
                else:
                    json_str = content

        # 清洗 LLM 常见的 JSON 格式问题：尾逗号
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"  [Debug] 批次 {batch_index} JSON 解析失败: {e}")
            print(f"  [Debug] json_str 前 500 字符: {json_str[:500]}")
            raise

        # 兼容：如果返回的是单个 dict 而非 list
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            raise ValueError(f"LLM 返回格式异常，期望 list，得到 {type(parsed).__name__}")

        return parsed

    def _save_profile(self, profile: dict, index: int, output_dir: Path) -> Path:
        """将单个画像立即写入磁盘，返回文件路径。"""
        basic = profile.get("基本信息", {})
        name = basic.get("姓名", "Unknown")
        role = basic.get("职业", "Unknown")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_role = role.replace(" ", "_").replace("/", "_")
        filename = f"user_profile_{index}_{safe_role}_{timestamp}.json"
        filepath = output_dir / filename
        filepath.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  [Saved] #{index}: {name} ({role}) -> {filepath.name}")
        return filepath

    def generate_profiles(self, count: int, output_dir: Path) -> list[Path]:
        """
        并行生成 count 个用户画像。
        每次 LLM 调用产出 PROFILES_PER_CALL 个，用线程池并行调度。
        每个画像解析成功后立即写入磁盘，不依赖全部批次完成。
        """
        import threading
        num_calls = math.ceil(count / PROFILES_PER_CALL)
        # 最后一个批次可能不足 PROFILES_PER_CALL
        batch_sizes = [PROFILES_PER_CALL] * (num_calls - 1) + [count - PROFILES_PER_CALL * (num_calls - 1)]

        print(f"  [Plan] 总计 {count} 个画像，分 {num_calls} 批调用 LLM（每批 {PROFILES_PER_CALL} 个），并行度 {MAX_WORKERS}")

        saved_files: list[Path] = []
        failed_batches = 0
        _lock = threading.Lock()
        _counter = [0]  # 全局递增序号（用 list 以便闭包可修改）

        def _process_batch(batch_index: int, need: int):
            """调用 LLM 并将每个画像即时落盘。"""
            nonlocal failed_batches
            try:
                profiles = self._call_llm_batch(batch_index, need)
                print(f"  [OK] 批次 {batch_index} 解析成功，得到 {len(profiles)} 个画像")
                for profile in profiles:
                    with _lock:
                        _counter[0] += 1
                        idx = _counter[0]
                        if idx > count:
                            return  # 已达 count 上限，丢弃多余
                    filepath = self._save_profile(profile, idx, output_dir)
                    with _lock:
                        saved_files.append(filepath)
            except Exception as e:
                with _lock:
                    failed_batches += 1
                print(f"  [Error] 批次 {batch_index} 失败: {e}")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [
                pool.submit(_process_batch, i + 1, batch_sizes[i])
                for i in range(num_calls)
            ]
            for f in as_completed(futures):
                f.result()  # 触发异常打印（实际已在内部 catch）

        print(f"\n  [Summary] 成功生成 {len(saved_files)}/{count} 个用户画像（{failed_batches} 批失败）")
        return saved_files


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  User Profile 生成器（随机身份引擎版）")
    print("=" * 60)

    # 从配置读取输出目录和数量
    _output_dir_str = _gen_cfg.get("output_dir")
    output_dir = Path(_output_dir_str) if _output_dir_str else _PROFILES_DIR

    count = _gen_cfg.get("count") or 3

    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  输出目录: {output_dir}")
    print(f"  生成数量: {count}")

    # 初始化生成器
    generator = ProfileGenerator(model=LLM_MODEL)

    # 并行生成并保存用户画像
    print("\n[步骤 1/1] 并行生成并保存用户画像")
    saved_files = generator.generate_profiles(count, output_dir)

    if not saved_files:
        print("\n[Error] 生成用户画像失败，请检查 API 配置")
        return 1

    # 完成
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
