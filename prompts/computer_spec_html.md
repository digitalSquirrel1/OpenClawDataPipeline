用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 {file_count}个 可从公网下载保存的HTML网页文件。

请直接输出有效的JSON，标准格式如下（只有files数组）：
{{
  "files": [
    {{
      "path": "D/网页存档/财经新闻/比亚迪2023年销量创历史记录.html",
      "type": "downloadable",
      "sub_type": "html",
      "description": "比亚迪2023年全年销量创历史记录相关新闻页面，报道了比亚迪新能源汽车销量突破300万辆大关，创下中国汽车行业新纪录，详细分析了市场份额增长、产品线扩张以及国际化战略的成功实施情况。",
      "search_query": "比亚迪 2023年销量 302万辆 历史记录"
    }},
    ...（共{file_count}个）
  ]
}}
