# -*- coding: utf-8 -*-
"""
Step 4 — User Agent Builder
Generates a self-contained user_agent.py that simulates the user
doing a specific task while interacting with an external AI assistant.
"""
import json
from utils.llm_client import LLMClient

SYSTEM = "你是一名资深AI应用开发工程师，擅长设计角色扮演型AI Agent。只输出纯Python代码。"

PROMPT_TMPL = """
请为以下用户画像生成一个完整的 user_agent.py 文件。

--- 用户画像 ---
{profile_json}

--- 电脑环境（关键文件摘要）---
{file_summary}

--- 任务 ---
{task_description}
任务背景：{task_context}

--- 要求 ---
1. 生成的文件是完整可运行的Python脚本
2. 使用OpenAI兼容API（base_url、api_key可通过顶部常量配置，也可被环境变量覆盖）
3. 包含一个详细的SYSTEM_PROMPT，描述：
   - 用户的身份、性格、工作背景
   - 用户的电脑环境（操作系统、关键文件路径、常用软件）
   - 用户当前的任务目标
   - 用户的行为风格（会主动追问、提供截图/数据、有时不耐烦、希望助手直接给出操作步骤）
4. 包含 UserAgent 类，核心方法：
   - get_initial_message() → str  # 任务开始的第一条消息
   - respond(assistant_msg: str, history: list) → str  # 根据助手回复生成用户的下一条消息
   - is_done(history: list) → bool  # 判断任务是否完成（检测关键词）
5. 包含 if __name__ == "__main__" 的CLI交互循环：
   - 打印用户角色信息和任务说明
   - 输出用户的初始消息
   - 接收外部助手输入（input()），生成用户回复
   - 循环直到任务完成或输入"exit"
6. API_KEY 默认值为 "{api_key}"
7. BASE_URL 默认值为 "{base_url}"
8. MODEL 默认值为 "{model}"

只输出Python代码，不要有任何解释或markdown包裹。
"""


def _build_file_summary(spec: dict) -> str:
    lines = []
    for f in spec.get("files", [])[:20]:
        lines.append(f"  - {f['path']}  ({f.get('description','')})")
    return "\n".join(lines)


class UserAgentBuilder:
    def __init__(self, llm: LLMClient,
                 api_key: str, base_url: str, model: str):
        self.llm      = llm
        self.api_key  = api_key
        self.base_url = base_url
        self.model    = model

    def build(self, profile: dict, spec: dict) -> str:
        """Return the content of user_agent.py as a string."""
        print("[Step 4] 生成 user_agent.py ...")
        file_summary = _build_file_summary(spec)
        prompt = PROMPT_TMPL.format(
            profile_json     = json.dumps(profile, ensure_ascii=False, indent=2),
            file_summary     = file_summary,
            task_description = profile.get("task_description", ""),
            task_context     = profile.get("task_context", ""),
            api_key          = self.api_key,
            base_url         = self.base_url,
            model            = self.model,
        )
        code = self.llm.generate(prompt, system=SYSTEM, temperature=0.4)
        # strip markdown fences if present
        code = code.strip()
        if code.startswith("```"):
            lines = code.split("\n")
            code  = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        print(f"  → 生成代码 {len(code)} chars")
        return code

    def save(self, code: str, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"  → 已保存：{path}")
