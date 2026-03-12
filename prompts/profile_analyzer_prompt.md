
请将以下用户画像文本解析为结构化JSON。字段说明见后。

---用户画像---
{profile_text}
---end---

请直接输出有效的JSON，所有字段均需填写，不得省略，标准格式如下：
{{
  "name": "根据角色特征生成一个真实感强的中文姓名（如：陈志远）",
  "gender": "男/女",
  "age": 推测年龄整数,
  "role": "职业角色（精确描述）",
  "industry": "所在行业",
  "company": "推测的单位名称（不必是真实公司，要有说服力）",
  "department": "所在部门",
  "os": "操作系统全称",
  "username": "Windows用户名（英文/拼音，如：chenzhiyuan）",
  "hostname": "电脑名（如：CHEN-RESEARCH）",
  "drive_layout": ["C", "D"],
  "core_tools": ["软件列表"],
  "file_types": ["经常处理的文件类型，如：PDF、XLSX、PPTX、CSV"],
  "work_focus": ["主要工作内容，每条简洁"],
  "file_organization_style": "文件组织习惯的描述",
  "personality": ["性格特征，影响任务描述风格"],
  "domain_keywords": ["领域关键词，用于搜索相关文件"],
  "task_description": "这个用户当前最典型的一项具体工作任务（要具体，包含文件名/路径引用，200字以内）",
  "task_context": "任务背景（领导/同事/截止日期等场景信息，100字以内）"
}}
