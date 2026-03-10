用户画像：
{profile_json}

目录结构（可用路径）：
{dirs_json}

请为该用户设计 {file_count}个 可从公网下载的真实图片文件。
sub_type 可以是 jpg, png, jpeg 等。

输出 JSON（只有files数组）：
{{
  "files": [
    {{
      "path": "D/资源文件/产品图片/比亚迪/比亚迪汉EV官方产品图.jpg",
      "type": "downloadable",
      "sub_type": "jpg",
      "description": "比亚迪汉EV新能源汽车官方产品图高清展示，包含车辆外观、内饰设计、配置参数、技术亮点等全方位视觉呈现，帮助用户了解比亚迪旗舰轿车的产品特色和市场定位。",
      "search_query": "比亚迪汉EV 官方产品图 site:byd.com"
    }},
    ...（共{file_count}个）
  ]
}}
