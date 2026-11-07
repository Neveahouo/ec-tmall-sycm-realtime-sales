# -*- coding: utf-8 -*-
"""表格写入后端。

两种方式：
- larkcli：调用本机 lark-cli（使用当前飞书登录态，无需应用授权），默认方式。
- api：调用飞书开放接口，需要应用已开通 sheets:spreadsheet 权限，
       且该应用/机器人被加入表格协作者。
"""

import json
import logging
import subprocess

import requests

log = logging.getLogger("sycm.writer")


class SheetWriter:
    def __init__(self, sheet_url: str, sheet_id: str, token: str = ""):
        self.sheet_url = sheet_url
        self.sheet_id = sheet_id
        self.token = token

    def write_row(self, row: int, values, dry_run: bool = False, start_col: str = "B") -> bool:
        raise NotImplementedError

    def read_layout(self):
        """读取 A 列时间标签，返回 (labels_map, empty_rows, max_row)。"""
        raise NotImplementedError

    @staticmethod
    def _build_layout(labels) -> tuple:
        """labels: [(row, text)]，返回标签映射、空行列表、最大行号。"""
        mapping = {}
        empty = []
        max_row = 1
        for row, text in labels:
            if row == 1:  # 表头
                continue
            max_row = max(max_row, row)
            label = (text or "").strip()
            if label:
                mapping[label] = row
            else:
                empty.append(row)
        return mapping, empty, max_row


class LarkCliWriter(SheetWriter):
    """通过 lark-cli 写入（沿用本机飞书登录态）。"""

    def __init__(self, sheet_url: str, sheet_id: str):
        super().__init__(sheet_url, sheet_id)

    def _run(self, *args, timeout: int = 60):
        cmd = ["lark-cli", "sheets", *args]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=timeout)
        except FileNotFoundError:
            log.error("未找到 lark-cli，请先安装并登录，或改用 --writer api")
            return None
        except subprocess.TimeoutExpired:
            log.error("lark-cli 执行超时")
            return None
        return result

    def read_layout(self):
        result = self._run("+csv-get", "--url", self.sheet_url,
                           "--sheet-id", self.sheet_id, "--range", "A1:A300")
        if result is None or result.returncode != 0:
            log.warning("读取时间标签失败，将按顺序追加：%s",
                        (result.stderr if result else "")[:200])
            return {}, [], 1

        raw = result.stdout or ""
        start = raw.find("{")
        if start < 0:
            return {}, [], 1
        try:
            payload = json.loads(raw[start:])
        except json.JSONDecodeError:
            log.warning("解析表格结构失败，按顺序追加")
            return {}, [], 1

        csv_text = (payload.get("data") or {}).get("csv") or ""
        labels = []
        for idx, line in enumerate(csv_text.splitlines()):
            if idx == 0:  # 表头行
                continue
            labels.append((idx + 1, line.split(",")[0].strip('"').strip()))

        mapping, empty, max_row = self._build_layout(labels)
        log.info("表格时间标签 %s 个，空行 %s 个，最大行 %s",
                 len(mapping), len(empty), max_row)
        return mapping, empty, max_row

    def write_row(self, row: int, values, dry_run: bool = False, start_col: str = "B") -> bool:
        cells = [[{"value": v} for v in values]]
        end_col = chr(ord(start_col) + len(values) - 1)
        cmd = [
            "lark-cli", "sheets", "+cells-set",
            "--url", self.sheet_url,
            "--sheet-id", self.sheet_id,
            "--range", f"{start_col}{row}:{end_col}{row}",
            "--cells", json.dumps(cells, ensure_ascii=False),
        ]
        if dry_run:
            log.info("[dry-run] 将执行：%s … --range %s%s:%s%s",
                     " ".join(cmd[:6]), start_col, row, end_col, row)
            return True

        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=60)
        except FileNotFoundError:
            log.error("未找到 lark-cli，请先安装并登录，或改用 --writer api")
            return False
        except subprocess.TimeoutExpired:
            log.error("lark-cli 执行超时")
            return False

        if result.returncode != 0:
            log.error("写入第 %s 行失败：%s", row, (result.stderr or result.stdout)[:300])
            return False

        log.info("已写入第 %s 行：%s", row, values)
        return True


class FeishuApiWriter(SheetWriter):
    """通过飞书开放接口写入（需要 sheets 权限）。"""

    API = "https://open.feishu.cn/open-apis/sheets/v2/spreadsheets"

    def read_layout(self):
        url = f"{self.API}/{self.token}/values/{self.sheet_id}!A1:A300"
        resp = requests.get(url, headers={"Authorization": f"Bearer {self.token}"}, timeout=20)
        payload = resp.json()
        if payload.get("code") != 0:
            log.warning("读取时间标签失败，将按顺序追加：%s", payload.get("msg"))
            return {}, [], 1

        rows = ((payload.get("data") or {}).get("valueRange") or {}).get("values") or []
        labels = []
        for idx, row in enumerate(rows):
            cell = row[0] if row else ""
            if isinstance(cell, dict):
                cell = cell.get("text") or cell.get("value") or ""
            labels.append((idx + 1, str(cell).strip()))

        mapping, empty, max_row = self._build_layout(labels)
        log.info("表格时间标签 %s 个，空行 %s 个，最大行 %s",
                 len(mapping), len(empty), max_row)
        return mapping, empty, max_row

    def write_row(self, row: int, values, dry_run: bool = False, start_col: str = "B") -> bool:
        end_col = chr(ord(start_col) + len(values) - 1)
        url = f"{self.API}/{self.token}/values_batch_update"
        body = {"valueRange": {"range": f"{self.sheet_id}!{start_col}{row}:{end_col}{row}",
                               "values": [list(values)]}}
        if dry_run:
            log.info("[dry-run] 将写入 %s：%s", body["valueRange"]["range"], values)
            return True

        resp = requests.put(url, headers={"Authorization": f"Bearer {self.token}"},
                            json=body, timeout=20)
        data = resp.json()
        if data.get("code") != 0:
            log.error("接口写入第 %s 行失败：%s", row, data)
            return False
        log.info("已写入第 %s 行：%s", row, values)
        return True


def build_writer(kind: str, sheet_url: str, sheet_id: str, tenant_token: str) -> SheetWriter:
    if kind == "api":
        return FeishuApiWriter(sheet_url, sheet_id, tenant_token)
    return LarkCliWriter(sheet_url, sheet_id)
