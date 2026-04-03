import globalPluginHandler
import speechDictHandler
import os
import ui
import logging

log = logging.getLogger("nvda")

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    # --- 對照表設定區 ---
    # 格式為 "檔案名稱": "切換時唸出的名稱"
    DICT_CONFIG = {
        "my_dict.dic": "破音字修正",
        "brl_dict.dic": "注音點字字庫",
        "math_dict.dic": "數學點字字庫",
    }
    # ------------------

    def __init__(self):
        super().__init__()
        self._orig_processText = speechDictHandler.processText
        speechDictHandler.processText = self._my_processText
        
        self.dicts = []        # 存放載入後的字典物件
        self.display_names = [] # 存放顯示名稱
        
        # 1. 根據對照表載入字典
        for fileName, friendlyName in self.DICT_CONFIG.items():
            path = os.path.join(os.path.dirname(__file__), fileName)
            if os.path.exists(path):
                sd = speechDictHandler.SpeechDict()
                try:
                    sd.load(path)
                    self.dicts.append(sd)
                    self.display_names.append(friendlyName)
                    log.info(f"載入字典成功: {fileName} ({friendlyName})")
                except Exception as e:
                    log.error(f"載入字典失敗 {fileName}: {e}")
        
        # 目前使用的字典索引 (-1 代表完全停用)
        self.current_idx = 0 if self.dicts else -1

    def _my_processText(self, text):
        if not text: 
            return self._orig_processText(text)
            
        try:
            # 1. 先呼叫原生的處理函式，讓 NVDA 原生辭典（使用者、語音、預設）優先發生作用
            processed_text = self._orig_processText(text)
            
            # 2. 如果目前是「停用」狀態，直接回傳原生處理後的結果
            if self.current_idx == -1:
                return processed_text
                
            # 3. 在原生處理後的基礎上，套用插件字典（如 math_dict.dic 或 brl_dict.dic）
            final_text = processed_text
            active_dict = self.dicts[self.current_idx]
            for rule in active_dict:
                final_text = rule.sub(final_text)
                
            return final_text
        except:
            # 發生錯誤時回傳原生處理結果，確保語音不中斷
            return self._orig_processText(text)

    # 2. 定義快捷鍵動作：切換字典
    def script_cycleDictionaries(self, gesture):
        if not self.dicts:
            ui.message("找不到任何自訂字典檔案 (.dic)")
            return
            
        # 循環邏輯：0 -> 1 -> ... -> 停用(-1) -> 0
        num_dicts = len(self.dicts)
        
        if self.current_idx == num_dicts - 1:
            # 如果已經是最後一個字典，下一個就是「停用」
            self.current_idx = -1
            ui.message("停用自訂字典")
        else:
            # 切換到下一個
            self.current_idx += 1
            current_name = self.display_names[self.current_idx]
            ui.message(f"使用：{current_name}")

    # 3. 綁定快捷鍵 NVDA+Alt+D
    __gestures = {
        "kb:nvda+alt+d": "cycleDictionaries",
    }

    def terminate(self):
        # 外掛解除時還原核心函式
        speechDictHandler.processText = self._orig_processText