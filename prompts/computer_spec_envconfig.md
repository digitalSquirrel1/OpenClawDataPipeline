为以下用户生成详细的 Windows 10 电脑环境配置 JSON。

用户信息：
• 姓名：{name}

• 职业：{role}

• 单位：{company}

• 系统用户名：{username}

• 电脑名：{hostname}

• 核心工具：{tools}


请生成如下 JSON 结构（所有字段完整填写，不得省略）：
{{
  "system": {{
    "os": "Windows 10 专业版",
    "os_version": "22H2 (19045.3803)",
    "username": "{username}",
    "display_name": "{name}",
    "hostname": "{hostname}",
    "timezone": "China Standard Time (UTC+8)",
    "language": "zh-CN",
    "install_date": "2022-03-10",
    "last_boot": "2024-11-18 08:47:22",
    "product_key_partial": "XXXXX-XXXXX-XXXXX-XXXXX-X7B3K"
  }},
  "hardware": {{
    "cpu": "Intel Core i7-12700 @ 2.10GHz (12C/20T)",
    "ram_gb": 32,
    "storage": [
      {{"drive": "C:", "label": "系统", "type": "NVMe SSD", "size_gb": 512, "free_gb": 178}},
      {{"drive": "D:", "label": "数据", "type": "SATA HDD", "size_gb": 2000, "free_gb": 1156}},
      {{"drive": "E:", "label": "备份", "type": "SATA HDD", "size_gb": 4000, "free_gb": 3210}}
    ],
    "display": "2560x1440 @60Hz Dell 27英寸 IPS",
    "gpu": "NVIDIA GeForce RTX 3060 12GB",
    "network_adapters": ["Intel Wi-Fi 6 AX201", "Realtek PCIe GbE Family Controller"]
  }},
  "installed_software": [
    至少20个软件，每个包含name/version/install_date/category/publisher字段
  ],
  "browser": {{
    "default": "Google Chrome",
    "version": "120.0.6099.130",
    "bookmarks": [至少20个书签],
    "extensions": ["至少5个插件"],
    "history_summary": "最近访问的网站类别统计"
  }},
  "recent_files": [最近打开的10个文件路径],
  "desktop_shortcuts": [至少12个桌面快捷方式],
  "startup_programs": [开机自启程序，至少8个],
  "scheduled_tasks": [定时任务，至少3个],
  "network": {{
    "hostname": "{hostname}",
    "ip_address": "192.168.1.105",
    "dns": ["114.114.114.114", "8.8.8.8"],
    "wifi_profiles": ["公司内网", "CHEN-home-5G", "手机热点"],
    "proxy": {{"enabled": true, "host": "proxy.securities.com", "port": 8080}}
  }},
  "environment_variables": {{
    "USERPROFILE": "C:\\\\Users\\\\{username}",
    "APPDATA": "C:\\\\Users\\\\{username}\\\\AppData\\\\Roaming",
    "PYTHON_HOME": "C:\\\\Python39",
    "WIND_HOME": "C:\\\\Wind\\\\Wind.NET.Client\\\\WindNET"
  }},
  "registry_notes": "已安装的COM组件、字体等简要说明",
  "windows_features": ["已启用的Windows功能列表，至少5个"]
}}
