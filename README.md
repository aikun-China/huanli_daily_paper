# 幻璃次元日报 (zhenxun_daily_paper)

基于真寻Bot的二次元每日日报插件，支持自动抓取热事、多群独立配置。

## 功能

- 🎨 每日自动推送日报（定时任务）
- 👤 今日次元人物（365+角色库，IP权重抽取）
- 📰 圈内大事件（自动抓取B站/微博热搜 + DeepSeek分析）
- 📅 智能倒计时（周末/假期/漫展）
- 💡 冷知识
- 🗳️ 互动投票
- ⚙️ 每个群独立配置

## 安装

1. 将 `daily_paper` 文件夹复制到真寻Bot的 `plugins/` 目录
2. 安装依赖：`pip install aiohttp`（如使用热事抓取）
3. 重启Bot

## 命令

| 命令 | 权限 | 说明 |
|------|------|------|
| `日报` | 所有人 | 手动触发日报 |
| `今日角色` | 所有人 | 预览今日角色 |
| `更新热事` | 超级用户 | 手动抓取热事 |
| `设置热事API [key]` | 超级用户 | 设置DeepSeek API Key |
| `日报设置` | 超级用户 | 查看/修改群配置 |
| `投票 [A/B/C/D]` | 所有人 | 参与投票 |

## 配置

群配置存储在 `data/daily_paper/groups/{群号}.json`，继承默认配置。

## 热事自动更新

### 方式1：使用DeepSeek API（推荐）

1. 获取 DeepSeek API Key
2. 发送命令：`设置热事API sk-xxxxxxxx`
3. 每天早上7:30自动抓取分析，8:00发送日报

### 方式2：无API（简化版）

不设置API Key，直接抓取最热的一条作为事件。

## 角色批量导入

```bash
# 准备CSV文件
python batch_import.py --input characters.csv --plugin-dir .

# 试运行
python batch_import.py --input characters.csv --dry-run
```

## 项目结构

```
daily_paper/
├── __init__.py          # 插件主入口
├── hot_fetcher.py       # 热事抓取 + DeepSeek分析
├── batch_import.py      # 角色批量导入
├── data/
│   ├── characters/      # 角色数据
│   ├── events/          # 大事件题库
│   ├── holidays/        # 节日数据
│   ├── trivia/          # 冷知识
│   ├── votes/           # 投票题库
│   └── ip_index.json    # IP索引
└── assets/
    ├── characters/      # 角色立绘
    ├── themes/          # 底图主题
    └── fonts/           # 字体
```

## 定时任务

| 时间 | 任务 |
|------|------|
| 7:30 | 自动抓取热事并分析 |
| 8:00 | 发送日报（按群配置时间） |

## License

MIT
