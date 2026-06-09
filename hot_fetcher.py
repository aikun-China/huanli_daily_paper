"""
@Author: 幻璃次元日报
@Description: 二次元热事自动抓取器
@Usage: 抓取B站/微博/贴吧热榜，通过DeepSeek API分析生成日报事件
@Version: 1.0.0
"""

import json
import asyncio
import aiohttp
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

from zhenxun.services.log import logger


@dataclass
class HotItem:
    """热事条目"""
    title: str
    url: str
    source: str  # bilibili/weibo/tieba
    hot_score: int
    tags: List[str]
    raw_content: str = ""


class HotFetcher:
    """热事抓取器"""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_all(self, limit: int = 20) -> List[HotItem]:
        """
        抓取所有源的热事

        Args:
            limit: 每个源最多抓取条数

        Returns:
            热事列表
        """
        tasks = [
            self._fetch_bilibili(limit),
            self._fetch_weibo(limit),
            # self._fetch_tieba(limit),  # 如需可添加
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items = []
        for result in results:
            if isinstance(result, list):
                all_items.extend(result)
            else:
                logger.warning(f"抓取失败: {result}")

        # 按热度排序
        all_items.sort(key=lambda x: x.hot_score, reverse=True)
        return all_items

    async def _fetch_bilibili(self, limit: int) -> List[HotItem]:
        """抓取B站热搜"""
        url = "https://api.bilibili.com/x/web-interface/search/square"

        try:
            async with self.session.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://search.bilibili.com/"
            }) as resp:
                data = await resp.json()

                items = []
                for item in data.get("data", {}).get("trending", {}).get("list", [])[:limit]:
                    items.append(HotItem(
                        title=item.get("keyword", ""),
                        url=f"https://search.bilibili.com/all?keyword={item.get('keyword', '')}",
                        source="bilibili",
                        hot_score=item.get("hot_score", 0),
                        tags=["bilibili", "热搜"],
                        raw_content=item.get("show_name", "")
                    ))

                logger.info(f"B站热搜抓取完成: {len(items)} 条")
                return items

        except Exception as e:
            logger.error(f"B站热搜抓取失败: {e}")
            return []

    async def _fetch_weibo(self, limit: int) -> List[HotItem]:
        """抓取微博热搜（简化版，实际可能需要代理或特殊处理）"""
        url = "https://weibo.com/ajax/side/hotSearch"

        try:
            async with self.session.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://weibo.com/hot/search"
            }) as resp:
                data = await resp.json()

                items = []
                for item in data.get("data", {}).get("realtime", [])[:limit]:
                    # 过滤非二次元内容
                    title = item.get("word", "")
                    if not self._is_acg_related(title):
                        continue

                    items.append(HotItem(
                        title=title,
                        url=f"https://s.weibo.com/weibo?q={title}",
                        source="weibo",
                        hot_score=item.get("raw_hot", 0),
                        tags=["weibo", "热搜", "二次元"],
                        raw_content=item.get("note", "")
                    ))

                logger.info(f"微博热搜抓取完成: {len(items)} 条")
                return items

        except Exception as e:
            logger.error(f"微博热搜抓取失败: {e}")
            return []

    def _is_acg_related(self, text: str) -> bool:
        """判断是否与二次元相关"""
        acg_keywords = [
            "原神", "崩坏", "星穹铁道", "明日方舟", "碧蓝航线",
            "初音", "洛天依", "虚拟主播", "VTuber", "动漫",
            "动画", "番剧", "新番", "鬼灭", "间谍过家家",
            "咒术", "海贼王", "火影", "柯南", "EVA",
            "漫展", "COS", "谷子", "手办", "二次元",
            "米哈游", "鹰角", "B站", "哔哩哔哩", "up主"
        ]

        text_lower = text.lower()
        return any(kw in text for kw in acg_keywords)


