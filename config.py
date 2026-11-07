# -*- coding: utf-8 -*-
"""配置读取：优先 .env / 环境变量，其次命令行参数覆盖。"""

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv


def parse_sheet_token(url: str) -> str:
    """从飞书表格链接中解析 spreadsheet token。"""
    if not url:
        return ""
    m = re.search(r"/(?:sheets|spreadsheets)/([A-Za-z0-9]+)", url)
    return m.group(1) if m else url.strip()


def parse_time_points(raw: str) -> List[str]:
    """解析 'HH:MM,HH:MM' 形式的时间点列表。"""
    if not raw:
        return []
    points = []
    for item in raw.replace("，", ",").split(","):
        item = item.strip()
        if not item:
            continue
        if not re.fullmatch(r"\d{1,2}:\d{2}", item):
            raise ValueError(f"时间点格式错误: {item}（应形如 20:05）")
        hh, mm = item.split(":")
        points.append(f"{int(hh):02d}:{int(mm):02d}")
    return points


def build_time_points(start: Optional[str], interval: Optional[int], count: Optional[int]) -> List[str]:
    """按起始时间 + 间隔 + 个数生成时间点。"""
    if not (start and interval and count):
        return []
    from datetime import datetime, timedelta

    base = datetime.strptime(start, "%H:%M")
    return [(base + timedelta(minutes=interval * i)).strftime("%H:%M") for i in range(count)]


@dataclass
class Config:
    # 飞书应用
    app_id: str = ""
    app_secret: str = ""
    chat_id: str = ""
    # 表格
    sheet_url: str = ""
    sheet_id: str = ""
    base_row: int = 2          # 基准数据写入的行号，后续时间点依次 +1
    sheet_writer: str = "larkcli"  # larkcli | api
    # 浏览器
    browser: str = "edge"      # edge | chrome
    debug_port: int = 9222
    login_timeout: int = 300   # 等待人工登录的秒数
    # 采集
    time_points: List[str] = field(default_factory=list)
    card_title: str = "天猫时段销售情况"
    dry_run: bool = False

    @property
    def sheet_token(self) -> str:
        return parse_sheet_token(self.sheet_url)


def load_config(args) -> Config:
    """从 .env 与环境变量加载配置，并用命令行参数覆盖。"""
    load_dotenv()

    cfg = Config(
        app_id=os.getenv("FEISHU_APP_ID", ""),
        app_secret=os.getenv("FEISHU_APP_SECRET", ""),
        chat_id=os.getenv("FEISHU_CHAT_ID", ""),
        sheet_url=os.getenv("SHEET_URL", ""),
        sheet_id=os.getenv("SHEET_ID", ""),
        base_row=int(os.getenv("BASE_ROW", "2")),
        sheet_writer=os.getenv("SHEET_WRITER", "larkcli"),
        browser=os.getenv("BROWSER", "edge"),
        debug_port=int(os.getenv("DEBUG_PORT", "9222")),
        login_timeout=int(os.getenv("LOGIN_TIMEOUT", "300")),
        card_title=os.getenv("CARD_TITLE", "天猫时段销售情况"),
    )

    raw_points = os.getenv("TIME_POINTS", "")
    if raw_points:
        cfg.time_points = parse_time_points(raw_points)

    # 命令行覆盖
    if getattr(args, "time_points", None):
        cfg.time_points = parse_time_points(args.time_points)
    elif getattr(args, "start", None):
        cfg.time_points = build_time_points(args.start, args.interval, args.count)

    if getattr(args, "sheet_id", None):
        cfg.sheet_id = args.sheet_id
    if getattr(args, "sheet_url", None):
        cfg.sheet_url = args.sheet_url
    if getattr(args, "base_row", None):
        cfg.base_row = args.base_row
    if getattr(args, "browser", None):
        cfg.browser = args.browser
    if getattr(args, "writer", None):
        cfg.sheet_writer = args.writer
    if getattr(args, "debug_port", None):
        cfg.debug_port = args.debug_port
    cfg.dry_run = bool(getattr(args, "dry_run", False))

    return cfg


def validate(cfg: Config) -> None:
    """校验必填项，缺失则抛出明确错误。"""
    missing = []
    if not cfg.app_id:
        missing.append("FEISHU_APP_ID")
    if not cfg.app_secret:
        missing.append("FEISHU_APP_SECRET")
    if not cfg.chat_id:
        missing.append("FEISHU_CHAT_ID")
    if not cfg.sheet_url:
        missing.append("SHEET_URL")
    if not cfg.sheet_id:
        missing.append("SHEET_ID")
    if missing:
        raise ValueError("缺少配置项: " + ", ".join(missing) + "（请复制 .env.example 为 .env 并填写）")
