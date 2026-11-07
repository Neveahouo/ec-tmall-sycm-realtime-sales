# -*- coding: utf-8 -*-
"""命令行入口。

用法示例：
    python run.py --time-points "20:05,20:10,20:15"
    python run.py --start 20:00 --interval 5 --count 12
    python run.py --once           # 只采集一次当前数据，用于验证环境
"""

import argparse
import logging
import os
import sys
from datetime import datetime

from config import load_config, validate
import runner
import browser
import extractor


def setup_logging(level: str = "INFO") -> None:
    os.makedirs("logs", exist_ok=True)
    logfile = os.path.join("logs", f"{datetime.now():%Y-%m-%d}.log")
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(logfile, encoding="utf-8"),
        ],
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="生意参谋实时销售数据采集")
    p.add_argument("--time-points", help='时间点列表，逗号分隔，如 "20:05,20:10"')
    p.add_argument("--start", help="按间隔生成时间点：起始时间 HH:MM")
    p.add_argument("--interval", type=int, help="按间隔生成时间点：间隔分钟")
    p.add_argument("--count", type=int, help="按间隔生成时间点：个数")
    p.add_argument("--sheet-url", help="飞书表格链接（覆盖 .env）")
    p.add_argument("--sheet-id", help="工作表 sheet_id（覆盖 .env）")
    p.add_argument("--base-row", type=int, help="基准数据写入行号，默认 2")
    p.add_argument("--browser", choices=["edge", "chrome"], help="连接的浏览器")
    p.add_argument("--debug-port", type=int, help="浏览器 debug 端口，默认 9222")
    p.add_argument("--writer", choices=["larkcli", "api"], help="表格写入方式")
    p.add_argument("--dry-run", action="store_true", help="只打印，不写表不推送")
    p.add_argument("--once", action="store_true", help="只采集一次当前数据并打印")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_level)
    log = logging.getLogger("sycm.main")

    cfg = load_config(args)

    if args.once:
        driver = browser.connect(cfg.browser, cfg.debug_port)
        browser.goto_sycm(driver)
        if not browser.wait_login(driver, cfg.login_timeout):
            log.error("未完成登录")
            return 2
        browser.switch_realtime(driver)
        data = extractor.extract_with_retry(driver)
        log.info("当前采集结果：%s", data)
        return 0 if extractor.is_valid(data) else 3

    try:
        validate(cfg)
    except ValueError as exc:
        log.error("%s", exc)
        return 4

    if not cfg.time_points:
        log.error("未配置时间点：请用 --time-points 或 --start/--interval/--count，"
                  "或在 .env 中设置 TIME_POINTS")
        return 4

    log.info("配置：浏览器=%s 端口=%s 写入方式=%s 基准行=%s 时间点=%s%s",
             cfg.browser, cfg.debug_port, cfg.sheet_writer, cfg.base_row,
             cfg.time_points, "（dry-run）" if cfg.dry_run else "")

    return runner.run(cfg)


if __name__ == "__main__":
    sys.exit(main())
