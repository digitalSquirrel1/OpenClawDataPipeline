用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 {file_count}个 可从公网下载的真实视频文件。
sub_type 可以是 mp4, mkv, avi 等。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/资源文件/视频资源/行业会议/2024新能源汽车论坛主题演讲.mp4",
      "type": "downloadable",
      "sub_type": "mp4",
      "description": "2024新能源汽车行业论坛中关于市场趋势的主题演讲视频，演讲嘉宾详细分析了新能源汽车市场发展现状、未来技术趋势、政策环境变化，以及产业链上下游的投资机会和挑战。",
      "search_query": "2024新能源汽车论坛 市场趋势 演讲视频"
    }},
    ...（共{file_count}个）
  ]
}}
