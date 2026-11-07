# -*- coding: utf-8 -*-
"""采集主流程：连接浏览器 → 登录 → 基准 → 按时间点采集 → 写表 → 推卡片。"""

import logging
import time
from datetime import datetime

import browser
import extractor
import feishu
from writer import build_writer

log = logging.getLogger("sycm.runner")


def _target_dt(time_point: str) -> datetime:
    now = datetime.now()
    t = datetime.strptime(time_point, "%H:%M")
    return t.replace(year=now.year, month=now.month, day=now.day)


def capture_at(driver, time_point: str, lead_seconds: int = 12):
    """在指定时刻采集：提前刷新页面，到点读取，减少时间误差。"""
    target = _target_dt(time_point)
    remaining = (target - datetime.now()).total_seconds()
    if remaining < -60:
        log.warning("%s 已过 %s 秒，跳过该时间点", time_point, int(-remaining))
        return None

    if remaining > lead_seconds:
        wait = remaining - lead_seconds
        log.info("等待 %s（%.0f 秒后刷新，%.0f 秒后采集）", time_point, wait, remaining - wait)
        time.sleep(wait)

    browser.refresh(driver)
    remaining = (target - datetime.now()).total_seconds()
    if remaining > 0:
        time.sleep(remaining)

    return extractor.extract_with_retry(driver)


def _period_minutes(base_time: str, current_time: str) -> int:
    base = datetime.strptime(base_time, "%H:%M")
    cur = datetime.strptime(current_time, "%H:%M")
    if cur < base:  # 跨零点
        cur = cur.replace(day=cur.day + 1)
    return int((cur - base).total_seconds() // 60)


def _write_row(writer, cfg, row: int, label: str, values, write_label: bool) -> bool:
    """按需决定是否把时间点写入 A 列。"""
    if write_label:
        return writer.write_row(row, [label] + list(values), cfg.dry_run, start_col="A")
    return writer.write_row(row, list(values), cfg.dry_run, start_col="B")


class RowResolver:
    """按 A 列时间标签定位写入行；标签不存在时取第一个空行，最后才追加。"""

    def __init__(self, labels_map, empty_rows, max_row, fallback_row: int = 2):
        self.labels = dict(labels_map)
        self.empty = [r for r in empty_rows if r >= fallback_row]
        self.next_row = max(max_row + 1, fallback_row)

    def resolve(self, label: str):
        if label in self.labels:
            return self.labels[label], False
        if self.empty:
            row = self.empty.pop(0)
            self.labels[label] = row
            return row, True
        row = self.next_row
        self.next_row += 1
        self.labels[label] = row
        return row, True


def run(cfg) -> int:
    writer_token = ""
    tok = feishu.get_tenant_token(cfg.app_id, cfg.app_secret)
    if cfg.sheet_writer == "api":
        writer_token = tok

    writer = build_writer(cfg.sheet_writer, cfg.sheet_url, cfg.sheet_id, writer_token)
    card_title = cfg.card_title

    driver = browser.connect(cfg.browser, cfg.debug_port)

    browser.goto_sycm(driver)
    if not browser.wait_login(driver, cfg.login_timeout):
        log.error("未完成登录，任务终止。请先在浏览器中登录生意参谋后重跑。")
        return 2

    browser.switch_realtime(driver)

    # ---------- 读取表格时间标签，建立行映射 ----------
    labels_map, empty_rows, max_row = writer.read_layout()
    resolver = RowResolver(labels_map, empty_rows, max_row, cfg.base_row)
    if cfg.dry_run:
        log.info("[dry-run] 现有时间标签：%s", labels_map)

    # ---------- 基准 ----------
    log.info("采集基准数据…")
    base = extractor.extract_with_retry(driver)
    if not extractor.is_valid(base):
        log.error("基准数据识别失败，请检查页面是否停在实时概览。")
        return 3

    base_time = datetime.now().strftime("%H:%M")
    log.info("基准时点 %s，数据：%s", base_time, base)

    base_row, base_write_label = resolver.resolve(base_time)
    log.info("基准写入第 %s 行%s", base_row, "（同时写入 A 列标签）" if base_write_label else "")

    _write_row(writer, cfg, base_row, base_time, [
        base["amount"], base["visitors"], base["buyers"], 0, 0, 0
    ], base_write_label)

    feishu.send_card(tok, cfg.chat_id, f"{card_title}-{base_time}（基准）", base_time,
                     base, {"amount": 0, "visitors": 0, "buyers": 0}, 0, cfg.dry_run)

    # ---------- 各时间点 ----------
    failures = []
    for tp in cfg.time_points:
        row, write_label = resolver.resolve(tp)
        log.info("===== 时间点 %s → 第 %s 行%s =====", tp, row,
                 "（同时写入 A 列标签）" if write_label else "")

        current = capture_at(driver, tp)
        if current is None:
            failures.append(f"{tp} 已过时未采集")
            continue
        if not extractor.is_valid(current):
            failures.append(f"{tp} 识别失败")
            continue

        period = {k: current[k] - base[k] for k in ("amount", "visitors", "buyers")}
        if any(period[k] < 0 for k in period):
            log.error("%s 数值小于基准，疑似识别异常，跳过写入：当前=%s 基准=%s", tp, current, base)
            failures.append(f"{tp} 数值异常（小于基准）")
            continue

        minutes = _period_minutes(base_time, tp)

        _write_row(writer, cfg, row, tp, [
            current["amount"], current["visitors"], current["buyers"],
            period["amount"], period["visitors"], period["buyers"],
        ], write_label)

        feishu.send_card(tok, cfg.chat_id, f"{card_title}-{tp}", tp,
                         current, period, minutes, cfg.dry_run)

    log.info("全部时间点处理完成")
    if failures:
        log.warning("未完成项：%s", "；".join(failures))
        return 1
    return 0
