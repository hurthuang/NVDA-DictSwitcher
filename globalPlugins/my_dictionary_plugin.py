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
from scriptHandler import script
import addonHandler

addonHandler.initTranslation()

log = logging.getLogger("nvda")


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
