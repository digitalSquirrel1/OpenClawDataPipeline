用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 {file_count}个 可从公网下载的Excel/CSV数据文件。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/数据分析/Wind导出/乘联会2023年月度销量.csv",
      "type": "downloadable",
      "sub_type": "csv",
      "description": "乘联会2023年新能源乘用车月度零售销量数据统计表，包含各月份销量数据、环比同比变化、细分市场占比分析，以及新能源汽车市场渗透率趋势图表，帮助分析行业发展动态和竞争格局。",
      "search_query": "乘联会 新能源汽车 月度销量 2023 filetype:csv"
    }},
    ...（共{file_count}个）
  ]
}}
