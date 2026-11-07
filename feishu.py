# -*- coding: utf-8 -*-
"""飞书开放平台：tenant_access_token 获取与卡片消息推送。"""

import json
import logging

import requests

log = logging.getLogger("sycm.feishu")

_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
_MSG_URL = "https://open.feishu.cn/open-apis/im/v1/messages"


class FeishuError(RuntimeError):
    pass


def get_tenant_token(app_id: str, app_secret: str) -> str:
    resp = requests.post(_TOKEN_URL, json={"app_id": app_id, "app_secret": app_secret}, timeout=20)
    data = resp.json()
    if data.get("code") != 0:
        raise FeishuError(f"获取 tenant_access_token 失败: {data}")
    return data["tenant_access_token"]


def _fmt_int(value: float) -> str:
    return f"{int(round(value)):,}"


def build_card(title: str, time_str: str, current: dict, period: dict, period_minutes: int) -> dict:
    """构造卡片：时点数据 + 时段累计。"""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**时点数据（{time_str} 实时累计）**\n"
                        "| 销售额 | 访客 | 买家数 |\n"
                        "| --- | --- | --- |\n"
                        f"| {current['amount']:,.2f} | {_fmt_int(current['visitors'])} | {_fmt_int(current['buyers'])} |"
                    ),
                },
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**时段累计（{period_minutes} 分钟）**\n"
                        "| 销售额 | 访客 | 买家数 |\n"
                        "| --- | --- | --- |\n"
                        f"| {period['amount']:,.2f} | {_fmt_int(period['visitors'])} | {_fmt_int(period['buyers'])} |"
                    ),
                },
            },
        ],
    }


def send_card(token: str, chat_id: str, title: str, time_str: str,
              current: dict, period: dict, period_minutes: int, dry_run: bool = False) -> bool:
    """发送卡片消息到群聊。"""
    card = build_card(title, time_str, current, period, period_minutes)

    if dry_run:
        log.info("[dry-run] 卡片预览：\n%s", json.dumps(card, ensure_ascii=False, indent=2))
        return True

    payload = {
        "receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    resp = requests.post(
        _MSG_URL,
        params={"receive_id_type": "chat_id"},
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=20,
    )
    data = resp.json()
    if data.get("code") != 0:
        log.error("卡片推送失败: %s", data)
        return False

    log.info("卡片推送成功（%s）", title)
    return True
