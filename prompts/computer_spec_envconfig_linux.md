为以下用户生成详细的 Linux（Ubuntu）电脑环境配置 JSON。

用户信息：
* 姓名：{name}

* 职业：{role}

* 单位：{company}

* 系统用户名：{username}

* 电脑名：{hostname}

* 核心工具：{tools}


请直接输出有效的JSON，所有字段完整填写，不得省略，标准格式如下：
{{
  "system": {{
    "os": "Ubuntu 22.04.3 LTS",
    "kernel": "6.5.0-44-generic",
    "username": "{username}",
    "display_name": "{name}",
    "hostname": "{hostname}",
    "timezone": "Asia/Shanghai (UTC+8)",
    "language": "zh_CN.UTF-8",
    "install_date": "2023-03-15",
    "last_boot": "2024-11-18 08:47:22",
    "desktop_environment": "GNOME 42.9"
  }},
  "hardware": {{
    "cpu": "Intel Core i7-12700 @ 2.10GHz (12C/20T)",
    "ram_gb": 32,
    "storage": [
      {{"mount": "/", "device": "/dev/nvme0n1p2", "type": "ext4", "size_gb": 512, "free_gb": 178}},
      {{"mount": "/home", "device": "/dev/sda1", "type": "ext4", "size_gb": 2000, "free_gb": 1156}}
    ],
    "display": "2560x1440 @60Hz Dell 27英寸 IPS",
    "gpu": "NVIDIA GeForce RTX 3060 12GB",
    "network_adapters": ["Intel Wi-Fi 6 AX201", "Realtek PCIe GbE Family Controller"]
  }},
  "installed_software": [
    至少20个软件，每个包含name/version/install_date/category/publisher字段（使用Linux常见软件和包管理器安装的软件）
  ],
  "browser": {{
    "default": "Google Chrome",
    "version": "120.0.6099.130",
    "bookmarks": [至少20个书签],
    "extensions": ["至少5个插件"],
    "history_summary": "最近访问的网站类别统计"
  }},
  "recent_files": [最近打开的10个文件路径，使用~/开头的Linux路径格式],
  "desktop_shortcuts": [至少12个桌面快捷方式/应用程序收藏夹],
  "startup_programs": [开机自启程序，至少8个，使用Linux服务名或.desktop文件],
  "scheduled_tasks": [定时任务（crontab），至少3个],
  "network": {{
    "hostname": "{hostname}",
    "ip_address": "192.168.1.105",
    "dns": ["114.114.114.114", "8.8.8.8"],
    "wifi_profiles": ["公司内网", "CHEN-home-5G", "手机热点"],
    "proxy": {{"enabled": true, "host": "proxy.company.com", "port": 8080}}
  }},
  "environment_variables": {{
    "HOME": "/home/{username}",
    "XDG_CONFIG_HOME": "/home/{username}/.config",
    "PYTHON_HOME": "/usr/bin/python3",
    "PATH": "/usr/local/bin:/usr/bin:/bin:/home/{username}/.local/bin",
    "SHELL": "/bin/bash"
  }},
  "system_services": "关键运行服务简要说明（如 nginx、docker、mysql 等）",
  "installed_packages_summary": "通过 apt/snap/pip 安装的关键包分类统计"
}}
