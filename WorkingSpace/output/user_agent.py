import os

# Constants for API configuration
API_KEY = os.getenv("API_KEY", "sk-U2BkWhBzdLcJn01ovsXXESVO2nboXEjKqjj8WxECS6Dom5UZ")
BASE_URL = os.getenv("BASE_URL", "https://api.gptplus5.com/v1")
MODEL = os.getenv("MODEL", "gpt-4o")

SYSTEM_PROMPT = """
用户画像：
- 姓名：陈志远
- 性别：男
- 年龄：35
- 职业：汽车行业研究员
- 行业：新能源汽车
- 公司：中信证券研究所
- 部门：新能源汽车板块
- 操作系统：Windows 10
- 用户名：chenzhiyuan
- 主机名：CHEN-RESEARCH
- 硬盘布局：C, D
- 核心工具：Microsoft Office, Wind 金融终端, Xmind, 亿图图示, iSlide
- 文件类型：PDF, XLSX, PPTX, CSV
- 工作重点：分析车企财报, 处理销量数据, 研究行业政策, 撰写竞品研报
- 文件组织风格：按车企、政策、销量数据分类归档，桌面仅留常用工具快捷方式
- 性格：细致, 分析能力强, 结构化思维
- 领域关键词：新能源乘用车, 财报分析, 销量趋势, 政策解读, 市场研报
- 任务描述：撰写2023年第三季度比亚迪财报分析报告，结合政策变化与销量数据进行深度解读。
- 任务背景：领导要求在下周一前提交，需与财务部同事确认数据准确性。
- 行为风格：会主动追问, 提供截图/数据, 有时不耐烦, 希望助手直接给出操作步骤
"""

class UserAgent:
    def __init__(self):
        self.name = "陈志远"
        self.task_description = "撰写2023年第三季度比亚迪财报分析报告，结合政策变化与销量数据进行深度解读。"
        self.task_context = "领导要求在下周一前提交，需与财务部同事确认数据准确性。"

    def get_initial_message(self) -> str:
        return "您好，我需要撰写比亚迪2023年第三季度财报分析报告，请帮助我结合政策变化与销量数据进行深度解读。"

    def respond(self, assistant_msg: str, history: list) -> str:
        if "数据准确性" in assistant_msg:
            return "请帮助我确认数据的准确性，并提供相关的分析步骤。"
        elif "政策变化" in assistant_msg:
            return "请详细说明政策变化对比亚迪的影响。"
        elif "销量数据" in assistant_msg:
            return "请提供最新的销量数据分析。"
        else:
            return "请继续提供相关信息和分析建议。"

    def is_done(self, history: list) -> bool:
        for msg in history:
            if "报告完成" in msg or "任务完成" in msg:
                return True
        return False

if __name__ == "__main__":
    agent = UserAgent()
    print(f"用户角色信息: {SYSTEM_PROMPT}")
    print(f"任务说明: {agent.task_description}")
    print(f"初始消息: {agent.get_initial_message()}")

    history = []
    while True:
        assistant_input = input("助手输入: ")
        if assistant_input.lower() == "exit":
            break
        user_response = agent.respond(assistant_input, history)
        print(f"用户回复: {user_response}")
        history.append(user_response)
        if agent.is_done(history):
            print("任务已完成。")
            break