"""
@Author: 幻璃次元日报
@Description: 二次元每日日报插件，支持多群独立配置
@Usage: 日报 / 日报设置 / 今日角色
@Version: 1.0.0
"""

import random
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple

from nonebot import on_command, require
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent, 
    MessageSegment, 
    Bot,
    Message
)
from nonebot.permission import SUPERUSER
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

# 真寻bot特有导入
from zhenxun.services.log import logger
from zhenxun.utils._build_image import BuildImage
from zhenxun.utils._image_template import ImageTemplate
from zhenxun.configs.config import BotConfig
from zhenxun.configs.path_config import DATA_PATH, IMAGE_PATH

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="幻璃次元日报",
    description="二次元每日日报插件，包含角色、大事件、倒计时、投票等",
    usage="日报 / 日报设置 / 今日角色 / 日报预览",
    extra={
        "author": "幻璃次元",
        "version": "1.0.0",
        "priority": 5,
        "cd": 0,
    },
)

# ========== 路径配置 ==========

PLUGIN_DIR = Path(__file__).parent
DATA_DIR = PLUGIN_DIR / "data"
ASSETS_DIR = PLUGIN_DIR / "assets"
THEMES_DIR = ASSETS_DIR / "themes"
FONTS_DIR = ASSETS_DIR / "fonts"
CHARACTERS_DIR = DATA_DIR / "characters"
EVENTS_DIR = DATA_DIR / "events"
HOLIDAYS_DIR = DATA_DIR / "holidays"
TRIVIA_DIR = DATA_DIR / "trivia"
VOTES_DIR = DATA_DIR / "votes"

# 群配置存储路径（使用真寻bot的DATA_PATH）
GROUP_CONFIG_DIR = DATA_PATH / "daily_paper" / "groups"
GROUP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# 历史记录路径
HISTORY_DIR = DATA_PATH / "daily_paper" / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

VOTE_RESULTS_DIR = DATA_PATH / "daily_paper" / "vote_results"
VOTE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ========== 默认配置 ==========

DEFAULT_CONFIG = {
    "enabled": True,
    "send_time": {"hour": 8, "minute": 0},
    "theme": "default",
    "character_pool": {
        "mode": "weighted",
        "weights": {
            "genshin": 5,
            "starrail": 3,
            "bangumi": 2,
            "vocaloid": 2,
            "honkai": 2
        }
    },
    "event_sources": ["genshin", "bangumi", "vtb"],
    "trivia_types": ["anime", "game", "mixed"],
    "vote_types": ["daily", "acg"],
    "custom_events": [
        {"name": "暑假", "date": "2026-07-01"},
        {"name": "泌阳幻璃漫展", "date": "2026-08-04"}
    ],
    "history_days": 30,
    "language": "zh-CN"
}

# ========== 配置加载 ==========

def load_group_config(group_id: str) -> Dict:
    """加载群配置（继承默认）"""
    config = DEFAULT_CONFIG.copy()
    config_file = GROUP_CONFIG_DIR / f"{group_id}.json"

    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                override = json.load(f)
            # 递归合并
            _deep_merge(config, override)
        except Exception as e:
            logger.error(f"加载群配置失败 {group_id}: {e}")

    config["group_id"] = group_id
    return config


