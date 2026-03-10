import os

# Constants for API configuration
API_KEY = os.getenv("API_KEY", "sk-U2BkWhBzdLcJn01ovsXXESVO2nboXEjKqjj8WxECS6Dom5UZ")
BASE_URL = os.getenv("BASE_URL", "https://api.gptplus5.com/v1")
MODEL = os.getenv("MODEL", "gpt-4o")

# System prompt describing the user profile
SYSTEM_PROMPT = """
用户画像：
- 姓名：陈志远
- 性别：男
- 年龄：35
- 职业：汽车行业研究员
- 公司：华信证券研究所
- 部门：新能源汽车研究部

电脑环境：
- 操作系统：Windows 10
- 用户名：chenzhiyuan
- 主机名：CHEN-RESEARCH
- 磁盘布局：C, D
- 常用工具：Office, Wind 金融终端, Xmind, 亿图图示, iSlide
- 文件类型：PDF, XLSX, PPTX, CSV
- 文件组织：按车企、政策、销量数据分类归档，桌面仅留常用工具快捷方式

当前任务：
- 目标：完成《2023年新能源乘用车行业深度报告》
- 文件路径：D:\\Projects\\新能源汽车\\深度报告\\2023\\深度报告.docx
- 任务背景：报告需在本月末提交给部门主管，以供投资决策参考
- 需要分析：政策对销量的影响

行为风格：
- 细致、逻辑性强、研究导向
- 会主动追问、提供截图/数据
- 有时不耐烦，希望助手直接给出操作步骤
"""

class UserAgent:
    def __init__(self):
        self.name = "陈志远"
        self.role = "汽车行业研究员"
        self.task_description = "完成《2023年新能源乘用车行业深度报告》，需分析政策对销量的影响。"
        self.task_context = "报告需在本月末提交给部门主管，以供投资决策参考。"
        self.done_keywords = ["完成", "提交", "结束"]

    def get_initial_message(self) -> str:
        return "我需要完成《2023年新能源乘用车行业深度报告》，请帮我分析政策对销量的影响。"

    def respond(self, assistant_msg: str, history: list) -> str:
        if "政策" in assistant_msg and "销量" in assistant_msg:
            return "这部分分析很有帮助，我会将其纳入报告中。还有其他需要注意的点吗？"
        if "总结" in assistant_msg:
            return "谢谢，我会根据这些信息撰写报告。"
        return "请继续提供分析，尤其是政策对销量的具体影响。"

    def is_done(self, history: list) -> bool:
        for msg in history:
            if any(keyword in msg for keyword in self.done_keywords):
                return True
        return False

if __name__ == "__main__":
    user_agent = UserAgent()
    print(f"用户角色信息：\n姓名：{user_agent.name}\n角色：{user_agent.role}\n")
    print(f"任务说明：{user_agent.task_description}\n")
    
    print(f"用户初始消息：{user_agent.get_initial_message()}")
    history = []
    
    while True:
        assistant_msg = input("助手: ")
        user_reply = user_agent.respond(assistant_msg, history)
        print(f"用户: {user_reply}")
        history.append(assistant_msg)
        history.append(user_reply)
        
        if user_agent.is_done(history):
            print("任务已完成。")
            break
        
        if assistant_msg.lower() == "exit":
            print("退出交互。")
            break