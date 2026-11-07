# -*- coding: utf-8 -*-
"""浏览器连接与页面操作。

核心思路：不自己启动浏览器，而是连接一个「人工登录过的、以 debug 模式启动的」
浏览器进程。这样页面是真人会话，不触发生意参谋的反爬/滑块风控。
"""

import time
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

SYCM_URL = "https://sycm.taobao.com/portal/home.htm"

log = logging.getLogger("sycm.browser")


def connect(browser: str = "edge", debug_port: int = 9222) -> webdriver.Remote:
    """连接到已启动的 debug 模式浏览器。"""
    addr = f"127.0.0.1:{debug_port}"
    if browser.lower() == "chrome":
        from selenium.webdriver.chrome.options import Options

        options = Options()
        options.add_experimental_option("debuggerAddress", addr)
        driver = webdriver.Chrome(options=options)
    else:
        from selenium.webdriver.edge.options import Options

        options = Options()
        options.add_experimental_option("debuggerAddress", addr)
        driver = webdriver.Edge(options=options)

    # 多窗口时优先选中生意参谋所在窗口
    try:
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if "sycm.taobao.com" in (driver.current_url or ""):
                break
    except Exception:
        pass

    log.info("已连接 %s（debug 端口 %s），当前页面：%s", browser, debug_port, driver.title)
    return driver


def _page_text(driver) -> str:
    try:
        return driver.find_element(By.TAG_NAME, "body").text or ""
    except Exception:
        return ""


def goto_sycm(driver) -> None:
    """打开生意参谋首页（若当前不在该域名下）。"""
    if "sycm.taobao.com" not in (driver.current_url or ""):
        driver.get(SYCM_URL)
        time.sleep(3)


def wait_login(driver, timeout: int = 300) -> bool:
    """等待人工登录完成。检测到数据概览文案即视为登录成功。"""
    log.info("等待登录：请在浏览器窗口中完成生意参谋登录（最长 %s 秒）", timeout)
    deadline = time.time() + timeout
    reported = 0
    dead = 0
    while time.time() < deadline:
        try:
            text = _page_text(driver)
            url = driver.current_url or ""
        except Exception as exc:
            dead += 1
            if dead >= 5:
                log.error("浏览器会话已失效（窗口可能被关闭）：%s", exc)
                return False
            time.sleep(2)
            continue
        dead = 0
        if "sycm.taobao.com" in url and ("支付金额" in text or "数据概览" in text):
            log.info("检测到登录成功")
            return True
        waited = int(time.time() - (deadline - timeout))
        if waited // 30 > reported:
            reported = waited // 30
            log.info("仍在等待登录… 已等待 %s 秒", waited)
        time.sleep(2)
    log.error("等待登录超时（%s 秒）", timeout)
    return False


def switch_realtime(driver) -> None:
    """切换到「实时」视图。"""
    try:
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'实时')] | //div[contains(text(),'实时')]"))
        )
        btn.click()
        time.sleep(3)
        log.info("已切换到实时视图")
    except Exception:
        log.info("未找到「实时」入口，按当前视图继续")


def refresh(driver) -> None:
    """刷新页面获取最新数据。"""
    try:
        driver.refresh()
    except Exception as exc:
        log.warning("刷新页面失败：%s", exc)
        time.sleep(3)
