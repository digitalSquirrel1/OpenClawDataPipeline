
根据以下用户画像，设计一个真实的 Linux（Ubuntu）电脑目录结构。

--- 用户画像 ---
{profile_json}
--- end ---

该用户使用 Linux 系统，主目录为 ~/ (即 /home/{username}/)。
请生成至少 35 个目录，按工作习惯深层分级，例如：
  Documents/研究资料/车企财报/比亚迪/2022/
  Documents/研究资料/车企财报/比亚迪/2023/
  Documents/工作文档/深度报告/2024/Q1/
  Desktop/
  Downloads/
  Projects/数据分析/xxx/
  ...

注意：
- 不要使用 Windows 盘符（C:/, D:/, E:/ 等），使用 Linux 家目录下的标准目录
- 路径不需要 ~/ 前缀，直接从 Documents/、Downloads/、Desktop/、Projects/ 等开始
- 常用顶级目录：Documents、Downloads、Desktop、Projects、Pictures、Videos、Music、.config 等
- 可以根据用户职业特点创建自定义顶级目录（如 Research、Data、Archives 等）
- 把 Windows 环境中通常放在 D 盘、E 盘的工作资料，合理分配到 Documents、Projects、Research、Data 等目录中

请直接输出有效的JSON，标准格式如下：
{{
  "directories": [
    "Documents/研究资料/车企财报/比亚迪/2022",
    "Documents/研究资料/车企财报/比亚迪/2023",
    ...（至少35个）
  ]
}}
