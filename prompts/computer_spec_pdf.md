用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 {file_count}个 可从公网下载的真实PDF文件。

每个文件的 search_query 必须精准，能搜到真实可下载的PDF。

输出 JSON（只有files数组，不要其他键）：
{{
  "files": [
    {{
      "path": "D/研究资料/车企财报/比亚迪/2023/比亚迪2023年度报告.pdf",
      "type": "downloadable",
      "sub_type": "pdf",
      "description": "比亚迪股份有限公司2023年度报告（H股，港交所披露），包含公司财务状况、经营成果、现金流量表、股东权益变动表等完整财务信息，以及管理层讨论与分析部分，详细阐述了新能源汽车业务的发展战略和市场前景展望。",
      "search_query": "比亚迪 2023年度报告 site:hkexnews.hk filetype:pdf"
    }},
    ...（共{file_count}个）
  ]
}}
