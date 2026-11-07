# -*- coding: utf-8 -*-
"""从生意参谋页面提取实时数据。

不依赖任何数据接口，只读取页面已渲染出来的文本，等同人工查看。
"""

import os
import re
import time
import logging
from datetime import datetime

from selenium.webdriver.common.by import By

log = logging.getLogger("sycm.extractor")

# 支付金额 / 访客数 / 支付买家数
PATTERNS = {
    "amount": [
        r"支付金额\s*\n\s*([\d,]+\.?\d*)",
        r"支付金额[\s\S]{0,40}?([\d,]+\.[\d]{2})",
        r"支付金额[\s\S]{0,40}?([\d,]{1,15})",
    ],
    "visitors": [
        r"访客数\s*\n\s*([\d,]+)",
        r"访客数[\s\S]{0,40}?([\d,]{1,15})",
    ],
    "buyers": [
        r"支付买家数\s*\n\s*([\d,]+)",
        r"支付买家数[\s\S]{0,40}?([\d,]{1,15})",
    ],
}


def parse_number(text: str) -> float:
    """去掉千分位逗号并转成数值。"""
    if not text:
        return 0.0
    clean = str(text).replace(",", "").replace(" ", "").strip()
    m = re.search(r"[\d]+\.?\d*", clean)
    if not m:
        return 0.0
    try:
        return float(m.group())
    except ValueError:
        return 0.0


def _match_any(text: str, patterns) -> float:
    for p in patterns:
        m = re.search(p, text)
        if m:
            value = parse_number(m.group(1))
            if value > 0:
                return value
    return 0.0


def extract(driver) -> dict:
    """提取一次当前页面数据。"""
    try:
        text = driver.find_element(By.TAG_NAME, "body").text or ""
    except Exception as exc:
        log.warning("读取页面文本失败：%s", exc)
        text = ""

    data = {k: _match_any(text, v) for k, v in PATTERNS.items()}
    log.info(
        "识别结果 支付金额=%s 访客=%s 买家数=%s",
        f"{data['amount']:,.2f}",
        f"{data['visitors']:,.0f}",
        f"{data['buyers']:,.0f}",
    )
    return data


def is_valid(data: dict) -> bool:
    return data["amount"] > 0 and data["visitors"] > 0 and data["buyers"] > 0


def extract_with_retry(driver, retries: int = 3, shot_dir: str = "logs") -> dict:
    """识别失败时刷新页面重试；仍失败则截图留证。"""
    data = {}
    for attempt in range(1, retries + 1):
        data = extract(driver)
        if is_valid(data):
            return data
        log.warning("第 %s/%s 次识别异常（存在 0 值），2 秒后重试", attempt, retries)
        if attempt < retries:
            try:
                driver.refresh()
            except Exception:
                pass
            time.sleep(3)

    os.makedirs(shot_dir, exist_ok=True)
    shot = os.path.join(shot_dir, f"fail_{datetime.now():%Y%m%d_%H%M%S}.png")
    try:
        driver.save_screenshot(shot)
        log.error("识别失败，已截图：%s", shot)
    except Exception as exc:
        log.warning("截图失败：%s", exc)
    return data
