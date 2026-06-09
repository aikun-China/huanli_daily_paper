# 幻璃次元日报 (Huanli Daily Paper)

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![NoneBot](https://img.shields.io/badge/NoneBot2-2.0%2B-green)](https://nonebot.dev/)

> 二次元每日日报生成系统，支持自动抓取热事、AI分析、多平台部署

## 项目简介

幻璃次元日报是一个面向二次元社群的自动化日报系统，支持：

- 🎨 **每日自动推送** - 定时生成精美日报图片
- 👤 **今日次元人物** - 365+角色库，IP权重随机抽取
- 📰 **圈内大事件** - 自动抓取B站/微博热搜，DeepSeek AI分析
- 📅 **智能倒计时** - 周末、假期、漫展等自动计算
- 💡 **冷知识** - 每日一条二次元冷知识
- 🗳️ **互动投票** - 群友参与投票，次日公布结果
- ⚙️ **多群独立配置** - 每个群的内容、风格、时间可自定义

## 版本说明

| 版本 | 路径 | 说明 | 状态 |
|------|------|------|------|
| **真寻Bot插件** | `zhenxun_bot/` | 基于真寻Bot/Nonebot2的QQ群插件 | ✅ 可用 |
| 独立运行版 | `standalone/` | 命令行生成日报，不依赖Bot框架 | 🚧 开发中 |
| 网页版 | `web/` | Web管理后台 + API服务 | 📋 规划中 |

## 快速开始

### 真寻Bot插件版

```bash
# 1. 克隆仓库
git clone https://github.com/aikun-China/huanli_daily_paper.git

# 2. 复制到真寻Bot插件目录
cp -r huanli_daily_paper/zhenxun_bot /path/to/zhenxun_bot/plugins/daily_paper

# 3. 安装依赖
pip install aiohttp

# 4. 配置DeepSeek API（可选，用于热事分析）
# 在群里发送：设置热事API sk-xxxxxxxx

# 5. 重启Bot
```

### 角色批量导入

```bash
cd zhenxun_bot

# 准备CSV文件（参考 characters_sample.csv）
# 然后执行：
python batch_import.py --input your_characters.csv

# 试运行（不写入）
python batch_import.py --input your_characters.csv --dry-run
```

## 命令列表

| 命令 | 权限 | 说明 |
|------|------|------|
| `日报` | 所有人 | 手动触发日报 |
| `今日角色` | 所有人 | 预览今日角色 |
| `投票 A/B/C/D` | 所有人 | 参与投票 |
| `更新热事` | 超级用户 | 手动抓取热事 |
| `设置热事API [key]` | 超级用户 | 设置DeepSeek API |
| `日报设置` | 超级用户 | 查看/修改群配置 |

## 项目结构

```
huanli_daily_paper/
├── zhenxun_bot/              # 真寻Bot插件版
│   ├── __init__.py           # 插件主入口
│   ├── hot_fetcher.py        # 热事抓取 + DeepSeek分析
│   ├── batch_import.py       # 角色批量导入
│   ├── data/                 # 数据文件
│   │   ├── characters/       # 角色库（按IP分文件夹）
│   │   ├── events/           # 大事件题库
│   │   ├── holidays/         # 节日数据
│   │   ├── trivia/           # 冷知识
│   │   ├── votes/            # 投票题库
│   │   └── ip_index.json     # IP索引
│   ├── assets/               # 素材文件
│   │   ├── characters/       # 角色立绘
│   │   ├── themes/           # 底图主题
│   │   └── fonts/            # 字体
│   └── README.md
│
├── standalone/               # 独立运行版（开发中）
├── tools/                    # 通用工具
├── docs/                     # 文档
├── .gitignore
└── README.md
```

## 数据格式

### 角色JSON

```json
{
  "ip": "genshin",
  "local_id": "001",
  "global_id": "genshin_001",
  "name": "可莉",
  "name_en": "Klee",
  "work": "原神",
  "tags": ["火系", "蒙德", "萝莉", "爆破"],
  "quote": "哒哒哒！",
  "description": "西风骑士团的火花骑士",
  "image_file": "001.png"
}
```

### CSV导入格式

```csv
ip,name,name_en,work,tags,quote,description
genshin,可莉,Klee,原神,"火系,蒙德,萝莉",哒哒哒！,西风骑士团的火花骑士
```

## 配置说明

群配置存储在真寻Bot数据目录：`data/daily_paper/groups/{群号}.json`

```json
{
  "enabled": true,
  "send_time": {"hour": 8, "minute": 0},
  "theme": "default",
  "character_pool": {
    "mode": "weighted",
    "weights": {
      "genshin": 5,
      "starrail": 3,
      "bangumi": 2
    }
  },
  "event_sources": ["genshin", "bangumi", "vtb"],
  "history_days": 30
}
```

## 热事自动更新流程

```
每天 7:30
  │
  ├── 抓取B站热搜 / 微博热搜
  ├── 过滤二次元关键词
  ├── 发送Top10给DeepSeek API分析
  ├── 返回结构化事件 {"title", "summary", "tags"}
  └── 保存到对应events文件

每天 8:00（按群配置）
  │
  ├── 读取群配置
  ├── 抽取角色 / 事件 / 冷知识 / 投票
  ├── 渲染日报图片
  └── 发送到QQ群
```

## 贡献指南

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/xxx`
3. 提交更改：`git commit -am 'Add xxx'`
4. 推送分支：`git push origin feature/xxx`
5. 提交 Pull Request

## 许可证

[MIT](LICENSE)

## 致谢

- [真寻Bot](https://github.com/zhenxun-org/zhenxun_bot) - 优秀的QQ机器人框架
- [NoneBot2](https://nonebot.dev/) - 跨平台Python异步机器人框架
- [DeepSeek](https://deepseek.com/) - AI大模型服务