class DeepSeekAnalyzer:
    """DeepSeek API 分析器"""

    def __init__(self, api_key: str, api_base: str = "https://api.deepseek.com/v1"):
        self.api_key = api_key
        self.api_base = api_base
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def analyze_hot_items(self, items: List[HotItem]) -> Optional[Dict]:
        """
        使用DeepSeek分析热事，生成日报事件

        Args:
            items: 热事列表

        Returns:
            分析后的事件数据 {"title": str, "summary": str, "tags": list}
        """
        if not items:
            return None

        # 构建提示词
        prompt = self._build_prompt(items)

        try:
            async with self.session.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是一个二次元资讯编辑，擅长从热搜中提取最有价值的二次元新闻，用简洁生动的语言撰写日报事件。"
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500
                }
            ) as resp:
                data = await resp.json()

                if "choices" not in data:
                    logger.error(f"DeepSeek API返回错误: {data}")
                    return None

                content = data["choices"][0]["message"]["content"]
                return self._parse_response(content, items)

        except Exception as e:
            logger.error(f"DeepSeek分析失败: {e}")
            return None

    def _build_prompt(self, items: List[HotItem]) -> str:
        """构建提示词"""
        hot_list = []
        for i, item in enumerate(items[:10], 1):
            hot_list.append(f"{i}. [{item.source}] {item.title} (热度: {item.hot_score})")

        prompt = f"""以下是今日二次元相关热搜（按热度排序）：

{"\n".join(hot_list)}

请从中选择最有价值的一条或合并相关几条，撰写一条"二次元圈内大事件"：

要求：
1. 标题不超过30字，吸引眼球
2. 摘要50-80字，概括事件核心
3. 判断事件类型标签（如：原神/番剧/虚拟主播/漫展/通用）
4. 用JSON格式返回：{{"title": "标题", "summary": "摘要", "tags": ["标签1", "标签2"]}}

只返回JSON，不要其他内容。"""

        return prompt

    def _parse_response(self, content: str, items: List[HotItem]) -> Dict:
        """解析DeepSeek返回的JSON"""
        try:
            # 尝试直接解析
            result = json.loads(content)
            return {
                "title": result.get("title", "今日二次元热事"),
                "summary": result.get("summary", ""),
                "tags": result.get("tags", ["二次元", "热事"]),
                "source": "AI生成",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "raw_items": [{"title": i.title, "source": i.source} for i in items[:3]]
            }
        except json.JSONDecodeError:
            # 如果返回的不是纯JSON，尝试提取
            logger.warning("DeepSeek返回非标准JSON，尝试提取")
            return {
                "title": "今日二次元热事",
                "summary": content[:100] + "..." if len(content) > 100 else content,
                "tags": ["二次元", "热事"],
                "source": "AI生成",
                "date": datetime.now().strftime("%Y-%m-%d")
            }


class AutoEventUpdater:
    """自动事件更新器"""

    def __init__(self, plugin_dir: Path, api_key: str = ""):
        self.plugin_dir = plugin_dir
        self.events_dir = plugin_dir / "data" / "events"
        self.api_key = api_key

    async def update(self) -> bool:
        """
        自动抓取并更新事件

        Returns:
            是否成功更新
        """
        logger.info("开始自动抓取二次元热事...")

        # 1. 抓取热事
        async with HotFetcher() as fetcher:
            items = await fetcher.fetch_all(limit=15)

        if not items:
            logger.warning("未抓取到任何热事")
            return False

        logger.info(f"抓取到 {len(items)} 条热事")

        # 2. 使用DeepSeek分析（如果有API Key）
        if self.api_key:
            async with DeepSeekAnalyzer(self.api_key) as analyzer:
                event = await analyzer.analyze_hot_items(items)
        else:
            # 无API时，直接取最热的一条
            top_item = items[0]
            event = {
                "title": top_item.title,
                "summary": f"{top_item.title} 登上{top_item.source}热搜，引发二次元圈热议。",
                "tags": top_item.tags,
                "source": top_item.source,
                "date": datetime.now().strftime("%Y-%m-%d")
            }

        if not event:
            return False

        # 3. 保存到对应事件源文件
        await self._save_event(event)

        logger.info(f"事件已更新: {event.get('title', '')}")
        return True

    async def _save_event(self, event: Dict):
        """保存事件到文件"""
        # 判断事件类型，保存到对应文件
        tags = event.get("tags", [])

        if any(t in ["原神", "崩坏", "星穹铁道", "米哈游"] for t in tags):
            target_file = self.events_dir / "genshin.json"
        elif any(t in ["番剧", "动画", "新番", "鬼灭", "间谍过家家"] for t in tags):
            target_file = self.events_dir / "bangumi.json"
        elif any(t in ["虚拟主播", "VTuber", "up主", "B站"] for t in tags):
            target_file = self.events_dir / "vtb.json"
        else:
            target_file = self.events_dir / "general.json"

        # 读取现有事件
        events = []
        if target_file.exists():
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    events = json.load(f)
            except Exception:
                events = []

        # 添加新事件（限制最多保留20条）
        event["id"] = f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        events.insert(0, event)
        events = events[:20]

        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)


# 便捷函数
async def auto_update_events(plugin_dir: Path, api_key: str = ""):
    """便捷函数：一键更新事件"""
    updater = AutoEventUpdater(plugin_dir, api_key)
    return await updater.update()
