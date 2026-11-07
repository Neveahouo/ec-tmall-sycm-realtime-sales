# -*- coding: utf-8 -*-
"""离线自检：不依赖浏览器，验证识别正则与配置解析。

运行： python tests/selftest.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extractor import extract, is_valid, parse_number
from config import parse_time_points, build_time_points, parse_sheet_token


class FakeDriver:
    def __init__(self, text):
        self.text = text

    def find_element(self, *a, **k):
        class E:
            pass
        e = E()
        e.text = self.text
        return e


CASES = [
    # (说明, 页面文本片段, 期望)
    ("标准三行", "支付金额\n2,042,513.82\n访客数\n428,939\n支付买家数\n28,619", (2042513.82, 428939, 28619)),
    ("带单位", "支付金额(元)\n86,420.15\n访客数(人)\n1,236\n支付买家数\n92", (86420.15, 1236, 92)),
    ("无千分位", "支付金额\n999.00\n访客数\n10\n支付买家数\n3", (999.0, 10, 3)),
    ("四行混排", "实时\n支付金额\n3,125.6\n较昨日\n访客数\n58\n支付买家数\n7\n其他", (3125.6, 58, 7)),
]

ok = True
for name, text, expect in CASES:
    d = extract(FakeDriver(text))
    got = (d["amount"], d["visitors"], d["buyers"])
    passed = all(abs(a - b) < 0.001 for a, b in zip(got, expect))
    ok &= passed
    print(f"[{'PASS' if passed else 'FAIL'}] {name}: got={got} expect={expect}")

# 配置解析
assert parse_time_points("20:05, 20:10，21:00") == ["20:05", "20:10", "21:00"]
assert build_time_points("11:50", 5, 3) == ["11:50", "11:55", "12:00"]
assert parse_sheet_token("https://x.feishu.cn/sheets/AbCdEf123456?sheet=QpR9wW") == "AbCdEf123456"
assert parse_number("2,042,513.82") == 2042513.82
print("[PASS] 配置解析 / 时间点展开 / token 解析")
print("\n全部通过" if ok else "\n存在失败用例")
sys.exit(0 if ok else 1)
