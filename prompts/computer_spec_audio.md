用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 {file_count}个 可从公网下载的真实音频文件。
sub_type 可以是 mp3, wav, m4a 等。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/资源文件/音频资源/播客/新能源行业周报第42期.mp3",
      "type": "downloadable",
      "sub_type": "mp3",
      "description": "新能源汽车行业周报播客第42期：市场动态分析，主持人邀请行业专家深度解读近期新能源汽车销量数据、市场份额变化、新车型发布情况，以及政策利好对行业发展的推动作用。",
      "search_query": "新能源汽车行业周报 播客 第42期"
    }},
    ...（共{file_count}个）
  ]
}}
