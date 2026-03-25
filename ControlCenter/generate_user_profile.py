# -*- coding: utf-8 -*-
"""
User Profile 生成器
====================
基于 LLM 生成多样化的用户画像（user profile），保存到 Outputs/profiles 目录。

输出格式：
• 每个用户画像包含：基本信息、生活喜好、学习工作喜好、常用工具、常用网站、Query 示例

• 文件名格式：user_profile_序号_职业_时间戳.json

"""

import os, sys, json, re, time, random
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
_CONTROL_CENTER = Path(__file__).resolve().parent
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
LLM_MODEL    = os.getenv("LLM_MODEL",    _api_cfg.get("LLM_MODEL",       "gpt-4o"))

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
        self.batch_code = self._make_batch_code()
        # 从配置读取 prompt 模板
        prompt_path = _gen_cfg.get("PROFILE_GENERATION_PROMPT", "prompts/profile_generation_prompt.md")
        self.prompt_template = get_prompt(prompt_path)

    @staticmethod
    def _make_batch_code(now: datetime | None = None) -> str:
        """
        将运行开始时间压缩成 2 位批次码。
        同一轮生成共享同一个尾缀，文件唯一性仍由 index 保证。
        """
        now = now or datetime.now()
        minute_of_day = now.hour * 60 + now.minute
        return f"{minute_of_day % 100:02d}"

    def _get_random_attributes(self):
        """生成随机的性别、年龄和职业"""
        gender = random.choice(["男", "女"])
        age = max(18, min(65, int(random.gauss(35, 8))))
        occupation = random.choice(OCCUPATIONS)
        return gender, age, occupation

    def _build_identity_block(self) -> str:
        """构建单个人物设定的文本块"""
        g, a, o = self._get_random_attributes()
        return f"人物：性别 {g}，年龄 {a}岁，职业 {o}"

    def _call_llm(self, call_index: int) -> dict:
        """
        单次 LLM 调用，生成 1 个画像。
        返回解析出的 profile 字典。
        """
        identity_block = self._build_identity_block()
        prompt = self.prompt_template.replace("{identity_assignments}", identity_block)

        start_time = time.time()
        content = chat_with_retry(
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
        )
        elapsed = time.time() - start_time
        print(f"  [LLM] 第 {call_index} 次调用完成，耗时 {elapsed:.1f}s")

        # 提取 JSON
        code_block = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
        if code_block:
            json_str = code_block.group(1).strip()
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
            print(f"  [Debug] 第 {call_index} 次调用 JSON 解析失败: {e}")
            print(f"  [Debug] json_str 前 500 字符: {json_str[:500]}")
            raise

        # 兼容：如果返回的是 list 则取第一个
        if isinstance(parsed, list):
            if len(parsed) == 0:
                raise ValueError("LLM 返回空列表")
            parsed = parsed[0]
        if not isinstance(parsed, dict):
            raise ValueError(f"LLM 返回格式异常，期望 dict，得到 {type(parsed).__name__}")

        return parsed

    def _save_profile(self, profile: dict, index: int, profiles_dir: Path) -> Path:
        """将单个画像立即写入磁盘，返回文件路径。"""
        basic = profile.get("基本信息", {})
        name = basic.get("姓名", "Unknown")
        role = basic.get("职业", "Unknown")

        safe_role = role.replace(" ", "_").replace("/", "_")
        filename = f"user_profile_{index}_{safe_role}_{self.batch_code}.json"
        filepath = profiles_dir / filename
        filepath.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  [Saved] #{index}: {name} ({role}) -> {filepath.name}")
        return filepath

    def generate_profiles(self, count: int, profiles_dir: Path) -> list[Path]:
        """
        并行生成 count 个用户画像。
        每次 LLM 调用产出 1 个画像，用线程池并行调度。
        每个画像解析成功后立即写入磁盘。
        """
        import threading

        print(f"  [Plan] 总计 {count} 个画像，共 {count} 次 LLM 调用，并行度 {MAX_WORKERS}")

        saved_files: list[Path] = []
        failed_calls = 0
        _lock = threading.Lock()

        def _process_call(call_index: int):
            """调用 LLM 并将画像即时落盘。"""
            nonlocal failed_calls
            try:
                profile = self._call_llm(call_index)
                print(f"  [OK] 第 {call_index} 次调用解析成功")
                filepath = self._save_profile(profile, call_index, profiles_dir)
                with _lock:
                    saved_files.append(filepath)
            except Exception as e:
                with _lock:
                    failed_calls += 1
                print(f"  [Error] 第 {call_index} 次调用失败: {e}")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [
                pool.submit(_process_call, i + 1)
                for i in range(count)
            ]
            for f in as_completed(futures):
                f.result()  # 触发异常打印（实际已在内部 catch）

        print(f"\n  [Summary] 成功生成 {len(saved_files)}/{count} 个用户画像（{failed_calls} 次调用失败）")
        return saved_files


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  User Profile 生成器（随机身份引擎版）")
    print("=" * 60)

    # 从配置读取输出目录和数量（相对路径基于 _PROJECT_ROOT）
    _profiles_dir_str = _gen_cfg.get("profiles_dir")
    if _profiles_dir_str:
        p = Path(_profiles_dir_str)
        profiles_dir = p if p.is_absolute() else _PROJECT_ROOT / p
    else:
        profiles_dir = _PROFILES_DIR

    count = _gen_cfg.get("count") or 3

    # 创建输出目录
    profiles_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  输出目录: {profiles_dir}")
    print(f"  生成数量: {count}")

    # 初始化生成器
    generator = ProfileGenerator(model=LLM_MODEL)

    # 并行生成并保存用户画像
    print("\n[步骤 1/1] 并行生成并保存用户画像")
    saved_files = generator.generate_profiles(count, profiles_dir)

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
