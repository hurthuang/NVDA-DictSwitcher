# -*- coding: utf-8 -*-
# DictSwitcher — NVDA Global Plugin
#
# 執行層級說明：
#   本外掛 hook speechDictHandler.processText，在以下順序中運作：
#     1. NVDA 使用者詞庫（User Dictionary）  ← 優先，本外掛不影響
#     2. NVDA 標點符號讀法（Speech Symbols）  ← 優先，本外掛不影響
#     3. _orig_processText（NVDA 原生字典流程）
#     4. 本外掛字典套用（my_dict / brl_dict 在原生之後；math_dict 在原生之前）
#
# 因此使用者在 NVDA 設定的個人詞庫與標點符號讀法不會被本外掛覆蓋。

import globalPluginHandler
import speechDictHandler
import os
import ui
import logging
import threading
import urllib.request
import json
import re
import tempfile
import wx
import gui
from scriptHandler import script
import addonHandler

addonHandler.initTranslation()

log = logging.getLogger("nvda")

# ── 檢查更新 ──────────────────────────────────────────────
GITHUB_LATEST_API = "https://api.github.com/repos/hurthuang/NVDA-DictSwitcher/releases/latest"
_UPDATE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/vnd.github+json",
}


def _parse_version(v):
    nums = [int(p) for p in re.findall(r'\d+', v)]
    nums += [0] * (4 - len(nums))
    return tuple(nums[:4])


def _current_version():
    try:
        return addonHandler.getCodeAddon().manifest.get("version", "0")
    except Exception:
        return "0"


def _check_update_worker(silent=False):
    """silent=True 用於開機自動檢查：沒有新版本時完全不提示，避免每次啟動都念一次。"""
    current = _current_version()
    req = urllib.request.Request(GITHUB_LATEST_API, headers=_UPDATE_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        if not silent:
            wx.CallAfter(ui.message, f"檢查更新失敗：{e}")
        return

    latest = data.get("tag_name", "").lstrip("vV")
    if _parse_version(latest) <= _parse_version(current):
        if not silent:
            wx.CallAfter(ui.message, f"目前已是最新版本（v{current}）。")
        return

    asset_url = None
    for asset in data.get("assets", []):
        if asset.get("name", "").endswith(".nvda-addon"):
            asset_url = asset.get("browser_download_url")
            break
    release_url = data.get("html_url", "https://github.com/hurthuang/NVDA-DictSwitcher/releases")
    wx.CallAfter(_prompt_update, latest, current, asset_url, release_url)


def _prompt_update(latest, current, asset_url, release_url):
    """在主執行緒彈出確認對話框；使用者按是才下載並開啟安裝。"""
    if not asset_url:
        ui.browseableMessage(
            f"有新版本可更新：v{latest}（目前使用：v{current}）\n\n下載頁面：\n{release_url}",
            "DictSwitcher 有新版本",
        )
        return
    result = gui.messageBox(
        f"發現新版本 v{latest}（目前使用：v{current}）。\n\n是否立即下載並安裝？",
        "DictSwitcher 有新版本",
        wx.YES_NO | wx.ICON_QUESTION,
    )
    if result == wx.YES:
        ui.message("正在下載更新…")
        threading.Thread(target=_download_and_install_worker, args=(asset_url,), daemon=True).start()


def _download_and_install_worker(asset_url):
    req = urllib.request.Request(asset_url, headers=_UPDATE_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
    except Exception as e:
        wx.CallAfter(ui.message, f"下載更新失敗：{e}")
        return

    tmp_path = os.path.join(tempfile.gettempdir(), "DictSwitcher-update.nvda-addon")
    try:
        with open(tmp_path, "wb") as f:
            f.write(content)
    except Exception as e:
        wx.CallAfter(ui.message, f"儲存更新檔失敗：{e}")
        return

    # 交給系統開啟，觸發 NVDA 原生的附加元件安裝確認流程
    wx.CallAfter(os.startfile, tmp_path)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    # --- 對照表設定區 ---
    DICT_CONFIG = {
        "my_dict.dic":   "破音字修正",
        "brl_dict.dic":  "注音點字字庫",
        "math_dict.dic": "數學點字字庫",
    }
    PRE_PROCESS_DICTS = {"math_dict.dic", "brl_dict.dic"}

    def __init__(self):
        super().__init__()

        self.dicts = []
        self.display_names = []
        self.pre_process = []

        for fileName, friendlyName in self.DICT_CONFIG.items():
            path = os.path.join(os.path.dirname(__file__), fileName)
            if os.path.exists(path):
                sd = speechDictHandler.SpeechDict()
                try:
                    sd.load(path)
                    self.dicts.append(sd)
                    self.display_names.append(friendlyName)
                    self.pre_process.append(fileName in self.PRE_PROCESS_DICTS)
                    log.info(f"DictSwitcher: 載入字典成功: {fileName} ({friendlyName})")
                except Exception as e:
                    log.error(f"DictSwitcher: 載入字典失敗 {fileName}: {e}")

        self.current_idx = 0 if self.dicts else -1

        self._orig_processText = speechDictHandler.processText
        log.info(f"DictSwitcher: _orig_processText = {self._orig_processText}")
        speechDictHandler.processText = self._my_processText
        log.info(f"DictSwitcher: hook 完成，speechDictHandler.processText = {speechDictHandler.processText}")

        # 啟動時背景自動檢查一次更新，延遲幾秒避免搶在 NVDA 啟動流程前面；有新版才提示，沒有則靜默
        wx.CallLater(5000, lambda: threading.Thread(
            target=_check_update_worker, kwargs={"silent": True}, daemon=True
        ).start())

    def _my_processText(self, text, *args):
        log.debug(f"DictSwitcher: called idx={self.current_idx} text={repr(text[:40] if text else text)} args={args}")
        if not text:
            return self._orig_processText(text, *args)

        try:
            if self.current_idx == -1:
                return self._orig_processText(text, *args)

            active_dict = self.dicts[self.current_idx]

            if self.pre_process[self.current_idx]:
                result = text
                for rule in active_dict:
                    result = rule.sub(result)
                return self._orig_processText(result, *args)
            else:
                result = self._orig_processText(text, *args)
                log.debug(f"DictSwitcher: after orig: {repr(result[:40] if result else result)}")
                for rule in active_dict:
                    result = rule.sub(result)
                log.debug(f"DictSwitcher: after brl_dict: {repr(result[:40] if result else result)}")
                return result

        except Exception:
            log.error("DictSwitcher: 發生錯誤", exc_info=True)
            return self._orig_processText(text, *args)

    @script(
        description="循環切換讀音字庫（破音字修正 / 注音點字字庫 / 數學點字字庫 / 停用）",
        category="讀音字庫切換",
        gesture="kb:nvda+alt+d",
    )
    def script_cycleDictionaries(self, gesture):
        if not self.dicts:
            ui.message("找不到任何自訂字典檔案 (.dic)")
            return

        num_dicts = len(self.dicts)
        if self.current_idx == num_dicts - 1:
            self.current_idx = -1
            ui.message("停用自訂字典")
        else:
            self.current_idx += 1
            ui.message(f"使用：{self.display_names[self.current_idx]}")

    def terminate(self):
        speechDictHandler.processText = self._orig_processText