def save_group_config(group_id: str, config: Dict):
    """保存群配置"""
    config_file = GROUP_CONFIG_DIR / f"{group_id}.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _deep_merge(base: Dict, override: Dict):
    """递归合并字典"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


# ========== 数据管理类 ==========

class CharacterPicker:
    """角色抽取器"""

    def __init__(self, config: Dict):
        self.config = config
        self.group_id = config.get("group_id", "default")
        self.history_days = config.get("history_days", 30)
        self.pool_config = config.get("character_pool", {})

    def pick(self) -> Optional[Dict]:
        """抽取角色"""
        # 1. 获取候选IP
        ip_list = self._get_candidate_ips()
        if not ip_list:
            return None

        # 2. 加权随机选IP
        selected_ip = self._weighted_random_ip(ip_list)

        # 3. 加载该IP角色
        characters = self._load_ip_characters(selected_ip)
        if not characters:
            return None

        # 4. 排除历史
        history = self._load_history()
        filtered = [c for c in characters if c.get("global_id") not in history]

        if not filtered:
            filtered = characters
            self._clear_history()

        # 5. 随机抽取
        selected = random.choice(filtered)
        self._record_history(selected.get("global_id", ""))

        return selected

    def _get_candidate_ips(self) -> List[Dict]:
        """获取候选IP列表"""
        ip_index_file = DATA_DIR / "ip_index.json"
        if not ip_index_file.exists():
            return []

        with open(ip_index_file, "r", encoding="utf-8") as f:
            ip_index = json.load(f)

        all_ips = ip_index.get("ips", [])
        mode = self.pool_config.get("mode", "weighted")

        if mode == "whitelist":
            whitelist = self.pool_config.get("whitelist", [])
            return [ip for ip in all_ips if ip["id"] in whitelist]
        elif mode == "blacklist":
            blacklist = self.pool_config.get("blacklist", [])
            return [ip for ip in all_ips if ip["id"] not in blacklist]
        else:
            return all_ips

    def _weighted_random_ip(self, ip_list: List[Dict]) -> str:
        """加权随机选择IP"""
        weights = self.pool_config.get("weights", {})
        weight_list = []
        for ip in ip_list:
            w = weights.get(ip["id"], ip.get("default_weight", 1))
            weight_list.append(w)

        selected = random.choices(ip_list, weights=weight_list, k=1)[0]
        return selected["folder"]

    def _load_ip_characters(self, ip_folder: str) -> List[Dict]:
        """加载IP下所有角色"""
        ip_path = CHARACTERS_DIR / ip_folder
        if not ip_path.exists():
            return []

        characters = []
        for json_file in sorted(ip_path.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    characters.append(json.load(f))
            except Exception as e:
                logger.warning(f"读取角色文件失败 {json_file}: {e}")

        return characters

    def _load_history(self) -> set:
        """加载抽取历史"""
        history_file = HISTORY_DIR / f"{self.group_id}.json"
        if not history_file.exists():
            return set()

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            cutoff = (datetime.now() - timedelta(days=self.history_days)).isoformat()
            history = set()
            for record in data:
                if record.get("date", "") > cutoff:
                    history.add(record.get("global_id", ""))
            return history
        except Exception:
            return set()

    def _record_history(self, global_id: str):
        """记录抽取历史"""
        history_file = HISTORY_DIR / f"{self.group_id}.json"
        data = []

        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        data.append({
            "global_id": global_id,
            "date": datetime.now().isoformat()
        })

        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _clear_history(self):
        """清空历史"""
        history_file = HISTORY_DIR / f"{self.group_id}.json"
        if history_file.exists():
            history_file.unlink()


class EventPicker:
    """大事件抽取器"""

    def __init__(self, config: Dict):
        self.sources = config.get("event_sources", ["genshin", "bangumi", "vtb"])

    def pick(self) -> Optional[Dict]:
        """抽取大事件"""
        all_events = []

        for source in self.sources:
            source_file = EVENTS_DIR / f"{source}.json"
            if source_file.exists():
                try:
                    with open(source_file, "r", encoding="utf-8") as f:
                        events = json.load(f)
                        all_events.extend(events)
                except Exception as e:
                    logger.warning(f"读取事件文件失败 {source_file}: {e}")

        if not all_events:
            return None

        return random.choice(all_events)


class HolidayChecker:
    """节日查询器"""

    def __init__(self):
        self.holidays = self._load_all()

    def check_today(self) -> Optional[Dict]:
        """检查今天是否是节日"""
        today_str = datetime.now().strftime("%m-%d")

        for h_type, holidays in self.holidays.items():
            for h in holidays:
                if h.get("date") == today_str:
                    return {**h, "type": h_type}

        return None

    def get_upcoming(self, days: int = 30) -> List[Dict]:
        """获取未来节日"""
        today = datetime.now()
        upcoming = []

        for h_type, holidays in self.holidays.items():
            for h in holidays:
                try:
                    h_date = datetime.strptime(f"{today.year}-{h['date']}", "%Y-%m-%d")
                    delta = (h_date - today).days
                    if 0 <= delta <= days:
                        upcoming.append({**h, "type": h_type, "days_until": delta})
                except Exception:
                    continue

        return sorted(upcoming, key=lambda x: x.get("days_until", 999))

    def _load_all(self) -> Dict:
        """加载所有节日"""
        holidays = {}
        for json_file in HOLIDAYS_DIR.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    holidays[json_file.stem] = json.load(f)
            except Exception as e:
                logger.warning(f"读取节日文件失败 {json_file}: {e}")
        return holidays


class CountdownCalculator:
    """倒计时计算器"""

    def __init__(self, config: Dict):
        self.custom_events = config.get("custom_events", [])

    def calculate(self) -> List[Dict]:
        """计算倒计时"""
        countdowns = []
        today = datetime.now()

        # 周末
        weekend_days = self._days_to_weekend(today)
        countdowns.append({
            "name": "周末",
            "days": weekend_days,
            "highlight": weekend_days <= 2
        })

        # 自定义事件
        for event in self.custom_events:
            try:
                event_date = datetime.strptime(event["date"], "%Y-%m-%d")
                days = (event_date - today).days
                if days >= 0:
                    countdowns.append({
                        "name": event["name"],
                        "days": days,
                        "highlight": days <= 7
                    })
            except Exception:
                continue

        # 下一个节日
        holiday_checker = HolidayChecker()
        upcoming = holiday_checker.get_upcoming(days=60)
        if upcoming:
            next_holiday = upcoming[0]
            countdowns.append({
                "name": next_holiday["name"],
                "days": next_holiday["days_until"],
                "highlight": next_holiday["days_until"] <= 3
            })

        return countdowns[:4]  # 最多4个

    def _days_to_weekend(self, today: datetime) -> int:
        weekday = today.weekday()
        if weekday >= 5:
            return 0
        return 5 - weekday


class TriviaPicker:
    """冷知识抽取器"""

    def __init__(self, config: Dict):
        self.types = config.get("trivia_types", ["anime", "game", "mixed"])

    def pick(self) -> Optional[Dict]:
        all_trivia = []

        for t_type in self.types:
            file_path = TRIVIA_DIR / f"{t_type}.json"
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        all_trivia.extend(json.load(f))
                except Exception:
                    pass

        if not all_trivia:
            return None

        return random.choice(all_trivia)


class VoteManager:
    """投票管理器"""

    def __init__(self, config: Dict):
        self.group_id = config.get("group_id", "default")
        self.vote_types = config.get("vote_types", ["daily", "acg"])

    def pick_question(self) -> Optional[Dict]:
        all_questions = []

        for v_type in self.vote_types:
            file_path = VOTES_DIR / f"{v_type}.json"
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        all_questions.extend(json.load(f))
                except Exception:
                    pass

        if not all_questions:
            return None

        return random.choice(all_questions)

    def record_vote(self, question_id: str, option: str, user_id: str) -> bool:
        """记录投票"""
        result_file = VOTE_RESULTS_DIR / f"{self.group_id}_{datetime.now().strftime('%Y-%m-%d')}.json"

        data = {}
        if result_file.exists():
            try:
                with open(result_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        if question_id not in data:
            data[question_id] = {"options": {}, "voters": []}

        if user_id in data[question_id]["voters"]:
            return False

        data[question_id]["options"][option] = data[question_id]["options"].get(option, 0) + 1
        data[question_id]["voters"].append(user_id)

        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return True


# ========== 日报渲染 ==========

class DailyRenderer:
    """日报渲染器（使用真寻BuildImage）"""

    WIDTH = 900
    HEIGHT = 1400

    COLORS = {
        "bg": (240, 244, 248),
        "primary": (74, 144, 217),
        "accent": (255, 107, 157),
        "text_dark": (45, 55, 72),
        "text_light": (113, 128, 150),
        "card_bg": (255, 255, 255),
        "border": (226, 232, 240),
        "weekend": (74, 144, 217),
        "holiday": (72, 187, 120),
        "summer": (237, 137, 54),
        "event": (159, 122, 234)
    }

    def __init__(self, config: Dict):
        self.config = config
        self.theme = config.get("theme", "default")
        self.theme_dir = THEMES_DIR / self.theme

    async def render(self, data: Dict) -> str:
        """渲染日报并返回图片路径"""
        # 使用真寻的BuildImage
        img = BuildImage(self.WIDTH, self.HEIGHT, color=self.COLORS["bg"])

        # 加载底图
        bg_path = self.theme_dir / "bg.png"
        if bg_path.exists():
            bg = BuildImage(0, 0, background=str(bg_path))
            bg.resize(self.WIDTH, self.HEIGHT)
            img.paste(bg, (0, 0))

        y = 20

        # 1. 标题区
        y = await self._draw_header(img, data, y)

        # 2. 倒计时
        y = await self._draw_countdowns(img, data.get("countdowns", []), y)

        # 3. 大事件
        y = await self._draw_event(img, data.get("event"), y)

        # 4. 今日角色
        y = await self._draw_character(img, data.get("character"), y)

        # 5. 冷知识
        y = await self._draw_trivia(img, data.get("trivia"), y)

        # 6. 投票
        y = await self._draw_vote(img, data.get("vote"), y)

        # 7. 底部
        await self._draw_footer(img, y)

        # 保存
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_dir = DATA_PATH / "daily_paper" / "output" / date_str
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f"{data.get('group_id', 'default')}.png"
        img.save(str(output_path))

        return str(output_path)

    async def _draw_header(self, img: BuildImage, data: Dict, y: int) -> int:
        """绘制标题"""
        # 日期
        img.text((30, y), data.get("date", ""), fill=self.COLORS["text_light"], fontsize=18)
        y += 30

        # 主标题
        title = "幻璃次元日报"
        img.text((self.WIDTH // 2, y), title, fill=self.COLORS["primary"], 
                fontsize=48, center_type="center")
        y += 60

        # 副标题
        subtitle = data.get("title", "")
        if subtitle:
            img.text((self.WIDTH // 2, y), subtitle, fill=self.COLORS["text_dark"],
                    fontsize=24, center_type="center")
            y += 40

        return y + 10

    async def _draw_countdowns(self, img: BuildImage, countdowns: List[Dict], y: int) -> int:
        """绘制倒计时卡片"""
        if not countdowns:
            return y

        card_h = 120
        card_w = (self.WIDTH - 60) // min(len(countdowns), 4) - 10

        for i, cd in enumerate(countdowns[:4]):
            x = 30 + i * (card_w + 10)

            # 卡片背景
            card = BuildImage(card_w, card_h, color=self.COLORS["card_bg"], 
                            font_size=18)
            card.circle_corner(12)

            # 名称
            card.text((card_w // 2, 20), cd.get("name", ""), 
                     fill=self.COLORS["text_light"], fontsize=16, center_type="center")

            # 天数
            color = self.COLORS["event"]
            if cd.get("name") == "周末":
                color = self.COLORS["weekend"]
            elif "暑假" in cd.get("name", ""):
                color = self.COLORS["summer"]

            card.text((card_w // 2, 60), str(cd.get("days", 0)), 
                     fill=color, fontsize=48, center_type="center")

            card.text((card_w // 2, 95), "天", 
                     fill=self.COLORS["text_light"], fontsize=16, center_type="center")

            img.paste(card, (x, y))

        return y + card_h + 20

    async def _draw_event(self, img: BuildImage, event: Optional[Dict], y: int) -> int:
        """绘制大事件"""
        if not event:
            return y

        card_h = 180
        card = BuildImage(self.WIDTH - 60, card_h, color=self.COLORS["card_bg"])
        card.circle_corner(12)

        # NEW标签
        tag = BuildImage(50, 25, color=self.COLORS["accent"])
        tag.circle_corner(4)
        tag.text((25, 12), "NEW", fill=(255, 255, 255), fontsize=14, center_type="center")
        card.paste(tag, (10, 10))

        # 标题
        card.text((10, 45), event.get("title", ""), 
                 fill=self.COLORS["text_dark"], fontsize=20)

        # 摘要
        summary = event.get("summary", "")
        if len(summary) > 50:
            summary = summary[:50] + "..."
        card.text((10, 80), summary, fill=self.COLORS["text_light"], fontsize=16)

        img.paste(card, (30, y))
        return y + card_h + 20

    async def _draw_character(self, img: BuildImage, character: Optional[Dict], y: int) -> int:
        """绘制今日角色"""
        if not character:
            return y

        card_h = 260
        card = BuildImage(self.WIDTH - 60, card_h, color=self.COLORS["card_bg"])
        card.circle_corner(12)

        # 角色名
        card.text((10, 15), character.get("name", ""), 
                 fill=self.COLORS["primary"], fontsize=28)
        card.text((10, 50), f"《{character.get('work', '')}》", 
                 fill=self.COLORS["text_light"], fontsize=16)

        # 标签
        tags = character.get("tags", [])[:3]
        tag_x = 10
        for tag in tags:
            tag_w = len(tag) * 16 + 20
            tag_img = BuildImage(tag_w, 25, color=self.COLORS["primary"])
            tag_img.circle_corner(4)
            tag_img.text((tag_w // 2, 12), tag, fill=(255, 255, 255), 
                        fontsize=12, center_type="center")
            card.paste(tag_img, (tag_x, 80))
            tag_x += tag_w + 8

        # 台词
        quote = character.get("quote", "")
        card.text((10, 120), f'"{quote}"', 
                 fill=self.COLORS["accent"], fontsize=18)

        # 描述
        desc = character.get("description", "")
        if len(desc) > 40:
            desc = desc[:40] + "..."
        card.text((10, 155), desc, fill=self.COLORS["text_light"], fontsize=14)

        # 角色立绘（右侧）
        char_img_path = ASSETS_DIR / "characters" / character.get("ip", "") / character.get("image_file", "")
        if char_img_path.exists():
            try:
                char_img = BuildImage(0, 0, background=str(char_img_path))
                char_img.resize(150, 200)
                card.paste(char_img, (card.w - 170, 30))
            except Exception:
                pass

        img.paste(card, (30, y))
        return y + card_h + 20

    async def _draw_trivia(self, img: BuildImage, trivia: Optional[Dict], y: int) -> int:
        """绘制冷知识"""
        if not trivia:
            return y

        card_h = 80
        card = BuildImage(self.WIDTH - 60, card_h, color=self.COLORS["card_bg"])
        card.circle_corner(12)

        card.text((10, 10), "💡 一句话冷知识", 
                 fill=self.COLORS["primary"], fontsize=14)

        content = trivia.get("content", "")
        if len(content) > 50:
            content = content[:50] + "..."
        card.text((10, 35), content, fill=self.COLORS["text_dark"], fontsize=16)

        img.paste(card, (30, y))
        return y + card_h + 20

    async def _draw_vote(self, img: BuildImage, vote: Optional[Dict], y: int) -> int:
        """绘制投票"""
        if not vote:
            return y

        card_h = 160
        card = BuildImage(self.WIDTH - 60, card_h, color=self.COLORS["card_bg"])
        card.circle_corner(12)

        card.text((10, 10), "💬 今日互动", 
                 fill=self.COLORS["primary"], fontsize=14)

        card.text((10, 35), vote.get("question", ""), 
                 fill=self.COLORS["text_dark"], fontsize=18)

        # 选项按钮
        options = vote.get("options", {})
        colors = [(255, 107, 107), (78, 205, 196), (69, 183, 209), (150, 206, 180)]
        btn_w = (self.WIDTH - 100) // len(options) - 10 if options else 100

        x = 10
        for i, (key, text) in enumerate(options.items()):
            color = colors[i % len(colors)]
            btn = BuildImage(btn_w, 35, color=color)
            btn.circle_corner(8)
            btn.text((btn_w // 2, 17), f"{key} {text}", 
                    fill=(255, 255, 255), fontsize=14, center_type="center")
            card.paste(btn, (x, 80))
            x += btn_w + 10

        card.text((10, 125), "回复选项参与投票，明日公布结果！", 
                 fill=self.COLORS["text_light"], fontsize=14)

        img.paste(card, (30, y))
        return y + card_h + 20

    async def _draw_footer(self, img: BuildImage, y: int):
        """绘制底部"""
        img.text((self.WIDTH // 2, self.HEIGHT - 30), 
                "幻璃次元日报 | 每日更新",
                fill=self.COLORS["text_light"], fontsize=14, center_type="center")


# ========== 日报生成核心 ==========

async def generate_daily(group_id: str) -> Tuple[str, Dict]:
    """
    生成日报

    Returns:
        (图片路径, 日报数据)
    """
    config = load_group_config(group_id)

    if not config.get("enabled", False):
        raise Exception("本群日报未启用")

    # 1. 抽取角色
    picker = CharacterPicker(config)
    character = picker.pick()

    # 2. 抽取事件
    event_picker = EventPicker(config)
    event = event_picker.pick()

    # 3. 检查节日
    holiday_checker = HolidayChecker()
    holiday = holiday_checker.check_today()

    # 4. 倒计时
    countdown_calc = CountdownCalculator(config)
    countdowns = countdown_calc.calculate()

    # 5. 冷知识
    trivia_picker = TriviaPicker(config)
    trivia = trivia_picker.pick()

    # 6. 投票
    vote_manager = VoteManager(config)
    vote = vote_manager.pick_question()

    # 7. 组装数据
    now = datetime.now()
    daily_data = {
        "date": now.strftime("%Y.%m.%d"),
        "weekday": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()],
        "issue": f"{(now - datetime(2026, 6, 9)).days + 1:03d}",
        "group_id": group_id,
        "title": holiday["name"] + "快乐！" if holiday else "泌阳同好集合！一起奔赴幻璃次元现场！",
        "character": character,
        "event": event,
        "holiday": holiday,
        "countdowns": countdowns,
        "trivia": trivia,
        "vote": vote
    }

    # 8. 渲染
    renderer = DailyRenderer(config)
    image_path = await renderer.render(daily_data)

    return image_path, daily_data


# ========== 命令注册 ==========

# 手动触发日报
daily_cmd = on_command("日报", aliases={"daily", "今日日报"}, priority=5, block=True)

@daily_cmd.handle()
async def handle_daily(event: GroupMessageEvent):
    """手动触发日报"""
    group_id = str(event.group_id)

    try:
        image_path, data = await generate_daily(group_id)
        await daily_cmd.send(MessageSegment.image(f"file://{image_path}"))

        # 发送投票引导
        if data.get("vote"):
            vote = data["vote"]
            options = " | ".join([f"{k}.{v}" for k, v in vote.get("options", {}).items()])
            await daily_cmd.send(f"📊 今日投票：{vote.get('question', '')}\n回复选项参与：{options}")

    except Exception as e:
        logger.error(f"生成日报失败: {e}")
        await daily_cmd.send(f"日报生成失败: {str(e)}")


# 预览今日角色（不发送完整日报）
character_cmd = on_command("今日角色", aliases={"角色预览"}, priority=5, block=True)

@character_cmd.handle()
async def handle_character(event: GroupMessageEvent):
    """预览今日角色"""
    group_id = str(event.group_id)
    config = load_group_config(group_id)

    picker = CharacterPicker(config)
    character = picker.pick()

    if not character:
        await character_cmd.send("暂无可用角色")
        return

    msg = f"🎭 今日角色预览\n"
    msg += f"【{character['name']}】"
    if character.get("name_en"):
        msg += f" ({character['name_en']})"
    msg += f"\n"
    msg += f"出自：{character['work']}\n"
    msg += f"标签：{', '.join(character.get('tags', []))}\n"
    msg += f"台词：{character.get('quote', '')}"

    await character_cmd.send(msg)


# 日报设置（管理员）
config_cmd = on_command("日报设置", permission=SUPERUSER, priority=5, block=True)

@config_cmd.handle()
async def handle_config(event: GroupMessageEvent, args: Message = CommandArg()):
    """查看/修改群配置"""
    group_id = str(event.group_id)
    config = load_group_config(group_id)

    arg_text = args.extract_plain_text().strip()

    if not arg_text:
        # 显示当前配置
        msg = f"📋 群 {group_id} 日报配置\n"
        msg += f"启用：{'✅' if config.get('enabled') else '❌'}\n"
        msg += f"发送时间：{config['send_time']['hour']:02d}:{config['send_time']['minute']:02d}\n"
        msg += f"主题：{config.get('theme', 'default')}\n"
        msg += f"历史天数：{config.get('history_days', 30)}\n"
        msg += f"\n修改命令：日报设置 [key] [value]"
        await config_cmd.send(msg)
        return

    # 解析设置命令
    parts = arg_text.split(maxsplit=1)
    if len(parts) < 2:
        await config_cmd.send("格式错误。示例：日报设置 enabled false")
        return

    key, value = parts[0], parts[1]

    # 简单配置修改
    if key == "enabled":
        config["enabled"] = value.lower() in ("true", "1", "yes", "on")
    elif key == "time":
        try:
            h, m = map(int, value.split(":"))
            config["send_time"] = {"hour": h, "minute": m}
        except Exception:
            await config_cmd.send("时间格式错误，示例：日报设置 time 8:00")
            return
    elif key == "theme":
        config["theme"] = value
    else:
        await config_cmd.send(f"未知配置项: {key}")
        return

    save_group_config(group_id, config)
    await config_cmd.send(f"✅ 配置已更新：{key} = {value}")


# 投票处理
vote_pattern = on_command("投票", priority=5, block=True)

@vote_pattern.handle()
async def handle_vote(event: GroupMessageEvent, args: Message = CommandArg()):
    """处理投票"""
    group_id = str(event.group_id)
    user_id = str(event.user_id)

    option = args.extract_plain_text().strip().upper()

    if not option or option not in "ABCD":
        await vote_pattern.send("请回复投票选项，如：投票 A")
        return

    config = load_group_config(group_id)
    vote_manager = VoteManager(config)

    # 获取今日投票题目ID（简化处理，实际应从记录中读取）
    # 这里简化处理，假设当前投票题目
    question_id = f"vote_{datetime.now().strftime('%Y%m%d')}"

    success = vote_manager.record_vote(question_id, option, user_id)

    if success:
        await vote_pattern.send(f"✅ 投票成功！你选择了 {option}")
    else:
        await vote_pattern.send("⚠️ 你今天已经投过票了")


# ========== 定时任务 ==========

@scheduler.scheduled_job("cron", hour=8, minute=0, id="daily_paper_morning")
async def scheduled_daily():
    """每天早上8点发送日报"""
    # 遍历所有群配置
    for config_file in GROUP_CONFIG_DIR.glob("*.json"):
        group_id = config_file.stem
        config = load_group_config(group_id)

        if not config.get("enabled", False):
            continue

        # 检查发送时间
        send_time = config.get("send_time", {"hour": 8, "minute": 0})
        now = datetime.now()
        if now.hour != send_time["hour"] or now.minute != send_time["minute"]:
            continue

        try:
            image_path, data = await generate_daily(group_id)

            # 获取bot实例发送消息
            # 注意：这里需要适配真寻bot的消息发送方式
            # 简化处理，实际需通过bot.send_group_msg
            logger.info(f"日报已生成: {group_id}")

        except Exception as e:
            logger.error(f"定时发送日报失败 {group_id}: {e}")




# ========== 热事自动更新集成 ==========

from .hot_fetcher import AutoEventUpdater, auto_update_events

# 从环境变量或配置文件读取API Key
DEEPSEEK_API_KEY = ""

async def scheduled_update_events():
    """定时更新热事"""
    try:
        plugin_dir = Path(__file__).parent
        success = await auto_update_events(plugin_dir, DEEPSEEK_API_KEY)
        if success:
            logger.info("热事自动更新成功")
        else:
            logger.warning("热事自动更新失败或无新内容")
    except Exception as e:
        logger.error(f"热事更新异常: {e}")

# 注册定时任务：每天早上7:30更新热事（日报发送前）
@scheduler.scheduled_job("cron", hour=7, minute=30, id="daily_paper_update_events")
async def _scheduled_update_events():
    await scheduled_update_events()


logger.info("幻璃次元日报插件已加载（含热事自动更新）")


# 手动更新热事（管理员）
update_events_cmd = on_command("更新热事", aliases={"刷新热事", "抓取热事"}, permission=SUPERUSER, priority=5, block=True)

@update_events_cmd.handle()
async def handle_update_events(event: GroupMessageEvent):
    """手动触发热事更新"""
    await update_events_cmd.send("🔄 正在抓取二次元热事并分析...")

    try:
        plugin_dir = Path(__file__).parent
        success = await auto_update_events(plugin_dir, DEEPSEEK_API_KEY)

        if success:
            await update_events_cmd.send("✅ 热事更新成功！明天日报将使用新内容。")
        else:
            await update_events_cmd.send("⚠️ 未获取到新热事，可能API限制或暂无热门事件。")

    except Exception as e:
        logger.error(f"手动更新热事失败: {e}")
        await update_events_cmd.send(f"❌ 更新失败: {str(e)}")


# 设置DeepSeek API Key（超级用户）
set_api_cmd = on_command("设置热事API", permission=SUPERUSER, priority=5, block=True)

@set_api_cmd.handle()
async def handle_set_api(event: GroupMessageEvent, args: Message = CommandArg()):
    """设置DeepSeek API Key"""
    global DEEPSEEK_API_KEY

    api_key = args.extract_plain_text().strip()
    if not api_key:
        await set_api_cmd.send("请输入API Key。示例：设置热事API sk-xxxxxxxx")
        return

    DEEPSEEK_API_KEY = api_key

    # 保存到配置文件
    config_file = DATA_PATH / "daily_paper" / "api_config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump({"deepseek_api_key": api_key}, f)

    await set_api_cmd.send("✅ DeepSeek API Key 已设置并保存！")


# 加载保存的API Key
def _load_api_key():
    """启动时加载API Key"""
    global DEEPSEEK_API_KEY
    config_file = DATA_PATH / "daily_paper" / "api_config.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                DEEPSEEK_API_KEY = config.get("deepseek_api_key", "")
                if DEEPSEEK_API_KEY:
                    logger.info("已加载DeepSeek API Key")
        except Exception:
            pass

# 启动时加载
_load_api_key()

