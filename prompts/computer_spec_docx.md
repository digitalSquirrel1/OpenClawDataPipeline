用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 {file_count}个 由用户自己创作的Word/文本文档文件（type=generated）。
format 可以是 docx 或 txt。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "C/Users/{username}/Documents/工作笔记/比亚迪2023财报精读笔记.docx",
      "type": "generated",
      "format": "docx",
      "description": "比亚迪2023年报精读笔记，含财务指标分析和投资要点，详细剖析了公司营收结构、利润增长来源、新能源汽车销量贡献度、供应链优化成效，以及未来产能扩张计划和潜在投资风险评估。",
      "content_prompt": "生成一篇比亚迪2023年报精读笔记，包含：营收增长分析、毛利率变化、新车型销量贡献、海外市场拓展进展、主要投资风险。约1500字，专业券商研究风格。"
    }},
    ...（共{file_count}个）
  ]
}}
