import webview
import json
import os
import subprocess
import threading
import datetime
import glob
import time
import sys
import ctypes
import webbrowser
import urllib.request
import urllib.error

# ==========================================
# 1. 基础配置与本地数据管理 (兼容 PyInstaller 打包)
# ==========================================
WINDOW_TITLE = 'XYplorerTagHelper 1.2.5'

# 如果是被打包成 .exe 运行，则获取 .exe 所在目录；否则获取当前 .py 脚本所在目录
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "Data")
LOG_DIR = os.path.join(BASE_DIR, "Logs")
OUTPUT_DIR = os.path.join(BASE_DIR, "Output")

TAGS_FILE = os.path.join(DATA_DIR, "tags.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

for d in [DATA_DIR, LOG_DIR, OUTPUT_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

DEFAULT_TAG_TREE = {
    "默认工作区": {
        "未分类": { "_bg_color": "", "_tags": ["?*", '""'] },
        "项目状态": { "_bg_color": "", "_tags": ["重要", "紧急", "待办", "搁置", "完成"] }
    }
}

# 增加文件读写锁，防止并发调用导致文件写入冲突及丢失
_data_lock = threading.Lock()
_config_lock = threading.Lock()

def load_tags():
    if os.path.exists(TAGS_FILE):
        try:
            with open(TAGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "未分类" in data: data = {"默认工作区": data}
                for ws in data:
                    if "未分类" not in data[ws]:
                        data[ws] = {"未分类": {"_bg_color": "", "_tags": ["?*", '""']}, **data[ws]}
                return data
        except Exception: pass
    return DEFAULT_TAG_TREE

def save_tags(tags_data):
    with _data_lock:
        with open(TAGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(tags_data, f, ensure_ascii=False, indent=4)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception: pass
    return {
        "colorHistory": [], "customColors": [], "currentWs": "默认工作区",
        "hist_path": [], "hist_name": [], "hist_remark": [],
        "customExts": [], "xyPath": r"C:\XYplorer\XYplorer.exe",
        "orderType": [], "orderLabel": [], "orderRating": [], "orderExt": [],
        "xyLabels": [], "actionBtnColors": {}, "wsColors": {},
        "theme": "dark", "lang": "zh-CN",
        "ai_api": "http://localhost:11434/api/generate",
        "ai_model": "qwen2.5:0.5b"
    }

def save_config(cfg_data):
    with _config_lock:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg_data, f, ensure_ascii=False, indent=4)

def write_log(msg, level="INFO"):
    try:
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        log_file = os.path.join(LOG_DIR, f"helper_{date_str}.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{time_str}] [{level}] {msg}\n")
        
        cutoff_date = now - datetime.timedelta(days=7)
        for log_path in glob.glob(os.path.join(LOG_DIR, "helper_*.log")):
            filename = os.path.basename(log_path)
            try:
                file_date_str = filename.replace("helper_", "").replace(".log", "")
                file_date = datetime.datetime.strptime(file_date_str, "%Y-%m-%d")
                if file_date < cutoff_date:
                    os.remove(log_path)
            except: pass
    except Exception as e:
        print("日志系统异常:", e)

# ==========================================
# 2. Python API
# ==========================================
class Api:
    def __init__(self):
        self.last_folder_open_time = 0
        self._cancel_flag = False  # 批量操作中断标志位

    def cancel_batch(self):
        self._cancel_flag = True

    def _update_progress(self, sent, total, mode='cmd'):
        try:
            if webview.windows:
                if mode == 'cmd':
                    webview.windows[0].evaluate_js(f"updateBatchProgress({sent}, {total})")
                else:
                    webview.windows[0].evaluate_js(f"updateAiProgress({sent}, {total})")
        except: pass

    def _t(self, key, *args):
        lang = self.get_config().get('lang', 'zh-CN')
        msgs = {
            'zh-CN': {
                'test_start': '测试 XYplorer 路径: {}',
                'test_ok': 'XYplorer 连接测试成功。',
                'test_fail': '无法启动 XYplorer: {}',
                'test_not_found': '未在指定路径找到 XYplorer.exe。',
                'log_search_cmd': '执行搜索命令: {} /feed="{}"',
                'log_script_cmd': '执行脚本命令: {} /feed="{}"',
                'log_exec_fail': '执行失败: 未找到 XYplorer.exe',
                'log_exec_search_err': '执行搜索异常: {}',
                'log_exec_script_err': '执行脚本异常: {}',
                'log_clip_err': '安全读取剪贴板异常: {}',
                'log_data_not_found': '找不到数据文件',
                'log_tag_dat_err': '未在 tag.dat 中找到 Labels 配置',
                'log_export_data_ok': '成功导出工作区数据至: {}',
                'log_export_data_err': '导出数据异常: {}',
                'log_export_cfg_ok': '成功导出软件设置至: {}',
                'log_export_cfg_err': '导出设置异常: {}',
                'log_open_dir_err': '无法打开输出目录: {}',
                'log_focus_err': '窗口聚焦失败: {}',
                'log_theme_err': '更改原生标题栏主题失败: {}',
                'log_doc_not_found': '找不到说明文档: {}',
                'log_doc_err': '打开文档失败: {}',
                'log_url_err': '打开链接失败: {}',
                'fn_data': 'XYplorerTagHelper-数据_{}.json',
                'fn_config': 'XYplorerTagHelper-软件设置_{}.json',
                'fn_ws': 'XYplorerTagHelper-工作区({})_{}.json',
                # --- 新增的批量UCS多语言支持 ---
                'err_xy_not_found': '未找到 XYplorer.exe',
                'err_dict_not_found': '未在 Data 目录下找到 {}',
                'err_timeout': '获取选中文件超时，请确保在 XYplorer 中有选中项',
                'info_no_sel': '未选中任何文件或文件夹',
                'err_no_valid': '选中范围内没有有效文件',
                'info_no_match_cat': '没有文件的 CatID 在字典中找到匹配项',
                'info_no_match_name': '没有任何文件名的片段匹配到同义词字典',
                'log_ucs_start': '开始执行 批量UCS标签...',
                'log_ucs_fail': '批量UCS标签失败：{}',
                'log_ucs_cancel': '批量UCS标签取消：{}',
                'log_ucs_ok': '批量UCS标签成功执行！共为 {} 个文件追加了标签。',
                'log_ucs_err': '批量UCS标签发生异常: {}',
                'log_ucs_name_start': '开始执行 批量文件名转UCS标签...',
                'log_ucs_name_fail': '批量文件名转UCS标签失败：{}',
                'log_ucs_name_cancel': '批量文件名转UCS标签取消：{}',
                'log_ucs_name_ok': '批量文件名转UCS标签成功执行！共为 {} 个文件追加了标签。',
                'log_ucs_name_err': '批量文件名转UCS标签发生异常: {}',
                'log_ai_start': '开始执行 AI智能打标签 ({})', 'log_ai_fail': 'AI 智能打标签失败: {}', 'log_ai_ok': 'AI 智能打标签执行成功！', 'log_ai_err': 'AI 智能打标签发生异常: {}',
                'err_ollama': '无法连接到本地 AI 接口 (Ollama)。请确保已安装并在后台运行。',
                'batch_cancelled': '已手动取消批量操作。'
            },
            'zh-TW': {
                'test_start': '測試 XYplorer 路徑: {}',
                'test_ok': 'XYplorer 連接測試成功。',
                'test_fail': '無法啟動 XYplorer: {}',
                'test_not_found': '未在指定路徑找到 XYplorer.exe。',
                'log_search_cmd': '執行搜尋命令: {} /feed="{}"',
                'log_script_cmd': '執行腳本命令: {} /feed="{}"',
                'log_exec_fail': '執行失敗: 未找到 XYplorer.exe',
                'log_exec_search_err': '執行搜尋異常: {}',
                'log_exec_script_err': '執行腳本異常: {}',
                'log_clip_err': '安全讀取剪貼簿異常: {}',
                'log_data_not_found': '找不到資料檔案',
                'log_tag_dat_err': '未在 tag.dat 中找到 Labels 配置',
                'log_export_data_ok': '成功匯出工作區資料至: {}',
                'log_export_data_err': '匯出資料異常: {}',
                'log_export_cfg_ok': '成功匯出軟體設定至: {}',
                'log_export_cfg_err': '匯出設定異常: {}',
                'log_open_dir_err': '無法開啟輸出目錄: {}',
                'log_focus_err': '視窗聚焦失敗: {}',
                'log_theme_err': '更改原生標題列主題失敗: {}',
                'log_doc_not_found': '找不到說明文件: {}',
                'log_doc_err': '開啟文件失敗: {}',
                'log_url_err': '開啟連結失敗: {}',
                'fn_data': 'XYplorerTagHelper-資料_{}.json',
                'fn_config': 'XYplorerTagHelper-軟體設定_{}.json',
                'fn_ws': 'XYplorerTagHelper-工作區({})_{}.json',
                # --- 新增的批量UCS多语言支持 ---
                'err_xy_not_found': '未找到 XYplorer.exe',
                'err_dict_not_found': '未在 Data 目錄下找到 {}',
                'err_timeout': '取得選取檔案超時，請確保在 XYplorer 中有選取項目',
                'info_no_sel': '未選取任何檔案或資料夾',
                'err_no_valid': '選取範圍內沒有有效檔案',
                'info_no_match_cat': '沒有檔案的 CatID 在字典中找到匹配項',
                'info_no_match_name': '沒有任何檔名的片段匹配到同義詞字典',
                'log_ucs_start': '開始執行 批次打UCS標籤...',
                'log_ucs_fail': '批次打UCS標籤失敗：{}',
                'log_ucs_cancel': '批次打UCS標籤取消：{}',
                'log_ucs_ok': '批次打UCS標籤成功執行！共為 {} 個檔案追加了標籤。',
                'log_ucs_err': '批次打UCS標籤發生異常: {}',
                'log_ucs_name_start': '開始執行 批次檔名轉UCS標籤...',
                'log_ucs_name_fail': '批次檔名轉UCS標籤失敗：{}',
                'log_ucs_name_cancel': '批次檔名轉UCS標籤取消：{}',
                'log_ucs_name_ok': '批次檔名轉UCS標籤成功執行！共為 {} 個檔案追加了標籤。',
                'log_ucs_name_err': '批次檔名轉UCS標籤發生異常: {}',
                'log_ai_start': '開始執行 AI智慧打標籤 ({})', 'log_ai_fail': 'AI 智慧打標籤失敗: {}', 'log_ai_ok': 'AI 智慧打標籤執行成功！', 'log_ai_err': 'AI 智慧打標籤發生異常: {}',
                'err_ollama': '無法連接到本地 AI 介面 (Ollama)。請確保已安裝並在後台運行。',
                'batch_cancelled': '已手動取消批次操作。'
            },
            'en': {
                'test_start': 'Testing XYplorer path: {}',
                'test_ok': 'XYplorer connection test successful.',
                'test_fail': 'Failed to launch XYplorer: {}',
                'test_not_found': 'XYplorer.exe not found at the specified path.',
                'log_search_cmd': 'Execute search command: {} /feed="{}"',
                'log_script_cmd': 'Execute script command: {} /feed="{}"',
                'log_exec_fail': 'Execution failed: XYplorer.exe not found',
                'log_exec_search_err': 'Execute search exception: {}',
                'log_exec_script_err': 'Execute script exception: {}',
                'log_clip_err': 'Safe clipboard read exception: {}',
                'log_data_not_found': 'Data file not found',
                'log_tag_dat_err': 'Labels config not found in tag.dat',
                'log_export_data_ok': 'Workspace data exported successfully to: {}',
                'log_export_data_err': 'Export data exception: {}',
                'log_export_cfg_ok': 'App config exported successfully to: {}',
                'log_export_cfg_err': 'Export config exception: {}',
                'log_open_dir_err': 'Cannot open output directory: {}',
                'log_focus_err': 'Window focus failed: {}',
                'log_theme_err': 'Failed to change native titlebar theme: {}',
                'log_doc_not_found': 'Manual not found: {}',
                'log_doc_err': 'Failed to open manual: {}',
                'log_url_err': 'Failed to open URL: {}',
                'fn_data': 'XYplorerTagHelper-Data_{}.json',
                'fn_config': 'XYplorerTagHelper-Config_{}.json',
                'fn_ws': 'XYplorerTagHelper-Workspace({})_{}.json',
                # --- 新增的批量UCS多语言支持 ---
                'err_xy_not_found': 'XYplorer.exe not found',
                'err_dict_not_found': '{} not found in Data directory',
                'err_timeout': 'Timeout getting selected files, please ensure items are selected in XYplorer',
                'info_no_sel': 'No files or folders selected',
                'err_no_valid': 'No valid files in selection',
                'info_no_match_cat': 'No files matched CatID in dictionary',
                'info_no_match_name': 'No filename segments matched the synonym dictionary',
                'log_ucs_start': 'Starting Batch UCS Tags...',
                'log_ucs_fail': 'Batch UCS Tags failed: {}',
                'log_ucs_cancel': 'Batch UCS Tags cancelled: {}',
                'log_ucs_ok': 'Batch UCS Tags successful! Appended tags to {} files.',
                'log_ucs_err': 'Batch UCS Tags exception: {}',
                'log_ucs_name_start': 'Starting Batch Filename to UCS Tags...',
                'log_ucs_name_fail': 'Batch Filename to UCS Tags failed: {}',
                'log_ucs_name_cancel': 'Batch Filename to UCS Tags cancelled: {}',
                'log_ucs_name_ok': 'Batch Filename to UCS Tags successful! Appended tags to {} files.',
                'log_ucs_name_err': 'Batch Filename to UCS Tags exception: {}',
                'log_ai_start': 'Starting AI Tagging ({})', 'log_ai_fail': 'AI Tagging failed: {}', 'log_ai_ok': 'AI Tagging successful!', 'log_ai_err': 'AI Tagging exception: {}',
                'err_ollama': 'Cannot connect to local AI (Ollama). Please ensure it is installed and running.',
                'batch_cancelled': 'Batch operation cancelled manually.'
            }
        }
        text = msgs.get(lang, msgs['zh-CN']).get(key, msgs['zh-CN'].get(key, key))
        try: return text.format(*args) if args else text
        except: return text

    def log_message(self, msg, level="INFO"):
        write_log(msg, level)
        print(f"[{level}] {msg}")

    def test_xy_path(self, xy_path):
        exe_path = self._normalize_xy_path(xy_path)
        self.log_message(self._t('test_start', exe_path), "INFO")
        
        if os.path.exists(exe_path):
            try:
                subprocess.Popen(f'"{exe_path}" /feed="::status \'XYplorerTagHelper Connected!\', \'00FF00\';"')
                self.log_message(self._t('test_ok'), "INFO")
                return {"success": True}
            except Exception as e:
                self.log_message(self._t('test_fail', str(e)), "ERROR")
                return {"success": False, "msg": str(e)}
        else:
            self.log_message(self._t('test_not_found'), "ERROR")
            return {"success": False, "msg": "Not found"}

    def focus_window(self):
        def _focus():
            try:
                if webview.windows:
                    w = webview.windows[0]
                    w.restore()
                if os.name == 'nt':
                    import ctypes
                    hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
                    if not hwnd:
                        hwnd = ctypes.windll.user32.GetForegroundWindow()
                    if hwnd:
                        ctypes.windll.user32.ShowWindow(hwnd, 9) # 9 = SW_RESTORE
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception as e:
                self.log_message(self._t('log_focus_err', str(e)), "ERROR")
        threading.Thread(target=_focus, daemon=True).start()

    def change_titlebar_theme(self, color_hex, is_dark):
        def _apply():
            time.sleep(0.1) 
            try:
                if os.name == 'nt':
                    import ctypes
                    from ctypes import wintypes
                    
                    hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
                    if not hwnd:
                        hwnd = ctypes.windll.user32.GetForegroundWindow()

                    if hwnd:
                        icon_path = os.path.abspath(os.path.join(BASE_DIR, 'logo.ico'))
                        if os.path.exists(icon_path):
                            LR_LOADFROMFILE = 0x00000010
                            IMAGE_ICON = 1
                            hicon = ctypes.windll.user32.LoadImageW(0, icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)
                            if hicon:
                                WM_SETICON = 0x0080
                                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 0, hicon) 
                                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 1, hicon) 

                        build = sys.getwindowsversion().build
                        # Win10 2004 (Build 19041) 及以上使用 20 开启暗黑模式，之前使用 19
                        attr_dark = 20 if build >= 19041 else 19
                        val_dark = ctypes.c_int(1 if is_dark else 0)
                        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr_dark, ctypes.byref(val_dark), ctypes.sizeof(val_dark))
                        
                        if build >= 22000:
                            hex_str = color_hex.lstrip('#')
                            r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
                            color_ref = ctypes.c_int(r | (g << 8) | (b << 16))
                            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color_ref), ctypes.sizeof(color_ref))
                            
                        # 【高维绝杀：像素级物理抖动】
                        # DWM 经常跨线程装死，只有物理改变窗口大小才会触发边框重绘
                        rect = wintypes.RECT()
                        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                        width = rect.right - rect.left
                        height = rect.bottom - rect.top
                        
                        # 1. 悄悄增加 1 像素高度，并且禁止画面重绘 (0x401E = ASYNC | NOACTIVATE | NOZORDER | NOMOVE | NOREDRAW)
                        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, width, height + 1, 0x401E)
                        # 2. 瞬间恢复高度，并挂上强制边框重绘标志 (0x4036 = ASYNC | FRAMECHANGED | NOACTIVATE | NOZORDER | NOMOVE)
                        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, width, height, 0x4036)
            except Exception as e:
                self.log_message(self._t('log_theme_err', str(e)), "ERROR")
                
        threading.Thread(target=_apply, daemon=True).start()

    def _normalize_xy_path(self, path):
        p = path.strip().strip('"').strip("'")
        if not p: return ""
        if p.lower().endswith(".exe"): return p
        return os.path.join(p, "XYplorer.exe")

    def _open_output_folder(self):
        current_time = time.time()
        if current_time - self.last_folder_open_time > 2:
            try:
                os.startfile(OUTPUT_DIR)
                self.last_folder_open_time = current_time
            except Exception as e:
                self.log_message(self._t('log_open_dir_err', str(e)), "ERROR")

    def get_data(self): return load_tags()
    def save_data(self, data): return save_tags(data)
    def get_config(self): return load_config()
    def save_config(self, data): return save_config(data)

    def export_data(self):
        try:
            now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self._t('fn_data', now_str)
            save_path = os.path.join(OUTPUT_DIR, filename)
            
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self.get_data(), f, ensure_ascii=False, indent=4)
                
            self.log_message(self._t('log_export_data_ok', save_path), "INFO")
            self._open_output_folder()
            return {"success": True}
        except Exception as e:
            self.log_message(self._t('log_export_data_err', str(e)), "ERROR")
            return {"success": False, "msg": str(e)}

    def export_config(self):
        try:
            now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self._t('fn_config', now_str)
            save_path = os.path.join(OUTPUT_DIR, filename)
            
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self.get_config(), f, ensure_ascii=False, indent=4)
                
            self.log_message(self._t('log_export_cfg_ok', save_path), "INFO")
            self._open_output_folder()
            return {"success": True}
        except Exception as e:
            self.log_message(self._t('log_export_cfg_err', str(e)), "ERROR")
            return {"success": False, "msg": str(e)}

    def export_workspace(self, ws_data_str, ws_name):
        try:
            safe_ws_name = "".join([c for c in ws_name if c not in r'\/:*?"<>|'])
            now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self._t('fn_ws', safe_ws_name, now_str)
            save_path = os.path.join(OUTPUT_DIR, filename)
            
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(ws_data_str)
                
            self.log_message(self._t('log_export_data_ok', save_path), "INFO")
            self._open_output_folder()
            return {"success": True}
        except Exception as e:
            self.log_message(self._t('log_export_data_err', str(e)), "ERROR")
            return {"success": False, "msg": str(e)}

    def execute_search(self, path, syntax, xy_path):
        path = path.strip() or "*"
        syntax = syntax.strip()
        
        path_safe = path.replace("'", "''")
        syntax_safe = syntax.replace("'", "''")
        
        if syntax_safe.startswith("/"):
            script_content = f"goto '{path_safe}?{syntax_safe}';"
        elif syntax_safe:
            script_content = f"goto '{path_safe}?:{syntax_safe}';"
        else:
            script_content = f"goto '{path_safe}?';"
            
        exe_path = self._normalize_xy_path(xy_path)
        
        self.log_message(self._t('log_search_cmd', exe_path, f"load temp.xys -> {script_content}"))
        try:
            if os.path.exists(exe_path):
                import tempfile
                # 写入临时文件，彻底规避 XYplorer 命令行遇到双引号和管道符就崩溃的黑洞
                temp_script = os.path.join(tempfile.gettempdir(), "xy_helper_search.xys")
                with open(temp_script, "w", encoding="utf-16") as f:
                    f.write(script_content)
                
                # 核心杀招：依然使用 /feed 保证在当前页签瞬时执行
                # 但不直接传递含有 R&B 的代码，而是传达一个极其干净的 load 指令！
                temp_safe = temp_script.replace("'", "''")
                cmd_str = f'"{exe_path}" /feed="::load \'{temp_safe}\';"'
                subprocess.Popen(cmd_str)
            else:
                self.log_message(self._t('log_exec_fail'), "ERROR")
        except Exception as e:
            self.log_message(self._t('log_exec_search_err', str(e)), "ERROR")

    def execute_script(self, script, xy_path):
        script = script.strip()
        exe_path = self._normalize_xy_path(xy_path)
        
        self.log_message(self._t('log_script_cmd', exe_path, f"load temp.xys -> {script}"))
        try:
            if os.path.exists(exe_path):
                import tempfile
                temp_script = os.path.join(tempfile.gettempdir(), "xy_helper_script.xys")
                with open(temp_script, "w", encoding="utf-16") as f:
                    # 移除前导 :: 防止独立文件加载时报错
                    s = script[2:].strip() if script.startswith("::") else script
                    f.write(s)
                
                # 同样使用 load 指令，保护你的其他所有操作
                temp_safe = temp_script.replace("'", "''")
                cmd_str = f'"{exe_path}" /feed="::load \'{temp_safe}\';"'
                subprocess.Popen(cmd_str)
            else:
                self.log_message(self._t('log_exec_fail'), "ERROR")
        except Exception as e:
            self.log_message(self._t('log_exec_script_err', str(e)), "ERROR")

    def execute_script(self, script, xy_path):
        script = script.strip()
        exe_path = self._normalize_xy_path(xy_path)
        
        self.log_message(self._t('log_script_cmd', exe_path, script))
        try:
            if os.path.exists(exe_path):
                subprocess.Popen(f'"{exe_path}" /feed="{script}"')
            else:
                self.log_message(self._t('log_exec_fail'), "ERROR")
        except Exception as e:
            self.log_message(self._t('log_exec_script_err', str(e)), "ERROR")
    
    def batch_ucs_tags(self, xy_path):
        import tempfile
        import time
        import os
        import json
        import subprocess
        
        self.log_message(self._t('log_ucs_start'), "INFO")
        try:
            exe_path = self._normalize_xy_path(xy_path)
            if not os.path.exists(exe_path):
                msg = self._t('err_xy_not_found')
                self.log_message(self._t('log_ucs_fail', msg), "ERROR")
                return {"success": False, "msg": msg}

            lang = self.get_config().get('lang', 'zh-CN')
            dict_filename = "ucs_dict_en.json"  # [修改] 强制读取英文字典
            ucs_file = os.path.join(DATA_DIR, dict_filename)
            
            if not os.path.exists(ucs_file):
                msg = self._t('err_dict_not_found', dict_filename)
                self.log_message(self._t('log_ucs_fail', msg), "ERROR")
                return {"success": False, "msg": msg}
            
            with open(ucs_file, 'r', encoding='utf-8') as f:
                ucs_dict = json.load(f)
            
            lower_ucs_dict = {k.lower(): v for k, v in ucs_dict.items()}
            
            temp_dir = tempfile.gettempdir()
            unique_id = str(int(time.time() * 1000)) 
            sel_file = os.path.join(temp_dir, f"xy_sel_ucs_{unique_id}.txt")
            
            safe_sel_file = sel_file.replace("'", "''")
            cmd_get_sel = f"::writefile('{safe_sel_file}', get('SelectedItemsPathNames', '|'), 'o', 'tu');"
            subprocess.Popen(f'"{exe_path}" /feed="{cmd_get_sel}"')
            
            wait_time = 0
            read_success = False
            sel_content = ""
            
            while wait_time < 30: 
                if os.path.exists(sel_file):
                    try:
                        with open(sel_file, 'r', encoding='utf-16', errors='ignore') as f:
                            sel_content = f.read().strip()
                        if sel_content or wait_time > 10:
                            read_success = True
                            break 
                    except PermissionError:
                        pass 
                    except Exception:
                        pass
                time.sleep(0.1)
                wait_time += 1
                
            if not read_success:
                msg = self._t('err_timeout')
                self.log_message(self._t('log_ucs_fail', msg), "ERROR")
                return {"success": False, "msg": msg}
                
            if not sel_content:
                msg = self._t('info_no_sel')
                self.log_message(self._t('log_ucs_cancel', msg), "INFO")
                return {"success": False, "msg": msg}
                
            sel_items = sel_content.split('|')
            all_files = []
            
            for item in sel_items:
                clean_item = item.strip().strip('"').strip("'").strip('\x00')
                if not clean_item:
                    continue
                if os.path.isfile(clean_item):
                    all_files.append(clean_item)
                elif os.path.isdir(clean_item):
                    for root, _, files in os.walk(clean_item):
                        for file in files:
                            all_files.append(os.path.join(root, file))
                            
            if not all_files:
                msg = self._t('err_no_valid')
                self.log_message(self._t('log_ucs_fail', msg), "ERROR")
                return {"success": False, "msg": msg}
                
            self._cancel_flag = False
            total_files = len(all_files)
            self._update_progress(0, total_files)
                
            tag_to_files = {}
            tagged_count = 0
            
            for file_path in all_files:
                basename = os.path.basename(file_path)
                if "_" in basename:
                    cat_id = basename.split('_')[0]
                    target_subcat = lower_ucs_dict.get(cat_id.lower())
                                
                    if target_subcat:
                        final_tag = target_subcat.title() 
                        if final_tag not in tag_to_files:
                            tag_to_files[final_tag] = []
                        tag_to_files[final_tag].append(file_path)
                        tagged_count += 1
                        
            if tagged_count == 0:
                msg = self._t('info_no_match_cat')
                self.log_message(self._t('log_ucs_cancel', msg), "INFO")
                return {"success": False, "msg": msg}
                
            MAX_CHUNK_LEN = 6000
            sent_cmds = 0
            for tag, file_list in tag_to_files.items():
                if self._cancel_flag: break
                current_chunk = []
                current_len = 0
                
                for fp in file_list:
                    current_chunk.append(fp)
                    current_len += len(fp) + 1 
                    
                    if current_len >= MAX_CHUNK_LEN:
                        file_list_str = "|".join(current_chunk)
                        safe_tag = tag.replace("'", "''")
                        safe_file_list_str = file_list_str.replace("'", "''")
                        tag_cmd = f"::tag '{safe_tag}', '{safe_file_list_str}', 1, 0;"
                        subprocess.Popen(f'"{exe_path}" /feed="{tag_cmd}"')
                        sent_cmds += 1
                        self._update_progress(sent_cmds, total_files)
                        time.sleep(0.05) 
                        if self._cancel_flag: break
                        current_chunk = []
                        current_len = 0
                
                if self._cancel_flag: break
                if current_chunk:
                    file_list_str = "|".join(current_chunk)
                    safe_tag = tag.replace("'", "''")
                    safe_file_list_str = file_list_str.replace("'", "''")
                    tag_cmd = f"::tag '{safe_tag}', '{safe_file_list_str}', 1, 0;"
                    subprocess.Popen(f'"{exe_path}" /feed="{tag_cmd}"')
                    sent_cmds += 1
                    self._update_progress(sent_cmds, total_files)
                    time.sleep(0.05)
            
            if getattr(self, '_cancel_flag', False):
                return {"success": False, "msg": self._t('batch_cancelled')}
            
            try:
                if os.path.exists(sel_file): os.remove(sel_file)
            except: pass
            
            self.log_message(self._t('log_ucs_ok', tagged_count), "INFO")
            return {"success": True, "count": tagged_count}
            
        except Exception as e:
            self.log_message(self._t('log_ucs_err', str(e)), "ERROR")
            return {"success": False, "msg": str(e)}

    def batch_ucs_name_tags(self, xy_path):
        import tempfile
        import time
        import os
        import json
        import subprocess
        import re
        
        self.log_message(self._t('log_ucs_name_start'), "INFO")
        try:
            exe_path = self._normalize_xy_path(xy_path)
            if not os.path.exists(exe_path):
                msg = self._t('err_xy_not_found')
                self.log_message(self._t('log_ucs_name_fail', msg), "ERROR")
                return {"success": False, "msg": msg}

            lang = self.get_config().get('lang', 'zh-CN')
            
            # ================= 修改点 1：固定读取合并后的字典 =================
            dict_filename = "ucs_synonyms_merged.json"
            ucs_file = os.path.join(DATA_DIR, dict_filename)
            
            if not os.path.exists(ucs_file):
                msg = self._t('err_dict_not_found', dict_filename)
                self.log_message(self._t('log_ucs_name_fail', msg), "ERROR")
                return {"success": False, "msg": msg}
            
            with open(ucs_file, 'r', encoding='utf-8') as f:
                ucs_syn_dict = json.load(f)

            def normalize_string(s):
                s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s)
                s = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', s)
                s = re.sub(r'[\W_]+', ' ', s)
                return f" {s.lower().strip()} "

            STOP_WORDS = {
                "a", "an", "the", "and", "or", "of", "in", "on", "at", "by", "to", "for", 
                "with", "your", "my", "his", "her", "its", "their", "our", "this", "that", 
                "these", "those", "is", "are", "am", "it", "be", "as"
            }

            # ================= 高维机制 1：通用词豁免名单 =================
            # 当这些词作为分类的次级修饰词时，不强制要求它们必须出现在文件名中
            GENERIC_WORDS = {"general", "misc", "other", "various", "通用", "其它", "其他", "杂项", "各类", "常规", "综合"}

            compiled_syn_dict = {}
            for raw_tag_key, syn_list in ucs_syn_dict.items():
                if '|' in raw_tag_key:
                    en_tag, zh_tag = raw_tag_key.split('|', 1)
                    target_tag = en_tag.strip()  # [修改] 摒弃界面语言判断，强制截取英文标签
                else:
                    target_tag = raw_tag_key.strip()
                    
                if not target_tag: continue
                if target_tag not in compiled_syn_dict:
                    compiled_syn_dict[target_tag] = []
                
                for syn in syn_list:
                    parts = re.split(r'[-_]', syn)
                    if not parts: continue
                    
                    primary_raw = parts[-1]
                    secondary_raws = parts[:-1]
                    
                    def get_sig(raw_str):
                        sig = []
                        for w in normalize_string(raw_str).split():
                            if not w or w.isdigit() or w in STOP_WORDS: continue
                            if len(w) == 1 and w.isascii() and w.isalpha(): continue
                            sig.append(f" {w} ")
                        return frozenset(sig)
                    
                    primary_sig = get_sig(primary_raw)
                    if not primary_sig: continue 
                    
                    valid_secondary_sigs = []
                    
                    for sec in secondary_raws:
                        sec_sig = get_sig(sec)
                        if not sec_sig: continue
                        
                        # ================= 高维机制 2：同义词嵌套免疫 =================
                        # 如果副词和主词的有效单词完全重合（例如 Rain_Cloth_Rain 中的前置 Rain），则忽略该副词校验
                        if sec_sig.issubset(primary_sig):
                            continue
                            
                        # 如果是纯通用修饰词（如 General / 其它），则将其剥离，豁免其硬性匹配规则
                        is_generic = True
                        for w in sec_sig:
                            clean_w = w.strip()
                            if clean_w not in GENERIC_WORDS:
                                is_generic = False
                                break
                        if is_generic:
                            continue
                            
                        valid_secondary_sigs.append(sec_sig)
                    
                    compiled_syn_dict[target_tag].append({
                        "primary": primary_sig,
                        "valid_secondaries": valid_secondary_sigs
                    })
            
            temp_dir = tempfile.gettempdir()
            unique_id = str(int(time.time() * 1000)) 
            sel_file = os.path.join(temp_dir, f"xy_sel_ucs_{unique_id}.txt")
            
            safe_sel_file = sel_file.replace("'", "''")
            
            # 【核心突破 1：高维探测术】
            # 使用 report() 获取所有文件的路径与现存标签，瞬间完成 0 延迟。
            cmd_get_sel = "::if (get('CountSelected') > 0) { writefile('" + safe_sel_file + "', report('{FullName}|||{Tags}<crlf>', 1), 'o', 'tu'); }"
            subprocess.Popen(f'"{exe_path}" /feed="{cmd_get_sel}"')
            
            wait_time = 0
            read_success = False
            sel_content = ""
            
            while wait_time < 30: 
                if os.path.exists(sel_file):
                    try:
                        with open(sel_file, 'r', encoding='utf-16', errors='ignore') as f:
                            sel_content = f.read().strip()
                        if sel_content or wait_time > 10:
                            read_success = True
                            break 
                    except PermissionError: pass 
                    except Exception: pass
                time.sleep(0.1)
                wait_time += 1
                
            if not read_success:
                msg = self._t('err_timeout')
                self.log_message(self._t('log_ucs_name_fail', msg), "ERROR")
                return {"success": False, "msg": msg}
                
            if not sel_content:
                msg = self._t('info_no_sel')
                self.log_message(self._t('log_ucs_name_cancel', msg), "INFO")
                return {"success": False, "msg": msg}
                
            # 【修复 XYplorer report() 的换行符】
            # 因为 report 输出了字面量的 <crlf>，我们需要在此将其替换为真正的换行符
            sel_content = re.sub(r'(?i)<crlf>', '\n', sel_content)
            sel_items = sel_content.split('\n')
            
            all_files_info = [] # 结构：(文件路径, 是否已有标签)
            
            for item in sel_items:
                clean_item = item.strip('\r\n\x00')
                if not clean_item: continue
                
                parts = clean_item.split('|||')
                fp = parts[0].strip().strip('"').strip("'")
                if not fp: continue
                
                # 【高维优化：精准提取已有标签集合】
                existing_tags_set = set()
                if len(parts) > 1 and parts[1].strip():
                    # XYplorer 提取出的多标签通常是用逗号分隔的，我们将其切片并转化为严谨的 Set 集合
                    existing_tags_set = {t.strip() for t in parts[1].split(',') if t.strip()}
                    
                if os.path.isfile(fp):
                    all_files_info.append((fp, existing_tags_set))
                elif os.path.isdir(fp):
                    # 针对文件夹，遍历其内部文件（默认视为无标签进行匹配测试）
                    for root, _, files in os.walk(fp):
                        for file in files:
                            all_files_info.append((os.path.join(root, file), set()))
                            
            if not all_files_info:
                msg = self._t('err_no_valid')
                self.log_message(self._t('log_ucs_name_fail', msg), "ERROR")
                return {"success": False, "msg": msg}
                
            self._cancel_flag = False
            total_files = len(all_files_info)
            self._update_progress(0, total_files)
                
            # 【高维优化 1：放弃单标签散装，改为标签组合聚类字典】
            tag_combo_to_files = {}
            tagged_count = 0
            
            # 【新增辅助探测函数】：精准识别泛用/杂项标签 (Misc)
            def is_generic_tag(t):
                tl = t.lower()
                return any(tl.endswith(x) for x in ['_misc', '_general', '_other', '_various', '_通用', '_其它', '_其他', '_杂项'])
            
            # 注意这里解包的变量变成了 existing_tags
            for file_path, existing_tags in all_files_info:
                if getattr(self, '_cancel_flag', False): break
                basename = os.path.basename(file_path)
                base_norm = normalize_string(basename)
                file_matches = []
                
                for target_tag, syn_patterns in compiled_syn_dict.items():
                    for pat in syn_patterns:
                        primary_sig = pat["primary"]
                        valid_secondaries = pat["valid_secondaries"]
                        
                        if not all(word in base_norm for word in primary_sig):
                            continue
                            
                        matched_words = set(primary_sig)
                        
                        if valid_secondaries:
                            sec_matched = False
                            for sec_sig in valid_secondaries:
                                if all(word in base_norm for word in sec_sig):
                                    sec_matched = True
                                    matched_words.update(sec_sig)
                            
                            if not sec_matched:
                                continue 
                                
                        file_matches.append((target_tag, frozenset(matched_words)))
                        
                if file_matches:
                    final_tags = set()
                    for tag, words in file_matches:
                        is_subset = False
                        for other_tag, other_words in file_matches:
                            if tag != other_tag and words < other_words:
                                is_subset = True
                                break
                        if not is_subset:
                            final_tags.add(tag)
                    
                    prefix_groups = {}
                    for tag in final_tags:
                        prefix = tag.split('_')[0] if '_' in tag else tag
                        if prefix not in prefix_groups:
                            prefix_groups[prefix] = []
                        prefix_groups[prefix].append(tag)
                        
                    limited_final_tags = set()
                    for prefix, tags in prefix_groups.items():
                        tags.sort(key=lambda x: (-len(x), x))
                        limited_final_tags.update(tags[:3])
                
                    if limited_final_tags:
                        specific_tags = {t for t in limited_final_tags if not is_generic_tag(t)}
                        generic_tags = {t for t in limited_final_tags if is_generic_tag(t)}
                        
                        final_tags_to_apply = set()
                        
                        if specific_tags:
                            final_tags_to_apply = specific_tags
                        else:
                            # 变量 existing_tags 是集合，如果非空表示已有标签
                            if not existing_tags:
                                final_tags_to_apply = generic_tags
                            else:
                                pass
                            
                        if final_tags_to_apply:
                            # 【核心性能优化：量子差集计算】
                            # 集合减法：只保留那些准备要打、但文件目前还【没有】的标签
                            tags_to_add = final_tags_to_apply - existing_tags
                            
                            # 只有在确切存在需要新增的标签时，才将其编入执行队列
                            if tags_to_add:
                                combo_key = ", ".join(sorted(tags_to_add))
                                if combo_key not in tag_combo_to_files:
                                    tag_combo_to_files[combo_key] = []
                                tag_combo_to_files[combo_key].append(file_path)
                                tagged_count += 1
                        
            if getattr(self, '_cancel_flag', False):
                return {"success": False, "msg": self._t('batch_cancelled')}
                        
            if tagged_count == 0:
                msg = self._t('info_no_match_name')
                self.log_message(self._t('log_ucs_name_cancel', msg), "INFO")
                return {"success": False, "msg": msg}
                
            # 【高维优化 2：生成智能批处理指令】
            all_commands = []
            MAX_CHUNK_LEN = 4000
            for combo_tags, file_list in tag_combo_to_files.items():
                current_chunk = []
                current_len = 0
                for fp in file_list:
                    current_chunk.append(fp)
                    current_len += len(fp) + 1 
                    
                    if current_len >= MAX_CHUNK_LEN:
                        file_list_str = "|".join(current_chunk)
                        safe_tags = combo_tags.replace("'", "''")
                        safe_file_list_str = file_list_str.replace("'", "''")
                        all_commands.append(f"    tag '{safe_tags}', '{safe_file_list_str}', 1, ',';")
                        current_chunk = []
                        current_len = 0
                
                if current_chunk:
                    file_list_str = "|".join(current_chunk)
                    safe_tags = combo_tags.replace("'", "''")
                    safe_file_list_str = file_list_str.replace("'", "''")
                    all_commands.append(f"    tag '{safe_tags}', '{safe_file_list_str}', 1, ',';")
            
            # 【高维优化 3：量子分批与呼吸缓冲，彻底告别卡死】
            BATCH_SIZE = 15
            sent_cmds = 0
            for i in range(0, len(all_commands), BATCH_SIZE):
                if getattr(self, '_cancel_flag', False): break
                batch_cmds = all_commands[i : i + BATCH_SIZE]
                
                script_content = '"AutoRun"\n' + "\n".join(batch_cmds)
                
                temp_script = os.path.join(tempfile.gettempdir(), f"xy_helper_batch_ucs_{i}.xys")
                with open(temp_script, "w", encoding="utf-16") as f:
                    f.write(script_content)
                
                temp_safe = temp_script.replace("'", "''")
                cmd_str = f'"{exe_path}" /feed="::load \'{temp_safe}\', \'AutoRun\';"'
                subprocess.Popen(cmd_str)
                
                sent_cmds += len(batch_cmds)
                self._update_progress(sent_cmds, total_files)
                time.sleep(0.3)
                
            if getattr(self, '_cancel_flag', False):
                return {"success": False, "msg": self._t('batch_cancelled')}
            
            try:
                if os.path.exists(sel_file): os.remove(sel_file)
            except: pass
            
            self.log_message(self._t('log_ucs_name_ok', tagged_count), "INFO")
            return {"success": True, "count": tagged_count}
            
        except Exception as e:
            self.log_message(self._t('log_ucs_name_err', str(e)), "ERROR")
            return {"success": False, "msg": str(e)}
      
    # ==========================================
    # --- AI 大模型通信模块 (调用本地 Ollama) ---
    # ==========================================
    def _call_ollama(self, prompt, system_prompt=""):
        cfg = self.get_config()
        api_url = cfg.get('ai_api', 'http://localhost:11434/api/generate')
        model = cfg.get('ai_model', 'qwen2.5:0.5b')
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": 16384
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt
            
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(api_url, data=data, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                return json.loads(res.read().decode('utf-8')).get('response', '').strip()
        except Exception as e:
            return None

    def ai_batch_process(self, xy_path, mode, domain="通用"):
        import tempfile
        import time
        import re
        import os
        import json
        import subprocess
        
        self.log_message(self._t('log_ai_start', mode), "INFO")
        try:
            exe_path = self._normalize_xy_path(xy_path)
            if not os.path.exists(exe_path): return {"success": False, "msg": self._t('err_xy_not_found')}
            
            lang = self.get_config().get('lang', 'zh-CN')
            is_zh = False  # [修改] 强制关闭中文模式，这会自动触发后续所有AI系统提示词和机器翻译的回退保护机制采用英文
            
            if is_zh:
                lang_instruction = "简体中文（中国大陆习惯，绝对禁止保留英文原词）"
            else:
                lang_instruction = "English (Strictly output English words ONLY)"
            
            temp_dir = tempfile.gettempdir()
            unique_id = str(int(time.time() * 1000))
            sel_file = os.path.join(temp_dir, f"xy_sel_{unique_id}.txt")
            safe_sel_file = sel_file.replace("'", "''")
            subprocess.Popen(f'"{exe_path}" /feed="::writefile(\'{safe_sel_file}\', get(\'SelectedItemsPathNames\', \'|\'), \'o\', \'tu\');"')
            
            wait_time, sel_content = 0, ""
            while wait_time < 30: 
                if os.path.exists(sel_file):
                    try:
                        with open(sel_file, 'r', encoding='utf-16', errors='ignore') as f: sel_content = f.read().strip()
                        if sel_content or wait_time > 10: break 
                    except: pass
                time.sleep(0.1); wait_time += 1
            try:
                if os.path.exists(sel_file): os.remove(sel_file)
            except: pass
            
            if not sel_content: return {"success": False, "msg": self._t('err_no_valid')}
            # [修改] 将 isfile 更改为 exists，这样无论是文件还是文件夹都能被提取名称并被成功打上标签
            all_files = [i for item in sel_content.split('|') if (i := item.strip().strip('"').strip("'").strip('\x00')) and os.path.exists(i)]
            if not all_files: return {"success": False, "msg": self._t('err_no_valid')}
                
            self._cancel_flag = False
            total_files = len(all_files)
            self._update_progress(0, total_files, mode='ai')
            
            merged_dict = {}
            tag_map = {} 
            
            if mode == 'dict_name':
                merged_file = os.path.join(DATA_DIR, "ucs_dict_merged.json")
                if os.path.exists(merged_file):
                    try:
                        with open(merged_file, 'r', encoding='utf-8') as f:
                            merged_dict = json.load(f)
                            
                            for cat, pairs in merged_dict.items():
                                for pair in pairs:
                                    en_t, zh_t = pair.split('|', 1)
                                    en_t, zh_t = en_t.strip(), zh_t.strip()
                                    target_t = zh_t if is_zh else en_t
                                    
                                    tag_map[en_t] = target_t
                                    tag_map[zh_t] = target_t
                                    tag_map[en_t.lower()] = target_t
                                    tag_map[zh_t.lower()] = target_t
                                    tag_map[en_t.replace('_', '').replace(' ', '').lower()] = target_t
                                    tag_map[zh_t.replace('_', '').replace(' ', '').lower()] = target_t
                    except Exception: pass
                if not tag_map:
                    return {"success": False, "msg": "未找到 ucs_dict_merged.json 字典文件，或格式不正确"}

            FORBIDDEN_TAGS = {
                "音", "声音", "录音", "文本", "图像", "照片", "音频", "视频", 
                "媒体", "宇体", "字体", "矢量图", "网页", "文档", "压缩包", 
                "可执行", "文件夹", "失聪", "失聪声", "底噪", "听力丧失", "标签", "音乐", "音效",
                "聲音", "錄音", "圖像", "音訊", "視訊", "媒體", "宇體", "字體", "字型", "向量圖", 
                "網頁", "文件", "壓縮檔", "執行檔", "資料夾", "失聰", "失聰聲", "聽力喪失", "標籤", "音樂",
                "sound", "audio", "video", "media", "text", "image", "photo", "font", "vector", "web", 
                "document", "archive", "executable", "folder", "deaf", "hearing loss", "tag", "tags", 
                "music", "sfx", "sound effect", "noise"
            }
            forbidden_str = "、".join(FORBIDDEN_TAGS)

            static_sys_prompt = ""
            if mode == 'auto_name':
                static_sys_prompt = f"你是一个专业的【{domain}】领域的打标签专家。必须将提取出的核心标签【全部彻底翻译为{lang_instruction}】！\n\n【严格规则】：\n1. 绝不允许保留原文件中的扩展名。\n2. 翻译必须符合“{domain}”的行业语境，禁止生硬机翻。\n3. 只输出2到4个精简的标签词，必须严格用英文逗号(,)分隔。\n4. 绝对禁止生成类似“第一章”、“第8集”、“01”等无意义的数字或序号标签。\n5. 绝对禁止输出以下无意义的大类或错译标签：{forbidden_str}。"
            elif mode == 'auto_name_en_zh':
                static_sys_prompt = f"你是一个专业的【{domain}】领域的打标签专家。你必须提取出代表核心概念的标签，并同时提供准确的【英文】和【简体中文】。绝对禁止保留原文件中的扩展名。\n\n【极其严格的格式规则】：\n1. 格式必须严格为：英文词@@中文词\n2. 只输出 2 到 4 个组合，必须用英文逗号(,)分隔。\n3. 示例输出：Rain@@雨声, Heavy@@沉重"
            elif mode == 'auto_content':
                static_sys_prompt = f"你是一个冷酷无情的关键词提取机器。你必须将提取的核心标签【全部彻底翻译为{lang_instruction}】！\n\n【极度严格规则，违背将被毁灭】：\n1. 词汇必须极度精简！必须是【短名词】（如“工作区”、“标签树”），绝对禁止拼接长句、动宾短语或造词（如“可视化状态转换”是严重错误的）。\n2. 标签字数限制：中文必须在 2 到 4 个汉字之间。\n3. 只输出 3 到 5 个词，必须严格用英文逗号(,)分隔，绝不能连写，不要任何解释。\n4. 绝对禁止输出以下标签：{forbidden_str}。"

            tag_to_files, tagged_count, all_applied_tags = {}, 0, set()

            for file_path in all_files:
                if getattr(self, '_cancel_flag', False): break
                basename = os.path.basename(file_path)
                basename_no_ext = os.path.splitext(basename)[0] 
                
                prompt = ""
                file_sys_prompt = static_sys_prompt
                
                if mode == 'dict_name':
                    categories_list = list(merged_dict.keys())
                    cat_sys_prompt = f"你是一个专业的【音效素材】分类路由器。你需要根据给定的【音效文件名】，推断该声音的来源或发声主体。请从以下音效大类列表中挑选出 1 到 3 个最相关的类别：\n{', '.join(categories_list)}\n\n【严格规则】：只输出大类名称的英文，用英文逗号(,)分隔，绝对禁止输出其他任何多余文字或解释。"
                    cat_prompt = f"音效文件名：【{basename_no_ext}】\n匹配的音效大类："
                    
                    cat_response = self._call_ollama(cat_prompt, cat_sys_prompt)
                    if not cat_response: return {"success": False, "msg": self._t('err_ollama')}
                    
                    selected_cats = []
                    cat_lower_map = {k.lower(): k for k in categories_list}
                    for c in cat_response.split(','):
                        c_clean = c.strip(' \n\r\t。，.,\'"[]*').lower()
                        if c_clean in cat_lower_map and cat_lower_map[c_clean] not in selected_cats:
                            selected_cats.append(cat_lower_map[c_clean])
                            
                    if not selected_cats:
                        tagged_count += 1
                        self._update_progress(tagged_count, total_files, mode='ai')
                        continue
                        
                    mini_dict_lines = []
                    for cat in selected_cats:
                        tags_in_cat = [f"{p.split('|')[0].strip()}({p.split('|')[1].strip()})" for p in merged_dict[cat]]
                        mini_dict_lines.append(f"[{cat}]: {', '.join(tags_in_cat)}")
                    mini_dict_str = "\n".join(mini_dict_lines)
                    
                    file_sys_prompt = f"""你是一个极其严谨的【音效素材】标签匹配专家。请记住：你正在处理的是【声音/音效文件】，请务必从发声源、动作、材质等听觉维度去理解文件名。
请阅读以下动态提取的【双语音效字典库】，为给定的音效寻找最契合的标签。

【双语音效字典库】(格式为 英文(中文))：
{mini_dict_str}

【极度严格匹配规则】（违背将被重罚）：
1. 必须有发声证据，严禁脑补：必须基于文件名中实际存在的【发声体/名词】进行匹配。绝对禁止挑选文件名中不存在的细分场景词条（例如：文件名仅为"Rain"，绝对不能瞎猜它打在塑料上而匹配"Rain_Plastic"）。
2. 发声修饰词辅助：文件名中的修饰词（如具体的发声动作、撞击的材质、发声体表面）必须与词条细分项严格对应时，才能提取具体细分标签。
3. 宁泛勿错（兜底机制）：如果文件名只有基础发声物，没有具体的发声细节与修饰词，请【强制优先】匹配带有“_Misc”、“_其它”、“_General”、“_通用”后缀的泛用音效词条，或者只匹配基础词。
4. 宁缺毋滥：最多提取 1 到 3 个核心标签。如果字典中完全没有合理的匹配项，请直接输出“无”。
5. 格式规范：绝对禁止自己发明新词！必须严格原样摘取上述字典库中存在的词条，输出【英文部分】或【中文部分】均可，并用英文逗号(,)分隔。"""

                    prompt = f"当前仅处理这 1 个音效文件。\n音效文件名：【{basename_no_ext}】\n请输出匹配的标签(用英文逗号分隔)："
                    
                elif mode == 'auto_name':
                    prompt = f"当前仅对这 1 个文件进行打标。\n输入: 【{basename_no_ext}】\n输出纯标签:"
                elif mode == 'auto_name_en_zh':
                    prompt = f"当前仅对这 1 个文件进行打标。\n输入: 【{basename_no_ext}】\n输出:"
                elif mode == 'auto_content':
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: 
                            full_text = f.read()
                            import re
                            clean_text = re.sub(r'\s+', ' ', full_text).strip()
                            if len(clean_text) <= 2300:
                                content = clean_text
                            else:
                                content = clean_text[:1500] + "\n...[中间部分已折叠]...\n" + clean_text[-800:]
                        prompt = f"请阅读以下经过压缩的文档片段，直接提取出 3 到 5 个最能代表核心概念的【简短名词】（请原样摘取，不要自己造长词）。\n内容片段：\n{content}\n\n请直接输出纯标签(用英文逗号分隔)："
                    except: 
                        tagged_count += 1
                        self._update_progress(tagged_count, total_files, mode='ai')
                        continue
                else: continue
                
                ai_response = self._call_ollama(prompt, file_sys_prompt)
                if not ai_response: return {"success": False, "msg": self._t('err_ollama')}
                
                if mode in ['auto_name', 'auto_content']:
                    if is_zh:
                        if re.search(r'[a-zA-Z]{3,}', ai_response):
                            trans_prompt = f"请把以下文字中的英文单词全部翻译为{lang_instruction}，已经是中文的保持不变。只输出最终的纯中文标签，严格用英文逗号(,)分隔，绝不能加任何多余废话：\n{ai_response}"
                            sys_role = f"你是一个无情的翻译机器，只输出逗号分隔的中文词语，绝对禁止输出任何英文字母或解释性对话。"
                            trans_res = self._call_ollama(trans_prompt, sys_role)
                            if trans_res: ai_response = trans_res
                    else:
                        if re.search(r'[\u4e00-\u9fa5]', ai_response):
                            trans_prompt = f"Translate the following text strictly into English. Keep the comma separation format:\n{ai_response}"
                            sys_role = f"You are a strict translator. Output ONLY English words separated by commas. Absolutely NO Chinese characters."
                            trans_res = self._call_ollama(trans_prompt, sys_role)
                            if trans_res: ai_response = trans_res
                
                normalized_response = re.sub(r'[，、；;\n|:：]|(\s*-\s*)', ',', ai_response)
                filler_words = ["翻译", "如下", "以下", "标签是", "这里是", "这些是", "these are", "here are", "translated", "输出", "分类", "大类"]
                
                current_file_tags = []
                
                for t in normalized_response.split(','):
                    raw_tag = t.strip(' \n\r\t。，.,\'"[]*')
                    if not raw_tag: continue
                    
                    clean_tag = raw_tag.strip(' -_()（）')
                    if clean_tag.lower() in ["无", "none", "null", "no", "n/a"]: continue
                    
                    if mode == 'dict_name':
                        resolved_tag = None
                        if '|' in clean_tag:
                            try:
                                clean_tag = clean_tag.split('|')[1 if is_zh else 0].strip()
                            except: pass
                            
                        match = re.search(r'([^\(（]+)[\(（]([^\)）]+)[\)）]?', raw_tag)
                        test_tags = [match.group(1).strip(), match.group(2).strip()] if match else [raw_tag, clean_tag]
                        
                        for test_t in test_tags:
                            test_t_c = test_t.strip(' -_()（）')
                            if not test_t_c: continue
                            if test_t_c in tag_map: resolved_tag = tag_map[test_t_c]; break
                            if test_t_c.lower() in tag_map: resolved_tag = tag_map[test_t_c.lower()]; break
                            no_u = test_t_c.replace('_', '').replace(' ', '').lower()
                            if no_u in tag_map: resolved_tag = tag_map[no_u]; break
                        
                        if not resolved_tag: continue 
                        clean_tag = resolved_tag
                    else:
                        if not clean_tag: continue
                        if is_zh and len(clean_tag) > 5: continue
                        if not is_zh and len(clean_tag) > 20: continue
                        if re.fullmatch(r'[0-9\.\-\_]+', clean_tag): continue
                        if re.fullmatch(r'第?[0-9一二三四五六七八九十百千万]+[章回节部分集季]', clean_tag): continue
                        if re.fullmatch(r'第[0-9一二三四五六七八九十百千万]+', clean_tag): continue
                        if any(fw in clean_tag.lower() for fw in filler_words): continue
                        if clean_tag.lower() in FORBIDDEN_TAGS: continue
                        
                        if mode != 'auto_name_en_zh': 
                            if is_zh:
                                if re.search(r'[a-zA-Z]{3,}', clean_tag) and not re.search(r'[\u4e00-\u9fa5]', clean_tag): continue 
                                if re.fullmatch(r'[a-zA-Z0-9\s\-_!@#$%^&*()]+', clean_tag): continue 
                            else:
                                if re.search(r'[\u4e00-\u9fa5]', clean_tag): continue
                    
                    if clean_tag not in current_file_tags:
                        current_file_tags.append(clean_tag)
                
                for clean_tag in current_file_tags[:5]:
                    if clean_tag not in tag_to_files: tag_to_files[clean_tag] = []
                    tag_to_files[clean_tag].append(file_path)
                    all_applied_tags.add(clean_tag)
                
                tagged_count += 1
                self._update_progress(tagged_count, total_files, mode='ai')
                time.sleep(0.1) 

            if getattr(self, '_cancel_flag', False):
                return {"success": False, "msg": self._t('batch_cancelled')}

            if not tag_to_files: return {"success": False, "msg": "AI 未能生成有效的标签（或已被系统过滤机制拦截）"}
                
            MAX_CHUNK_LEN = 6000
            sent_cmds = 0
            for tag, file_list in tag_to_files.items():
                if getattr(self, '_cancel_flag', False): break
                current_chunk = []
                current_len = 0
                for fp in file_list:
                    current_chunk.append(fp)
                    current_len += len(fp) + 1 
                    if current_len >= MAX_CHUNK_LEN:
                        file_list_str = "|".join(current_chunk)
                        xy_tag = tag.split('@@')[0] if '@@' in tag else tag
                        safe_tag = xy_tag.replace("'", "''")
                        safe_file_list_str = file_list_str.replace("'", "''")
                        tag_cmd = f"::tag '{safe_tag}', '{safe_file_list_str}', 1, 0;"
                        subprocess.Popen(f'"{exe_path}" /feed="{tag_cmd}"')
                        sent_cmds += 1
                        self._update_progress(sent_cmds, total_files, mode='cmd')
                        time.sleep(0.05) 
                        if getattr(self, '_cancel_flag', False): break
                        current_chunk = []
                        current_len = 0
                
                if getattr(self, '_cancel_flag', False): break
                if current_chunk:
                    file_list_str = "|".join(current_chunk)
                    xy_tag = tag.split('@@')[0] if '@@' in tag else tag
                    safe_tag = xy_tag.replace("'", "''")
                    safe_file_list_str = file_list_str.replace("'", "''")
                    tag_cmd = f"::tag '{safe_tag}', '{safe_file_list_str}', 1, 0;"
                    subprocess.Popen(f'"{exe_path}" /feed="{tag_cmd}"')
                    sent_cmds += 1
                    self._update_progress(sent_cmds, total_files, mode='cmd')
                    time.sleep(0.05)
            
            if getattr(self, '_cancel_flag', False):
                return {"success": False, "msg": self._t('batch_cancelled')}
            
            self.log_message(self._t('log_ai_ok'), "INFO")
            return {"success": True, "count": len(all_files), "tags": list(all_applied_tags), "mode": mode}
        except Exception as e:
            self.log_message(self._t('log_ai_err', str(e)), "ERROR")
            return {"success": False, "msg": str(e)}
    
    def read_clipboard_safe(self):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW 
            result = subprocess.check_output(['powershell', '-NoProfile', '-command', 'Get-Clipboard'], startupinfo=startupinfo, text=True, timeout=3)
            return result.strip()
        except Exception as e:
            self.log_message(self._t('log_clip_err', str(e)), "ERROR")
            return ""

    def update_xy_labels(self, xy_path):
        try:
            exe_path = self._normalize_xy_path(xy_path)
            if not exe_path or not os.path.exists(exe_path):
                return {"success": False, "msg": self._t('err_xy_not_found')}
            data_dir = os.path.join(os.path.dirname(exe_path), "Data")
            tag_file = os.path.join(data_dir, "tag.dat")
            if not os.path.exists(tag_file):
                return {"success": False, "msg": self._t('log_data_not_found')}
            content = ""
            try:
                with open(tag_file, 'r', encoding='utf-16') as f: content = f.read()
            except:
                with open(tag_file, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
            labels = []
            lines = content.splitlines()
            found_labels_header = False
            for line in lines:
                line = line.strip()
                if not line: continue
                if line == "Labels:":
                    found_labels_header = True
                    continue
                if found_labels_header:
                    parts = line.split(";")
                    for p in parts:
                        if not p: continue
                        segments = p.split("|")
                        if len(segments) >= 3:
                            name = segments[0]
                            bg_color = segments[2]
                            if not bg_color.startswith("#"): bg_color = "#" + bg_color
                            labels.append({"n": name, "c": bg_color})
                    break 
            if labels: return {"success": True, "labels": labels}
            else: return {"success": False, "msg": self._t('log_tag_dat_err')}
        except Exception as e:
            return {"success": False, "msg": str(e)}

    def open_manual(self, lang):
        docs_dir = os.path.join(BASE_DIR, "Docs")
        if lang == "zh-TW":
            filename = "manual_zh-TW.html"
        elif lang == "en":
            filename = "manual_en.html"
        else:
            filename = "manual_zh-CN.html"
            
        filepath = os.path.join(docs_dir, filename)
        try:
            if os.path.exists(filepath):
                os.startfile(filepath) 
                return {"success": True}
            else:
                self.log_message(self._t('log_doc_not_found', filepath), "ERROR")
                return {"success": False}
        except Exception as e:
            self.log_message(self._t('log_doc_err', str(e)), "ERROR")
            return {"success": False}

    def open_url(self, url):
            try:
                webbrowser.open(url)
                return {"success": True}
            except Exception as e:
                self.log_message(self._t('log_url_err', str(e)), "ERROR")
                return {"success": False}

    def toggle_pin(self, current_state):
        def _pin():
            w = webview.windows[0]
            w.on_top = not current_state
        threading.Thread(target=_pin).start()
        return not current_state

# ==========================================
# 3. 原生 Web 前端 (HTML/CSS/JS)
# ==========================================
html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <style>
        :root { 
            /* Modern Colors & Standardized Radius */
            --primary: #3B82F6; --green: #10B981; --orange: #F59E0B; --red: #EF4444; --blue: #3B82F6; 
            --radius: 6px;
            
            /* Dark Theme Variables - Modern Slate/Zinc tones, avoiding pure black */
            --bg-main: #1A1B1E; 
            --bg-panel: #25262B; 
            --bg-input: #141517; 
            --bg-btn: #2C2E33; 
            --bg-btn-hover: #3B3E45; 
            --bg-menu: #25262B; 
            --text-main: #D7DAE0; 
            --text-muted: #8B92A5; 
            --border-color: #373A40; 
            --ws-bar-bg: #1A1B1E; 
            --loader-bg: #1A1B1E;
            
            --btn-search-bg: #1E293B; --btn-search-border: #334155; --btn-search-text: #38BDF8;
            --btn-add-bg: #064E3B; --btn-add-border: #065F46; --btn-add-text: #34D399;
            --btn-read-bg: #451A03; --btn-read-border: #78350F; --btn-read-text: #FBBF24;
            --btn-clear-bg: #450A0A; --btn-clear-border: #7F1D1D; --btn-clear-text: #FCA5A5;

            /* --- 搜索与悬浮主题色 (Dark) --- */
        --hl-tag: #FFD700;
        --hl-tag-hover: #FFF200;
        --hl-remark: #84CC16;
        --hl-remark-hover: #BEF264;
        --hl-desc: #38BDF8;
        --hl-desc-hover: #7DD3FC;

        /* --- 标签激活状态映射 (Dark) --- */
        --bg-and: #3B82F6; --text-and: #FFFFFF; --hover-and: #60A5FA;
        --bg-or: #10B981; --text-or: #FFFFFF; --hover-or: #34D399;
        --bg-not: #EF4444; --text-not: #FFFFFF; --hover-not: #F87171;
    }

    body[data-theme="light"] {
            --primary: #2563EB; --green: #059669; --orange: #D97706; --red: #DC2626; --blue: #2563EB;
            
            /* Light Theme Variables - Soft off-whites, avoiding pure white for backgrounds */
            --bg-main: #F4F5F7; 
            --bg-panel: #FCFCFD; 
            --bg-input: #EDEEF0; 
            --bg-btn: #F1F3F5; 
            --bg-btn-hover: #E9ECEF; 
            --bg-menu: #FCFCFD; 
            --text-main: #2B2D31; 
            --text-muted: #868E96; 
            --border-color: #DEE2E6; 
            --ws-bar-bg: #F4F5F7; 
            --loader-bg: #F4F5F7;
            
            --btn-search-bg: #EFF6FF; --btn-search-border: #BFDBFE; --btn-search-text: #2563EB;
            --btn-add-bg: #ECFDF5; --btn-add-border: #A7F3D0; --btn-add-text: #059669;
            --btn-read-bg: #FFFBEB; --btn-read-border: #FDE68A; --btn-read-text: #D97706;
            --btn-clear-bg: #FEF2F2; --btn-clear-border: #FECACA; --btn-clear-text: #DC2626;

            /* --- 搜索与悬浮主题色 (Light) --- */
            --hl-tag: #D97706;       /* 深琥珀金，保证白底高对比度 */
            --hl-tag-hover: #B45309;
            --hl-remark: #65A30D;    /* 深黄绿色 */
            --hl-remark-hover: #4D7C0F;
            --hl-desc: #0284C7;      /* 深天蓝色 */
            --hl-desc-hover: #0369A1;

            /* --- 标签激活状态映射 (Light 恢复高饱和度 + 悬浮提亮变色) --- */
            /* 悬浮时不仅恢复 1.0 透明度，还将 RGB 映射为与 Dark 模式同款的“明亮发光色” */
            --bg-and: rgba(59, 130, 246, 0.85); --text-and: #FFFFFF; --hover-and: rgba(96, 165, 250, 1.0);
            --bg-or: rgba(16, 185, 129, 0.85); --text-or: #FFFFFF; --hover-or: rgba(52, 211, 153, 1.0);
            --bg-not: rgba(239, 68, 68, 0.85); --text-not: #FFFFFF; --hover-not: rgba(248, 113, 113, 1.0);
            }
        
        body { margin: 0; padding: 0; background: var(--bg-main); color: var(--text-main); font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 13px; height: 100vh; box-sizing: border-box; display: flex; flex-direction: column; overflow: hidden; user-select: none; -webkit-user-select: none; }
        
        /* Modern Scrollbar */
        ::-webkit-scrollbar { width: 6px; height: 6px; display: none; }
        .tree-container::-webkit-scrollbar, .comp-body::-webkit-scrollbar, textarea::-webkit-scrollbar, .ws-tabs-scroll::-webkit-scrollbar, .global-dropdown::-webkit-scrollbar { display: block; }
        ::-webkit-scrollbar-track { background: transparent; border-radius: 10px; }
        ::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

        /* --- 搜索栏增强样式 --- */
        #tag-search-results {
            max-height: 320px; 
            overflow-y: auto; 
            display: flex; 
            flex-direction: column; 
            gap: 4px; /* 【修复】增加行距 */
            padding-right: 4px;
        }
        
        /* 强制覆盖为现代滚动条，告别原生白条 */
        #tag-search-results::-webkit-scrollbar { width: 6px; display: block !important; }
        #tag-search-results::-webkit-scrollbar-track { background: transparent; border-radius: 6px; }
        #tag-search-results::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 6px; }
        #tag-search-results::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }
        
        .search-result-item {
            padding: 8px 12px;     /* 【修复】左右加宽，上下撑开 */
            min-height: 32px;      /* 【修复】强制最小高度，彻底杜绝文字被裁切 */
            box-sizing: border-box;
            cursor: pointer;
            border-radius: var(--radius);
            /* 核心修复：开启 Flex 弹性排版 */
            display: flex; 
            align-items: center;
            justify-content: flex-start;
            font-size: 13px;
            color: var(--text-main);
            transition: background 0.1s;
        }
        
        /* 左侧：标签路径（当空间不足时自动收缩并显示省略号） */
        .search-path-col {
            opacity: 0.55;
            margin-right: 6px;
            font-size: 11px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            flex-shrink: 1; /* 允许被压缩 */
            min-width: 0;   /* 必须属性，防止 Flex 子元素撑破父级 */
            line-height: 1.2;
        }
        
        /* 右侧：标签主体（享有最高显示优先级，绝不压缩） */
        .search-tag-col {
            white-space: nowrap;
            flex-shrink: 0; /* 绝对禁止压缩 */
            line-height: 1.2;
        }

        /* 斑马纹 */
        .search-result-item:nth-child(even) { background-color: rgba(128, 128, 128, 0.05); }
        
        /* 鼠标悬浮与键盘选中状态 */
        .search-result-item:hover, .search-result-item.selected {
            background-color: var(--primary) !important;
            color: #fff !important;
        }
        
        /* --- 搜索匹配动态高亮系统 --- */
        .hl-match { font-weight: bold; color: var(--hl-tag) !important; }
        .search-result-item:hover .hl-match, .search-result-item.selected .hl-match { color: var(--hl-tag-hover) !important; text-shadow: none; }
        
        .hl-remark { font-weight: bold; color: var(--hl-remark) !important; }
        .search-result-item:hover .hl-remark, .search-result-item.selected .hl-remark { color: var(--hl-remark-hover) !important; }
        
        .hl-desc { font-weight: bold; color: var(--hl-desc) !important; }
        .search-result-item:hover .hl-desc, .search-result-item.selected .hl-desc { color: var(--hl-desc-hover) !important; }

        /* --- 恢复标签按钮与分组的默认悬浮效果 (主题蓝) --- */
        .tag-btn:hover { border-color: var(--primary) !important; color: var(--primary) !important; box-shadow: none; }
        .group-header:hover .group-title, .group-header:hover .group-arrow { color: inherit !important; }
        
        .search-result-item {
            padding: 6px 10px;
            cursor: pointer;
            border-radius: var(--radius);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            font-size: 13px;
            color: var(--text-main);
            transition: background 0.1s;
        }
        /* 斑马纹 */
        .search-result-item:nth-child(even) { background-color: rgba(128, 128, 128, 0.05); }
        
        /* 鼠标悬浮与键盘选中状态 */
        .search-result-item:hover, .search-result-item.selected {
            background-color: var(--primary) !important;
            color: #fff !important;
        }
        
        /* 匹配高亮：默认主色，被选中时变白并发光 */
        .hl-match { font-weight: bold; color: var(--primary); }
        .search-result-item:hover .hl-match, .search-result-item.selected .hl-match { color: #fff !important; text-shadow: 0 0 3px rgba(255,255,255,0.6); }
        
        /* 备注高亮：默认橙黄，被选中时保持金黄 */
        .hl-remark { color: var(--orange); font-weight: bold; }
        .search-result-item:hover .hl-remark, .search-result-item.selected .hl-remark { color: #FFD700 !important; }

        #app-loader { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: var(--loader-bg); z-index: 9999999; display: flex; align-items: center; justify-content: center; color: var(--primary); font-size: 16px; font-weight: bold; letter-spacing: 2px; transition: opacity 0.4s; }
        .main-content { padding: 8px 12px; display: flex; flex-direction: column; flex: 1; overflow: hidden; opacity: 0; transition: opacity 0.5s ease-out; gap: 8px;}
        .main-content.ready { opacity: 1; }

        .top-bar { display: flex; gap: 6px; align-items: stretch; flex-shrink: 0; margin-bottom: 2px;}
        
        .syntax-wrapper { 
            width: 70%; min-height: 85px; min-width: 150px; display: flex; flex-shrink: 0; 
            resize: both; overflow: hidden; border: 1px solid var(--border-color); border-radius: var(--radius); background: var(--bg-input);
        }
        textarea#syntax-input {
            flex: 1; width: 100%; height: 100%; background: transparent; color: var(--primary);
            border: none; padding: 8px 10px; box-sizing: border-box; font-family: monospace; font-size: 12px; line-height: 1.5;
            resize: none; outline: none; white-space: pre-wrap; word-break: break-all;
        }

        button, .action-btn, .comp-btn, .comp-lbl-btn, .ws-tab, .tag-btn, .group-header, .menu-item, .tool-btn, .hist-toggle, .settings-btn { cursor: default !important; }
        svg { pointer-events: none; } 

        .action-buttons { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; flex: 1; min-width: 60px; }
        .action-btn { width: 100%; height: 100%; border-radius: var(--radius); display: flex; align-items: center; justify-content: center; padding: 0; transition: filter 0.2s; font-size: 12px;}
        .action-btn:hover { filter: brightness(1.1); }
        .action-btn svg { width: 18px; height: 18px; }
        
        .btn-search { background: var(--btn-search-bg); border: 1px solid var(--btn-search-border); color: var(--btn-search-text); }
        .btn-add { background: var(--btn-add-bg); border: 1px solid var(--btn-add-border); color: var(--btn-add-text); }
        .btn-read { background: var(--btn-read-bg); border: 1px solid var(--btn-read-border); color: var(--btn-read-text); }
        .btn-clear { background: var(--btn-clear-bg); border: 1px solid var(--btn-clear-border); color: var(--btn-clear-text); }

        .comp-module { background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: var(--radius); display: flex; flex-direction: column; flex-shrink: 0; height: 140px; min-height: 35px; resize: vertical; overflow: hidden; position: relative; margin-bottom: 2px;}
        .comp-module.collapsed { height: 35px !important; resize: none; overflow: hidden; }
        .comp-tabs { display: flex; align-items: center; border-bottom: 1px solid var(--border-color); background: var(--ws-bar-bg); height: 35px; flex-shrink: 0; }
        .comp-tab { padding: 0 14px; color: var(--text-muted); border-right: 1px solid var(--border-color); font-size: 12px; font-weight: bold; height: 100%; display: flex; align-items: center; transition: background 0.15s;}
        .comp-tab:hover { color: var(--primary); background: rgba(128,128,128,0.1); }
        .comp-tab.active { color: var(--primary); background: var(--bg-panel); border-bottom: 2px solid var(--primary); }
        .comp-body { padding: 10px; display: none; flex-direction: column; gap: 8px; flex: 1; overflow-y: auto; overflow-x: hidden; }
        .comp-body.active { display: flex; }
        
        .comp-btn-group { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
        .comp-btn { background: var(--bg-btn); color: var(--text-main); border: 1px solid var(--border-color); padding: 4px 10px; border-radius: var(--radius); font-size: 12px; font-weight: bold; position: relative; transition: 0.1s; }
        .comp-btn:hover { background: var(--bg-btn-hover); color: var(--primary); border-color: var(--primary); }
        
        /* 面板的包含(s1)映射为绿色，排除(s2)映射为红色 */
        .comp-btn.s1 { background: var(--bg-or) !important; color: var(--text-or) !important; border-color: var(--bg-or) !important; } 
        .comp-btn.s2 { background: var(--bg-not) !important; color: var(--text-not) !important; border-color: var(--bg-not) !important; } 
        .comp-btn.s1:hover { background: var(--hover-or) !important; border-color: var(--hover-or) !important; color: var(--text-or) !important; }
        .comp-btn.s2:hover { background: var(--hover-not) !important; border-color: var(--hover-not) !important; color: var(--text-not) !important; }
        
        .comp-lbl-btn { display: inline-flex; align-items: center; gap: 6px; background: var(--bg-btn); color: var(--text-main); border: 1px solid var(--border-color); padding: 4px 10px; border-radius: var(--radius); font-size: 12px; }
        .comp-lbl-btn.active { border-color: var(--primary); background: var(--bg-btn-hover); color: var(--primary); }
        .lbl-dot { width: 10px; height: 10px; border-radius: 50%; box-shadow: 0 0 2px rgba(0,0,0,0.3);}

        input, select { background: var(--bg-input); color: var(--text-main); border: 1px solid var(--border-color); padding: 6px 10px; border-radius: var(--radius); outline: none; font-family: inherit; font-size: 12px; cursor: text !important;}
        input:focus, select:focus { border-color: var(--primary); }
        select { cursor: default !important; }

        .input-group { position: relative; display: flex; width: 100%; max-width: 500px; }
        .input-group input { flex: 1; border-radius: var(--radius) 0 0 var(--radius); }
        .hist-toggle { background: var(--bg-btn); border: 1px solid var(--border-color); border-left: none; color: var(--text-muted); border-radius: 0 var(--radius) var(--radius) 0; width: 28px; display: flex; align-items: center; justify-content: center; }
        .hist-toggle:hover { background: var(--bg-btn-hover); color: var(--primary); }
        
        .global-dropdown { position: absolute; z-index: 99999; background: var(--bg-menu); border: 1px solid var(--border-color); border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); display: none; flex-direction: column; max-height: 320px; overflow-x: hidden; overflow-y: auto; padding: 4px; box-sizing: border-box; }
        .hist-item { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--text-main); border-radius: var(--radius); cursor: pointer; padding: 0 10px; width: 100%; box-sizing: border-box; margin-bottom: 2px;}
        .hist-item:hover { background: var(--bg-btn-hover); color: var(--primary);}
        .hist-item-text { padding: 8px 0px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .hist-del { padding: 8px 10px; color: var(--red); background: transparent; font-size: 16px; font-weight: bold; line-height: 1; transition: 0.2s; cursor: pointer !important; opacity: 0.7; flex-shrink: 0; margin: 0; border-radius: var(--radius);}
        .hist-del:hover { opacity: 1; color: #ff0000; background: rgba(255,0,0,0.1); }

        .builder-row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
        .builder-sel { padding: 4px; border-radius: var(--radius);}
        .builder-tag { background: var(--blue); color: #fff; padding: 2px 8px; border-radius: var(--radius); font-size: 11px; display: inline-flex; align-items: center; gap: 4px; }
        .builder-tag:hover { background: var(--red); }

        .ws-bar { display: flex; align-items: center; gap: 6px; background: var(--ws-bar-bg); padding: 4px 6px; border-radius: var(--radius); border: 1px solid var(--border-color); flex-shrink: 0; min-width: 0; position: relative;}
        .ws-tabs-scroll { display: flex; gap: 6px; flex: 1; overflow-x: auto; flex-wrap: nowrap; scrollbar-width: none; -ms-overflow-style: none; scroll-behavior: smooth; }
        .ws-tabs-scroll::-webkit-scrollbar { display: none; }
        
        .ws-tab { padding: 4px 12px; border: 1px solid transparent; background: var(--bg-btn); color: var(--text-muted); border-radius: var(--radius); font-size: 12px; font-weight: bold; white-space: nowrap; display: flex; align-items: center; justify-content: center; flex-shrink: 0;}
        .ws-tab:hover { filter: brightness(1.05); color: var(--primary); border-color: rgba(128,128,128,0.3);}
        .ws-tab.active { background: var(--primary); color: #fff !important; border-color: var(--primary); }
        
        .ws-add { width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; border-radius: var(--radius); flex-shrink: 0; margin-left: 2px;}
        .btn-plus-icon { color: var(--green); opacity: 0.7; transition: 0.2s; cursor: pointer; }
        .btn-plus-icon:hover { background-color: rgba(76, 175, 80, 0.15) !important; color: var(--green) !important; opacity: 1; }

        .ws-dynamic-area { display: none; align-items: center; padding-left: 6px; margin-left: 2px; border-left: 1px dashed var(--border-color); flex-shrink: 0; gap: 6px;}

        .tool-btn { background: transparent; color: var(--text-muted); border: none; border-radius: var(--radius); width: 28px; height: 28px; display: inline-flex; align-items: center; justify-content: center; padding: 0; flex-shrink: 0;}
        .tool-btn:hover { background: var(--bg-btn-hover); color: var(--primary); }
        .tool-btn.active-orange { background: rgba(230, 162, 60, 0.15); color: var(--orange) !important; }
        .tool-btn.active-green { background: rgba(103, 194, 58, 0.15); color: var(--green) !important; }
        .tool-btn svg { width: 16px; height: 16px; }

        .icon-solid-circle { width: 14px; height: 14px; background-color: currentColor; border-radius: 50%; display: inline-block; }
        .icon-outline-circle { width: 14px; height: 14px; border: 2px solid currentColor; border-radius: 50%; display: inline-block; box-sizing: border-box; }

        .tree-container { flex: 1; background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 8px; overflow-y: auto; overflow-x: hidden;}
        
        .group { margin-bottom: 0px; width: 100%; }
        .group-root { background: transparent; border-radius: var(--radius); padding: 0px; margin-bottom: 1px; border: 1px solid transparent;}
        
        .group-sub { display: flex; position: relative; margin-top: 2px; }
        .group-root > .group-content > .subgroups-area > .group-sub { margin-left: 20px; }
        .group-sub > .group-sub-main > .group-content > .subgroups-area > .group-sub { margin-left: 4px; }
        .group-sub-bar { width: 14px; flex-shrink: 0; border-radius: var(--radius) 0 0 var(--radius); display: flex; align-items: flex-start; justify-content: center; padding-top: 3px; color: var(--sub-arrow, rgba(255,255,255,0.7)); cursor: pointer; transition: opacity 0.2s;}
        .group-sub-bar:hover { opacity: 1; }
        .group-sub-bar svg { width: 10px; height: 10px; }
        .group-sub-main { flex: 1; min-width: 0; padding-left: 2px; }

        .group-header { display: flex; align-items: center; padding: 2px 4px; border-radius: var(--radius); position: relative; transition: background-color 0.1s; min-height: 21px; color: var(--group-text, var(--text-main));}
        .group-header:hover { background-color: rgba(128, 128, 128, 0.08) !important; }
        .group-arrow { width: 16px; font-weight: bold; color: var(--group-arrow, var(--text-muted)); display: flex; align-items: center; }
        .group-arrow svg { width: 14px; height: 14px; }
        .group-title { font-weight: bold; font-size: 13px; }
        .group-dot { color: var(--green); font-size: 10px; margin-left: 6px; display: none; }
        .group-dot.show { display: inline; }

        .group-content { padding: 0; }
        .group.collapsed > .group-content, .group.collapsed > .group-sub-main > .group-content { display: none; }
        
        /* 标签精确对齐组名文本 */
        .tags-area { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 2px; padding-left: 0; }
        .group-root > .group-content > .tags-area { padding-left: 20px; }
        .group-sub > .group-sub-main > .group-content > .tags-area { padding-left: 4px; }
        
        .tags-area:empty { display: none; margin-bottom: 0; }
        .subgroups-area > .group-sub:first-child { margin-top: 2px; } /* 根级跟首个子组贴紧 */
        
        .subgroups-area { display: flex; flex-direction: column; width: 100%; }

        /* --- 核心修复：彻底封杀所有交互元素的双击选中文本（幽灵蓝影）现象 --- */
        .tag-btn, .comp-btn, .group-header, .tool-btn, .ws-tab, .action-btn { 
            -webkit-user-select: none; 
            user-select: none; 
        }

        /* 标签按钮紧凑化 */
        .tag-btn { position: relative; height: 25px; padding: 0 8px; background: var(--bg-btn); color: var(--btn-text, var(--text-main)); border: 1px solid var(--border-color); border-radius: var(--radius); font-size: 12px; font-weight: bold; display: inline-flex; align-items: center; justify-content: center; box-sizing: border-box; white-space: nowrap; transition: 0.1s; }
        .tag-btn:hover { background: var(--bg-btn-hover); border-color: var(--primary); color: var(--primary); }
        
        .tag-btn.s1 { background: var(--bg-and) !important; color: var(--text-and) !important; border-color: var(--bg-and) !important; } 
        .tag-btn.s2 { background: var(--bg-not) !important; color: var(--text-not) !important; border-color: var(--bg-not) !important; } 
        .tag-btn.s3 { background: var(--bg-or) !important; color: var(--text-or) !important; border-color: var(--bg-or) !important; } 
        
        /* 独立且具有绝对优先权的悬浮修复 */
        .tag-btn.s1:hover { background: var(--hover-and) !important; border-color: var(--hover-and) !important; color: var(--text-and) !important; }
        .tag-btn.s2:hover { background: var(--hover-not) !important; border-color: var(--hover-not) !important; color: var(--text-not) !important; }
        .tag-btn.s3:hover { background: var(--hover-or) !important; border-color: var(--hover-or) !important; color: var(--text-or) !important; }
        
        .tag-del, .custom-ext-del { position: absolute; width: 16px; height: 16px; background: var(--red); color: white; border-radius: 50%; display: none; align-items: center; justify-content: center; box-shadow: 0 1px 3px rgba(0,0,0,0.3); z-index: 2; transition: 0.2s;}
        .tag-del { right: -6px; top: -6px; }
        .custom-ext-del { right: -5px; top: -5px; width: 14px; height: 14px; }
        .tag-del svg, .custom-ext-del svg { width: 10px; height: 10px; }
        .tag-del:hover, .custom-ext-del:hover { background: #d32f2f; transform: scale(1.1); }
        .edit-mode .tag-del { display: flex; }
        .ext-edit-mode .custom-ext-del { display: flex; }

        .add-tag-btn { width: 24px; height: 24px; display: inline-flex; align-items: center; justify-content: center; color: transparent; border-radius: var(--radius); flex-shrink: 0; transition: 0.2s; }
        .add-tag-btn svg { width: 16px; height: 16px; }
        .tags-area:hover .add-tag-btn, .comp-btn-group:hover .add-tag-btn, .group-header:hover .add-tag-btn { color: var(--green); opacity: 0.7; }
        .add-tag-btn:hover { background-color: rgba(76, 175, 80, 0.15) !important; color: var(--green) !important; opacity: 1 !important; }

        .drag-top { border-top: 2px solid var(--orange) !important; }
        .drag-bottom { border-bottom: 2px solid var(--orange) !important; }
        .drag-center { background: rgba(0, 188, 212, 0.15) !important; }
        .drag-left { border-left: 3px solid var(--orange) !important; }
        .drag-right { border-right: 3px solid var(--orange) !important; }

        /* 菜单样式升级，增加光影边缘感 */
        #ctx-menu, #ws-ctx-menu, #ws-list-menu, #quick-edit, #batch-add-menu, #action-btn-ctx-menu { display: none; position: fixed; z-index: 9999; background: var(--bg-menu); border: 1px solid var(--border-color); border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); flex-direction: column; padding: 4px; min-width: 140px; }
        .menu-item { padding: 6px 12px; border-radius: var(--radius); font-size: 13px; display: flex; align-items: center; position: relative; color: var(--text-main); gap: 8px; margin-bottom: 2px;}
        .menu-item:last-child { margin-bottom: 0; }
        .menu-item:hover { background: var(--primary); color: #fff; }
        .menu-item .menu-text { flex: 1; white-space: nowrap; }
        .menu-icon { width: 14px; height: 14px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
        
        .has-submenu .submenu { display: none; position: absolute; background: var(--bg-menu); border: 1px solid var(--border-color); border-radius: 8px; min-width: 120px; box-shadow: 0 6px 16px rgba(0,0,0,0.15); flex-direction: column; padding: 4px; z-index: 10001; }
        .submenu-item { padding: 6px 10px; border-radius: var(--radius); font-size: 12px; color: var(--text-main); margin-bottom: 2px;}
        .submenu-item:hover { background: var(--primary); color: #fff; }

        #ws-list-menu { max-height: 300px; overflow-y: auto; }
        
        .ws-list-item { transition: background 0.15s; }
        .ws-list-item.active .menu-text { color: var(--primary); font-weight: bold; }
        .ws-list-item:hover { background: var(--primary) !important; }
        .ws-list-item:hover .menu-text { color: #fff !important; }

        #quick-edit { padding: 6px; min-width: 120px; }

        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.5); z-index: 10000; align-items: center; justify-content: center; backdrop-filter: blur(3px); }
        .modal-content { background: var(--bg-panel); padding: 15px; border-radius: 10px; width: 380px; border: 1px solid var(--border-color); box-shadow: 0 10px 30px rgba(0,0,0,0.3); display: flex; flex-direction: column; }
        
        .settings-btn { background: var(--bg-btn); border: 1px solid var(--border-color); color: var(--text-main); border-radius: var(--radius); padding: 6px; transition: 0.2s; display: flex; align-items: center; justify-content: center; gap: 6px; font-size: 13px; }
        .settings-btn:hover { background: var(--bg-btn-hover); color: var(--primary); border-color: var(--primary); }

        .theme-tabs { display: flex; border-bottom: 1px solid var(--border-color); margin-bottom: 6px; }
        .tab-btn { flex: 1; text-align: center; padding: 6px 0; color: var(--text-muted); font-weight: bold; border-bottom: 2px solid transparent; font-size: 12px; transition: 0.2s; border-radius: var(--radius) var(--radius) 0 0;}
        .tab-btn:hover { color: var(--text-main); background: rgba(128,128,128,0.05); }
        .tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }
        .theme-view { display: none; flex-direction: column; gap: 6px; height: 120px; overflow-y: auto; padding-right: 5px;}
        .theme-view.active { display: flex; }
        .palette-row { display: flex; align-items: center; gap: 8px; }
        .palette-title { width: 60px; font-size: 11px; color: var(--text-muted); text-align: right; }
        .palette-colors { display: flex; gap: 4px; flex: 1; flex-wrap: wrap; }
        .color-swatch { width: 22px; height: 22px; border-radius: var(--radius); border: 1px solid var(--border-color); transition: 0.1s; }
        .color-swatch:hover { transform: scale(1.15); border-color: var(--primary); z-index: 2; position: relative; }
        .history-row { padding-top: 6px; margin-top: 4px; display: flex; align-items: flex-start; gap: 8px; }
        input[type="color"] { -webkit-appearance: none; border: none; width: 28px; height: 28px; border-radius: var(--radius); padding: 0; background: transparent; cursor: pointer !important;}
        input[type="color"]::-webkit-color-swatch-wrapper { padding: 0; }
        input[type="color"]::-webkit-color-swatch { border: 1px solid var(--border-color); border-radius: var(--radius); }
        
        #toast-container { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; flex-direction: column; gap: 8px; z-index: 100000; pointer-events: none; }
        .toast { background: var(--bg-menu); color: var(--text-main); padding: 10px 20px; border-radius: 8px; box-shadow: 0 6px 16px rgba(0,0,0,0.25); font-size: 13px; font-weight: bold; opacity: 0; transition: opacity 0.3s, transform 0.3s; transform: translateY(15px); border-left: 4px solid var(--primary); display: flex; align-items: center; gap: 8px;}
        .toast.show { opacity: 1; transform: translateY(0); }
        .toast.error { border-left-color: var(--red); }
        .toast.success { border-left-color: var(--green); }
        .toast.info { border-left-color: var(--blue); }
        
        /* [修复] 增加 width: max-content 强制由内容撑开，避免边缘挤压 */
        #float-tooltip { display: none; position: fixed; background: var(--bg-menu); color: var(--text-main); padding: 8px 12px; border-radius: var(--radius); border: 1px solid var(--border-color); box-shadow: 0 8px 24px rgba(0,0,0,0.3); z-index: 999999; width: max-content; max-width: 300px; white-space: pre-wrap; word-wrap: break-word; font-size: 12px; pointer-events: none; line-height: 1.4; }

        /* --- 彻底移除“网页感”的小手光标，回归纯粹的桌面端箭头质感 --- */
        * { cursor: default !important; }
        
        /* [保护机制] 确保所有的文本输入框依然显示文字录入光标 (I字形) */
        input[type="text"], textarea { cursor: text !important; }
        
        /* 确保复选框和单选框也严格使用箭头 */
        input[type="checkbox"], input[type="radio"] { cursor: default !important; }
    </style>
</head>
<body>

    <div id="app-loader">L O A D I N G ...</div>

    <div id="tag-search-modal" class="global-dropdown" style="width: 380px; padding: 10px; z-index: 10002; display: none; cursor: default; background: var(--bg-panel);">
        <div style="display: flex; gap: 6px; margin-bottom: 8px; align-items: center;">
            <input type="text" id="tag-search-input" data-i18n-ph="search_ph" style="flex: 1;" oninput="doTagSearch()">
            <button class="tool-btn" onclick="closeTagSearch()" v-html="delete"></button>
        </div>
        <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 12px; color: var(--text-muted); padding: 0 4px;">
            <div style="display: flex; gap: 15px;">
                <label style="cursor: pointer;"><input type="radio" name="search_mode" value="fuzzy" checked onclick="doTagSearch()"> <span data-i18n="fuzzy">模糊</span></label>
                <label style="cursor: pointer;"><input type="radio" name="search_mode" value="exact" onclick="doTagSearch()"> <span data-i18n="exact">精准</span></label>
            </div>
            <label style="cursor: pointer;" data-i18n-title="remember_search_hint"><input type="checkbox" id="search-memory-toggle" onclick="toggleSearchMemory(this.checked)"> <span data-i18n="remember_search">记忆搜索</span></label>
        </div>
        <div style="display: flex; gap: 10px; margin-bottom: 8px; font-size: 12px; color: var(--text-muted); padding: 0 4px; border-top: 1px dashed var(--border-color); padding-top: 6px;">
            <span data-i18n="search_in" style="opacity: 0.8;">范围:</span>
            <label style="cursor: pointer;"><input type="checkbox" id="search-in-group" checked onchange="doTagSearch()"> <span data-i18n="s_group">标签组</span></label>
            <label style="cursor: pointer;"><input type="checkbox" id="search-in-tag" checked onchange="doTagSearch()"> <span data-i18n="s_tag">标签</span></label>
            <label style="cursor: pointer;"><input type="checkbox" id="search-in-remark" checked onchange="doTagSearch()"> <span data-i18n="s_remark">备注</span></label>
            <label style="cursor: pointer;"><input type="checkbox" id="search-in-desc" checked onchange="doTagSearch()"> <span data-i18n="s_desc">描述</span></label>
        </div>
        <div id="tag-search-results">
            </div>
    </div>

    <div class="main-content">
        <div class="ws-bar" id="ws-bar">
            <div class="ws-tabs-scroll" id="ws-tabs-scroll" onscroll="updateWsVisibility()"></div>
            <div class="ws-add btn-plus-icon" onclick="addWs(event)" data-i18n-title="new_ws" v-html="add"></div>
            <div class="ws-dynamic-area" id="ws-dynamic-area"></div>
            <button class="tool-btn" id="btn-ws-dropdown" style="margin-left:4px;" onclick="toggleWsDropdown(event)" data-i18n-title="view_all_ws" v-html="arrowDown"></button>
            
            <div style="display:flex; gap:4px; padding-left: 8px; border-left: 1px solid var(--border-color);">
                <button class="tool-btn" id="btn-pin" data-i18n-title="pin_top" onclick="togglePin()" v-html="pin"></button>
                <button class="tool-btn" data-i18n-title="settings" onclick="openSettings()" v-html="settings"></button>
            </div>
        </div>

        <div class="top-bar">
            <div class="syntax-wrapper" id="syntax-wrapper">
                <textarea id="syntax-input" readonly data-i18n-ph="syntax_ph"></textarea>
            </div>
            <div class="action-buttons">
                <button id="btn-search" class="action-btn btn-search" data-i18n-title="search_title" onclick="execSearch()" oncontextmenu="onActionBtnCtx(event, 'search')">
                    <span v-html="search"></span><span style="margin-left:4px;" data-i18n="search">搜索</span>
                </button>
                <button id="btn-add" class="action-btn btn-add" data-i18n-title="tag_title" onclick="execAddTags()" oncontextmenu="onActionBtnCtx(event, 'add')">
                    <span v-html="add"></span><span style="margin-left:4px;" data-i18n="add_tag">打标签</span>
                </button>
                <button id="btn-read" class="action-btn btn-read" data-i18n-title="read_title" onclick="execReadTags()" oncontextmenu="onActionBtnCtx(event, 'read')">
                    <span v-html="importIco"></span><span style="margin-left:4px;" data-i18n="read_tag">读标签</span>
                </button>
                <button id="btn-clear" class="action-btn btn-clear" data-i18n-title="clear_title" onclick="clearAllFiltersAndTags()" oncontextmenu="onActionBtnCtx(event, 'clear')">
                    <span v-html="clear"></span><span style="margin-left:4px;" data-i18n="clear">清空</span>
                </button>
            </div>
        </div>

        <div class="comp-module" id="comp-module">
            <div class="comp-tabs" onclick="toggleCompModule()">
                <div class="comp-tabs-scroll" style="display: flex; flex: 1; height: 100%; overflow-x: auto; scrollbar-width: none; -ms-overflow-style: none;">
                    <style>.comp-tabs-scroll::-webkit-scrollbar { display: none; } .comp-tabs-scroll .comp-tab { white-space: nowrap; flex-shrink: 0; }</style>
                    <div class="comp-tab active" onclick="event.stopPropagation(); switchCompTab('type')" data-i18n="tab_type">类型</div>
                    <div class="comp-tab" onclick="event.stopPropagation(); switchCompTab('path')" data-i18n="tab_path">路径</div>
                    <div class="comp-tab" onclick="event.stopPropagation(); switchCompTab('name')" data-i18n="tab_name">文件名</div>
                    <div class="comp-tab" onclick="event.stopPropagation(); switchCompTab('remark')" data-i18n="tab_remark">备注</div>
                    <div class="comp-tab" onclick="event.stopPropagation(); switchCompTab('label')" data-i18n="tab_label">标注</div>
                    <div class="comp-tab" onclick="event.stopPropagation(); switchCompTab('rating')" data-i18n="tab_rating">评分</div>
                    <div class="comp-tab" onclick="event.stopPropagation(); switchCompTab('size')" data-i18n="tab_size">大小/日期</div>
                </div>
                
                <div style="display: flex; flex-shrink: 0; align-items: center; padding-right: 4px; gap: 2px;">
                    <button class="tool-btn" data-i18n-title="clear_filter" onclick="event.stopPropagation(); clearCompFilters()" v-html="clear"></button>
                    <button class="tool-btn" id="comp-collapse-btn" onclick="event.stopPropagation(); toggleCompModule()" v-html="arrowDown"></button>
                </div>
            </div>
            
            <div class="comp-body active" id="comp-type">
                <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
                    <span style="font-size:11px; color:var(--text-muted);" data-i18n="hint_type">左键：包含 (OR) | 右键：排除 (NOT) | 拖拽排序</span>
                </div>
                <div class="comp-btn-group" id="comp-type-container"></div>
                <div style="margin-top:6px; border-top:1px dashed var(--border-color); padding-top:6px;">
                    <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                        <span style="font-size:11px; color:var(--text-muted);" data-i18n="custom_ext">自定义后缀名</span>
                        <span class="tool-btn" style="width:20px; height:20px; border:1px solid var(--border-color);" onclick="toggleExtEditMode()" data-i18n-title="edit_mode" v-html="edit"></span>
                    </div>
                    <div class="comp-btn-group" id="comp-ext-container"></div>
                </div>
            </div>
            
            <div class="comp-body" id="comp-path">
                <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px; display:flex; justify-content:space-between; align-items:center;">
                    <span data-i18n="hint_path">输入路径，单个如 C:\\ ；多个如 C:\\|D:\\ ；* (全盘)</span>
                </div>
                <div class="input-group" style="margin-bottom:6px;">
                    <input type="text" id="comp-input-path" data-i18n-ph="ph_path" oninput="updateCompState('path', this.value)" onkeydown="if(event.key==='Enter'){ event.preventDefault(); confirmInput('path'); }">
                    <button class="hist-toggle" onclick="confirmInput('path')" style="border-radius:0; border-right:1px solid var(--border-color);" data-i18n-title="save_record" v-html="check"></button>
                    <button class="hist-toggle" onclick="toggleHistory(event, 'path')" v-html="arrowDown"></button>
                </div>
                <div style="display:flex; gap:6px;">
                    <button class="comp-btn" onclick="setCompPath('')" data-i18n="all_drives">全盘</button>
                    <button class="comp-btn" onclick="setCompPath('%desktop%')" data-i18n="desktop">桌面</button>
                </div>
            </div>

            <div class="comp-body" id="comp-name">
                <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;" data-i18n="hint_name">名字包含A排除B，如 A+B,C-D 会智能转换为 (A & B) | (C & !D)</div>
                <div class="input-group">
                    <input type="text" id="comp-input-name" data-i18n-ph="ph_name" oninput="updateCompState('name', this.value)" onkeydown="if(event.key==='Enter'){ event.preventDefault(); confirmInput('name'); }">
                    <button class="hist-toggle" onclick="confirmInput('name')" style="border-radius:0; border-right:1px solid var(--border-color);" data-i18n-title="save_record" v-html="check"></button>
                    <button class="hist-toggle" onclick="toggleHistory(event, 'name')" v-html="arrowDown"></button>
                </div>
            </div>

            <div class="comp-body" id="comp-remark">
                <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;" data-i18n="hint_remark">备注包含A排除B，如 A+B,C-D 会智能转换为 (A & B) | (C & !D)</div>
                <div class="input-group" style="margin-bottom:6px;">
                    <input type="text" id="comp-input-remark" data-i18n-ph="ph_remark" oninput="updateCompState('remark', this.value)" onkeydown="if(event.key==='Enter'){ event.preventDefault(); confirmInput('remark'); }">
                    <button class="hist-toggle" onclick="confirmInput('remark')" style="border-radius:0; border-right:1px solid var(--border-color);" data-i18n-title="save_record" v-html="check"></button>
                    <button class="hist-toggle" onclick="toggleHistory(event, 'remark')" v-html="arrowDown"></button>
                </div>
                <div style="display:flex; gap:6px;">
                    <button class="comp-btn" id="btn-remark-any" onclick="applyRemarkPreset('any')" data-i18n="has_remark">含备注</button>
                    <button class="comp-btn" id="btn-remark-none" onclick="applyRemarkPreset('none')" data-i18n="no_remark">无备注</button>
                </div>
            </div>

            <div class="comp-body" id="comp-label">
                <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px; display:flex; justify-content:space-between; align-items:center;">
                    <span data-i18n="hint_label">点击选择标注，支持拖拽排序</span>
                    <button class="comp-btn" style="padding: 2px 8px; border-radius:var(--radius); font-weight:normal;" onclick="updateXYLabels()" data-i18n="sync_xy">同步XYplorer批注</button>
                </div>
                <div class="comp-btn-group" id="comp-label-container"></div>
            </div>

            <div class="comp-body" id="comp-rating">
                <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;" data-i18n="hint_rating">点击选择评分 (支持多选与拖拽)</div>
                <div class="comp-btn-group" id="comp-rating-container"></div>
            </div>

            <div class="comp-body" id="comp-size">
                <div style="display:flex; flex-direction:column; gap:12px;">
                    <div>
                        <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;" data-i18n="size">文件大小</div>
                        <div class="builder-row">
                            <select id="size-op" class="builder-sel"><option value=">=">≥</option><option value="<=">≤</option><option value="==">=</option></select>
                            <input type="number" id="size-val" style="width:60px; padding:4px;" data-i18n-ph="value" onkeydown="if(event.key==='Enter'){ event.preventDefault(); addRule('size'); }">
                            <select id="size-unit" class="builder-sel"><option value="MB">MB</option><option value="KB">KB</option><option value="GB">GB</option></select>
                            <button class="tool-btn btn-plus-icon" style="width:22px; height:22px; border-radius:var(--radius);" onclick="addRule('size')" v-html="add"></button>
                        </div>
                    </div>
                    <div>
                        <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;" data-i18n="date">日期时间</div>
                        <div class="builder-row">
                            <select id="date-type" class="builder-sel">
                                <option value="dateC" data-i18n="date_c">创建日期</option>
                                <option value="dateM" data-i18n="date_m">修改日期</option>
                                <option value="dateA" data-i18n="date_a">访问日期</option>
                                <option value="ageC" data-i18n="age_c">创建时间</option>
                                <option value="ageM" data-i18n="age_m">修改时间</option>
                                <option value="ageA" data-i18n="age_a">访问时间</option>
                            </select>
                            <select id="date-op" class="builder-sel">
                                <option value=""> </option>
                                <option value="==">=</option>
                                <option value=">=">≥</option>
                                <option value="<=">≤</option>
                            </select>
                            <input type="text" id="date-val" style="width:80px; padding:4px;" placeholder="YYYY-MM-DD" onkeydown="if(event.key==='Enter'){ event.preventDefault(); addRule('date'); }">
                            <button class="tool-btn btn-plus-icon" style="width:22px; height:22px; border-radius:var(--radius);" onclick="addRule('date')" v-html="add"></button>
                            <button class="tool-btn btn-plus-icon" style="width:22px; height:22px; border-radius:var(--radius); margin-left:4px;" onclick="openDateHelp()" v-html="help"></button>
                        </div>
                    </div>
                </div>
                <div class="comp-btn-group" id="rules-container" style="margin-top:8px;"></div>
            </div>
        </div>

        <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 4px; flex-shrink: 0;">
            <div style="display: flex; align-items: center; gap: 6px; font-size: 14px; font-weight: bold; color: var(--primary);">
                <span style="width: 16px; height: 16px; display: flex; align-items: center;" v-html="tag"></span>
                <span data-i18n="tag_group">标签组</span>
            </div>
            <div style="flex: 1;"></div>
            <button class="tool-btn" data-i18n-title="clear_tree" onmousedown="event.preventDefault(); clearAll()" ondblclick="event.preventDefault()" v-html="clear"></button>
            <button class="tool-btn" id="btn-toggle" data-i18n-title="toggle_all" onmousedown="event.preventDefault(); toggleAll(event)" ondblclick="event.preventDefault()" oncontextmenu="event.preventDefault()" v-html="expand"></button>
            <button class="tool-btn" id="btn-active" data-i18n-title="expand_active" onmousedown="event.preventDefault(); toggleTool('activeOnly')" ondblclick="event.preventDefault()"><div class="icon-solid-circle"></div></button>
            <button class="tool-btn" id="btn-filter" data-i18n-title="show_active" onmousedown="event.preventDefault(); toggleTool('filterOnly')" ondblclick="event.preventDefault()"><div class="icon-outline-circle"></div></button>
            <button class="tool-btn" id="btn-edit" data-i18n-title="edit_mode" onmousedown="event.preventDefault(); toggleTool('editMode')" ondblclick="event.preventDefault()" v-html="edit"></button>
            <button class="tool-btn" id="btn-swap-alias" data-i18n-title="swap_alias" onmousedown="event.preventDefault(); toggleTool('showAlias')" ondblclick="event.preventDefault()" v-html="swap"></button>
            <button class="tool-btn" id="btn-toggle-tooltip" data-i18n-title="toggle_tooltip" onmousedown="event.preventDefault(); toggleTool('enableTooltip')" ondblclick="event.preventDefault()" v-html="tooltip"></button>
            <button class="tool-btn" style="margin-left:4px;" data-i18n-title="search_tags" onclick="openTagSearch(event)" v-html="search"></button>
            <button class="tool-btn btn-plus-icon" data-i18n-title="add_root" onclick="addRootGroup(event)" oncontextmenu="triggerBatchAddMenu(event, 'root')" v-html="add"></button>
        </div>

        <div class="tree-container" id="tree"></div>
    </div>

    <div id="global-hist-dropdown" class="global-dropdown"></div>

    <div id="ctx-menu">
        <div class="menu-item" onclick="ctxAction('select-all-or')"><span class="menu-icon" style="color:var(--green);" v-html="selectAll"></span><span class="menu-text" data-i18n="ctx_select_or">全选组内标签 (或)</span></div>
        <div class="menu-item" onclick="ctxAction('exclude-all')"><span class="menu-icon" style="color:var(--red);" v-html="excludeAll"></span><span class="menu-text" data-i18n="ctx_exclude_all">排除组内标签 (非)</span></div>
        <div class="menu-item" onclick="ctxAction('clear-group')"><span class="menu-icon" v-html="clear"></span><span class="menu-text" data-i18n="ctx_clear_group">清除组内状态</span></div>
        <div style="border-top:1px solid var(--border-color); margin:4px 0;"></div>
        
        <div class="menu-item" id="ctx-expand" onclick="ctxAction('expand-all')"><span class="menu-icon" v-html="expand"></span><span class="menu-text" data-i18n="expand_all_sub">展开子组</span></div>
        <div class="menu-item" id="ctx-collapse" onclick="ctxAction('collapse-leaf')"><span class="menu-icon" v-html="minimize"></span><span class="menu-text" data-i18n="collapse_leaf">折叠子组</span></div>
        <div style="border-top:1px solid var(--border-color); margin:4px 0;"></div>
        <div class="menu-item" onclick="ctxAction('color')"><span class="menu-icon" v-html="palette"></span><span class="menu-text" data-i18n="edit_color">修改分类颜色</span></div>
        <div class="menu-item" onclick="ctxAction('color-reset')"><span class="menu-icon" v-html="refresh"></span><span class="menu-text" data-i18n="reset_color">恢复默认颜色</span></div>
        <div class="menu-item" id="ctx-reset-uncat" onclick="ctxAction('reset-uncat')"><span class="menu-icon" v-html="refresh"></span><span class="menu-text" data-i18n="reset_uncat">恢复默认标签</span></div>
        <div class="menu-item" id="ctx-rename" onclick="ctxAction('rename')"><span class="menu-icon" v-html="edit"></span><span class="menu-text" data-i18n="rename_group">重命名分组</span></div>
        <div style="border-top:1px solid var(--border-color); margin:4px 0;"></div>
        <div class="menu-item" onclick="ctxAction('add')"><span class="menu-icon" v-html="add"></span><span class="menu-text" data-i18n="add_sub">新建子组</span></div>
        <div class="menu-item" onclick="ctxAction('batch-add')"><span class="menu-icon" v-html="edit"></span><span class="menu-text" data-i18n="batch_add_sub">批量新建子组</span></div>
        <div class="menu-item" onclick="ctxAction('add-tag')"><span class="menu-icon" v-html="add"></span><span class="menu-text" data-i18n="add_tag_menu">新建标签</span></div>
        <div class="menu-item" onclick="ctxAction('batch-add-tag')"><span class="menu-icon" v-html="edit"></span><span class="menu-text" data-i18n="batch_add_tag_menu">批量新建标签</span></div>
        <div style="border-top:1px solid var(--border-color); margin:4px 0;"></div>
        <div class="menu-item has-submenu" id="ctx-move">
            <span class="menu-icon" v-html="move"></span><span class="menu-text" data-i18n="move_to">移动到工作区</span><span class="submenu-arrow" v-html="arrowRight"></span>
            <div class="submenu" id="sub-move"></div>
        </div>
        <div class="menu-item has-submenu" id="ctx-copy">
            <span class="menu-icon" v-html="copy"></span><span class="menu-text" data-i18n="copy_to">复制到工作区</span><span class="submenu-arrow" v-html="arrowRight"></span>
            <div class="submenu" id="sub-copy"></div>
        </div>
        <div style="border-top:1px solid var(--border-color); margin:4px 0;"></div>
        <div class="menu-item" id="ctx-del" onclick="ctxAction('delete')"><span class="menu-icon" v-html="delete" style="color:var(--red);"></span><span class="menu-text" style="color:var(--red);" data-i18n="del_group">删除分组</span></div>
    </div>
    
    <div id="action-btn-ctx-menu">
        <div class="menu-item" id="ctx-batch-ucs" style="display:none;" onclick="execBatchUCS()"><span class="menu-icon" v-html="edit"></span><span class="menu-text" data-i18n="batch_ucs">批量UCS标签</span></div>
        <div class="menu-item" id="ctx-batch-ucs-name" style="display:none;" onclick="execBatchUCSName()"><span class="menu-icon" v-html="edit"></span><span class="menu-text" data-i18n="batch_ucs_name">批量文件名转UCS标签</span></div>
        <div id="ai-sep" style="border-top:1px solid var(--border-color); margin:4px 0; display:none;"></div>
        <div class="menu-item" id="ctx-ai-filename-dict" style="display:none;" onclick="execAITagging('dict_name')"><span class="menu-icon" style="color:var(--orange);" v-html="info"></span><span class="menu-text" data-i18n="ai_filename_dict">AI 文件名匹配字典 (不激活)</span></div>
        <div class="menu-item has-submenu" id="ctx-ai-filename-auto-en-zh" style="display:none;">
            <span class="menu-icon" style="color:var(--orange);" v-html="info"></span><span class="menu-text" data-i18n="ai_filename_auto_en_zh">AI 文件名自动生成标签-英中 (激活)</span><span class="submenu-arrow" v-html="arrowRight"></span>
            <div class="submenu" style="min-width: 140px; margin-left: 5px;">
                <div class="submenu-item" onclick="execAITagging('auto_name_en_zh', '通用')"><span data-i18n="domain_general">通用领域</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name_en_zh', '音效/音频')"><span data-i18n="domain_audio">音效 / 音频</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name_en_zh', '影视/视频')"><span data-i18n="domain_video">影视 / 视频</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name_en_zh', '设计/图像素材')"><span data-i18n="domain_design">设计 / 图像素材</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name_en_zh', '摄影/照片')"><span data-i18n="domain_photo">摄影 / 照片</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name_en_zh', '时尚/穿搭')"><span data-i18n="domain_fashion">时尚 / 穿搭</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name_en_zh', '编程/代码')"><span data-i18n="domain_code">编程 / 代码</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name_en_zh', '文档/办公')"><span data-i18n="domain_office">文档 / 办公</span></div>
            </div>
        </div>
        <div class="menu-item has-submenu" id="ctx-ai-filename-auto" style="display:none;">
            <span class="menu-icon" style="color:var(--orange);" v-html="info"></span><span class="menu-text" data-i18n="ai_filename_auto">AI 文件名自动生成标签 (激活)</span><span class="submenu-arrow" v-html="arrowRight"></span>
            <div class="submenu" style="min-width: 140px; margin-left: 5px;">
                <div class="submenu-item" onclick="execAITagging('auto_name', '通用')"><span data-i18n="domain_general">通用领域</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name', '音效/音频')"><span data-i18n="domain_audio">音效 / 音频</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name', '影视/视频')"><span data-i18n="domain_video">影视 / 视频</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name', '设计/图像素材')"><span data-i18n="domain_design">设计 / 图像素材</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name', '摄影/照片')"><span data-i18n="domain_photo">摄影 / 照片</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name', '时尚/穿搭')"><span data-i18n="domain_fashion">时尚 / 穿搭</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name', '编程/代码')"><span data-i18n="domain_code">编程 / 代码</span></div>
                <div class="submenu-item" onclick="execAITagging('auto_name', '文档/办公')"><span data-i18n="domain_office">文档 / 办公</span></div>
            </div>
        </div>
        <div class="menu-item" id="ctx-ai-content-auto" style="display:none;" onclick="execAITagging('auto_content')"><span class="menu-icon" style="color:var(--orange);" v-html="info"></span><span class="menu-text" data-i18n="ai_content_auto">AI 文本内容自动生成 (激活)</span></div>
        <div class="menu-item" onclick="execActionBtnColor()"><span class="menu-icon" v-html="palette"></span><span class="menu-text" data-i18n="edit_bg">修改背景颜色</span></div>
        <div class="menu-item" onclick="execActionBtnColorReset()"><span class="menu-icon" v-html="refresh"></span><span class="menu-text" data-i18n="reset_color">恢复默认颜色</span></div>
    </div>

    <div id="batch-add-menu">
        <div class="menu-item" onclick="executeBatchAddMenu()"><span class="menu-icon" id="batch-title-icon" v-html="add"></span><span class="menu-text" id="batch-title-text" data-i18n="batch_add">批量新建</span></div>
        <div id="ws-io-separator" style="border-top:1px solid var(--border-color); margin:4px 0; display:none;"></div>
        <div class="menu-item" id="ws-export-btn" style="display:none;" onclick="exportCurrentWorkspace()"><span class="menu-icon" v-html="export"></span><span class="menu-text" data-i18n="export_workspace">导出当前工作区</span></div>
        <div class="menu-item" id="ws-import-btn" style="display:none;" onclick="importToWorkspace()"><span class="menu-icon" v-html="importIco"></span><span class="menu-text" data-i18n="import_workspace">导入到当前工作区</span></div>
    </div>
    <input type="file" id="import-ws-file" accept=".json" style="display:none;" onchange="handleImportWorkspace(event)">
    <div id="ext-batch-menu" class="global-dropdown" style="display: none; position: fixed; z-index: 9999; background: var(--bg-menu); border: 1px solid var(--border-color); border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.15); flex-direction: column; padding: 4px; min-width: 140px;">
        <div class="menu-item" onclick="batchTarget = { type: 'ext' }; executeBatchAddMenu(); document.getElementById('ext-batch-menu').style.display='none';"><span class="menu-icon" v-html="edit"></span><span class="menu-text" data-i18n="batch_ext_custom">自定义批量添加...</span></div>
        <div style="border-top:1px solid var(--border-color); margin:4px 0;"></div>
        <div class="menu-item" onclick="addCommonExts('text')"><span class="menu-icon" v-html="add"></span><span class="menu-text" data-i18n="batch_ext_text">批量添加 文本 后缀</span></div>
        <div class="menu-item" onclick="addCommonExts('image')"><span class="menu-icon" v-html="add"></span><span class="menu-text" data-i18n="batch_ext_image">批量添加 图像 后缀</span></div>
        <div class="menu-item" onclick="addCommonExts('audio')"><span class="menu-icon" v-html="add"></span><span class="menu-text" data-i18n="batch_ext_audio">批量添加 音频 后缀</span></div>
        <div class="menu-item" onclick="addCommonExts('video')"><span class="menu-icon" v-html="add"></span><span class="menu-text" data-i18n="batch_ext_video">批量添加 视频 后缀</span></div>
        <div class="menu-item" onclick="addCommonExts('document')"><span class="menu-icon" v-html="add"></span><span class="menu-text" data-i18n="batch_ext_doc">批量添加 文档 后缀</span></div>
    </div>

    <div id="ws-list-menu"></div>

    <div id="ws-ctx-menu">
        <div class="menu-item" onclick="wsCtxAction('color')"><span class="menu-icon" v-html="palette"></span><span class="menu-text" data-i18n="edit_tab_color">修改选项卡颜色</span></div>
        <div class="menu-item" onclick="wsCtxAction('color-reset')"><span class="menu-icon" v-html="refresh"></span><span class="menu-text" data-i18n="reset_color">恢复默认颜色</span></div>
        <div style="border-top:1px solid var(--border-color); margin:4px 0;"></div>
        <div class="menu-item" onclick="wsCtxAction('rename')"><span class="menu-icon" v-html="edit"></span><span class="menu-text" data-i18n="rename_ws">重命名工作区</span></div>
        <div class="menu-item" onclick="wsCtxAction('duplicate')"><span class="menu-icon" v-html="copy"></span><span class="menu-text" data-i18n="dup_ws">重复工作区</span></div>
        <div class="menu-item" style="color: var(--red);" onclick="wsCtxAction('delete')"><span class="menu-icon" v-html="delete"></span><span class="menu-text" data-i18n="del_ws">删除工作区</span></div>
    </div>
    
    <div id="quick-edit">
        <input type="text" id="edit-input">
    </div>

    <div id="detail-edit" class="global-dropdown" style="padding: 12px; width: 300px; display: none; background: var(--bg-panel); cursor: default; z-index: 10003; box-sizing: border-box;">
        <div style="font-size: 13px; font-weight: bold; color: var(--primary); margin-bottom: 10px;" id="de-title">编辑属性</div>
        <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 4px;" data-i18n="alias_remark">别名/备注</div>
        <input type="text" id="de-alias" style="width: 100%; box-sizing: border-box; margin-bottom: 12px; background: var(--bg-input); color: var(--text-main); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 6px 10px; font-family: inherit; font-size: 12px; outline: none;">
        <div style="font-size: 11px; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span data-i18n="descriptions">描述 (多行)</span>
            <button class="tool-btn btn-plus-icon" style="width: 20px; height: 20px;" onclick="addDeDescRow()" v-html="add"></button>
        </div>
        <div id="de-desc-list" style="display: flex; flex-direction: column; gap: 6px; max-height: 180px; overflow-y: auto; overflow-x: hidden; margin-bottom: 12px; padding-right: 4px;"></div>
        <div style="display: flex; justify-content: flex-end; gap: 8px;">
            <button class="settings-btn" style="padding: 6px 16px; width: auto;" onclick="closeDetailEdit()" data-i18n="cancel">取消</button>
            <button class="action-btn btn-search" style="padding: 6px 16px; border:none; width: auto;" onclick="submitDetailEdit()" data-i18n="save">保存</button>
        </div>
    </div>
    
    <div id="float-tooltip"></div>

    <div id="batch-progress-overlay" class="modal-overlay" style="z-index: 100000; backdrop-filter: blur(3px);">
        <div class="modal-content" style="width: 380px; text-align: center; justify-content: center; padding: 25px;">
            <h3 style="margin-top: 0; color: var(--primary); font-size: 16px; display: flex; align-items: center; justify-content: center; gap: 8px;">
                <span style="width: 18px; height: 18px; display: flex; align-items: center;" v-html="refresh"></span>
                <span data-i18n="batch_processing">批量处理中...</span>
            </h3>
            <p style="color: var(--red); font-weight: bold; font-size: 15px; margin: 15px 0; display: flex; align-items: center; justify-content: center; gap: 6px;">
                <span style="width: 20px; height: 20px; display: flex; align-items: center;" v-html="warning"></span>
                <span data-i18n="batch_warning">XYplorer完成批量打签前请勿操作！</span>
            </p>
            <div style="background: var(--bg-input); padding: 12px; border-radius: var(--radius); margin-bottom: 20px;">
                <span id="batch-progress-status" style="font-size: 13px; color: var(--text-main); font-family: monospace;" data-i18n="batch_status">正在分析文件并生成指令...</span>
            </div>
            <div style="display: flex; justify-content: center; gap: 10px;">
                <button id="batch-cancel-btn" class="settings-btn" style="width: 120px; border: 1px solid var(--border-color);" onclick="cancelBatchOperation()" data-i18n="batch_cancel">取消操作</button>
                <button id="batch-done-btn" class="action-btn btn-add" style="display:none; width: 140px; padding: 8px;" onclick="closeBatchProgressOverlay()" data-i18n="batch_exit">退出批量操作</button>
            </div>
        </div>
    </div>
    
    <div id="batch-modal" class="modal-overlay">
        <div class="modal-content" style="width: 450px; display: flex; flex-direction: column; height: 50vh; min-height: 300px;">
            <h4 id="batch-title" style="margin:0 0 10px 0; color:var(--primary); font-size:15px; display:flex; gap:8px; align-items:center;">
                <span v-html="add"></span> <span data-i18n="batch_add">批量新建</span>
            </h4>
            <div style="font-size:12px; color:var(--text-muted); margin-bottom:8px;" data-i18n="paste_hint">请在此处粘贴 (Ctrl+V) 要批量添加的项，每行一个。</div>
            <textarea id="batch-textarea" style="flex:1; width:100%; resize:none; margin-bottom:15px; box-sizing:border-box; font-family:inherit; padding:10px; border:1px solid var(--border-color); border-radius:var(--radius); background:var(--bg-input); color:var(--text-main); outline:none; white-space:pre;"></textarea>
            <div style="display:flex; justify-content:flex-end; gap:8px; flex-shrink:0;">
                <button class="settings-btn" style="width:auto; padding:6px 16px;" onclick="closeBatchModal()" data-i18n="cancel">取消</button>
                <button class="action-btn btn-search" style="width:auto; padding:6px 16px; border:none;" onclick="confirmBatchAdd()" data-i18n="confirm">确定</button>
            </div>
        </div>
    </div>

    <div id="date-help-modal" class="modal-overlay">
        <div class="modal-content" style="width: 580px; max-width: 90vw; max-height: 85vh; display: flex; flex-direction: column;">
            <h4 style="margin:0 0 15px 0; color:var(--primary); font-size:15px; display:flex; justify-content:space-between; align-items:center; flex-shrink:0;">
                <div style="display:flex; gap:8px; align-items:center;"><span v-html="help"></span> <span>Date & Age Syntax</span></div>
                <span class="hist-del" onclick="closeDateHelp()" style="font-size:22px; width:24px; height:24px; display:flex; align-items:center; justify-content:center;">×</span>
            </h4>
            <div style="flex:1; overflow-y:auto; font-size:13px; line-height:1.6; color:var(--text-main); font-family: 'Consolas', 'Courier New', monospace; background: var(--bg-main); padding: 15px; border-radius: 6px; border: 1px solid var(--border-color); white-space: pre-wrap; user-select: text; -webkit-user-select: text; cursor: auto;">CMA are for Created, Modified, Accessed (创建 修改 访问)
"dateC:", "dateM:", "dateA:"
"ageC:", "ageM:", "ageA:"

dateM: 20.05.2014 16:16:40 = exact timestamp
dateM: == 20.05.2014 16:16:40 = same
dateM: >= 20.05.2014 16:16:40 = then or later
dateM: 22.05.2014 = covers the whole day
dateM: 05/22/2014 = same
dateM: 2010.01.01 - = modified 2010 or later
dateM: dw 6-7 = on a weekend (Saturday and Sunday)
dateM: h 11 = at eleven o'clock
dateM: m 5 & dateM: d 1 = modified on the 1st of May (of any year)
dateM: dy 51 = modified on the 51st day of the year (the 20th of February of any year)

When adding two dates, convert to range syntax:
dateM: 19.05.2014 - 20.05.2014 = covers two whole days
dateM: 05/19/2014 - 05/20/2014 = same
dateM: 2014-05-19 - 2014-05-20 = same

ageM: d = modified today
ageM: w = modified this week
ageM: m = modified this month
ageM: y = modified this year
ageM: 1 d = modified yesterday
ageM: 1 w = modified last week
ageM: <= 30 n = modified in the last 30 mins
ageM: <= 3 h = modified in the last 3 hours
ageM: <= 7 d = modified last 7 days</div>
        </div>
    </div>

    <div id="confirm-modal" class="modal-overlay" style="z-index: 10005;">
        <div class="modal-content" style="width: 320px;">
            <h4 id="confirm-header" style="margin:0 0 10px 0; color:var(--red); font-size:15px; display:flex; gap:8px; align-items:center;">
                <span id="confirm-title-icon" v-html="delete"></span><span id="confirm-title-text" data-i18n="confirm_del_title">确认删除</span>
            </h4>
            <div id="confirm-msg" style="font-size:13px; color:var(--text-main); margin-bottom:15px; line-height: 1.5; word-break: break-all; white-space: pre-wrap;"></div>
            <div style="display:flex; justify-content:flex-end; gap:8px;">
                <button class="settings-btn" style="width:auto; padding:6px 16px;" onclick="closeConfirmModal()" data-i18n="cancel">取消</button>
                <button id="confirm-btn" class="action-btn" style="width:auto; padding:6px 16px; border:none; background:var(--red); color:white;" onclick="executeConfirm()" data-i18n="delete">删除</button>
            </div>
        </div>
    </div>

    <div id="settings-modal" class="modal-overlay">
        <div class="modal-content" style="width: 420px;">
            <h4 style="margin:0 0 15px 0; color:var(--primary); font-size:15px; display:flex; justify-content:space-between; align-items:center;">
                <div style="display:flex; gap:8px; align-items:center;"><span v-html="settings"></span> <span data-i18n="settings">系统设置</span></div>
                <div style="display:flex; gap:4px;">
                    <button class="tool-btn" style="width:24px; height:24px; color:var(--primary);" onclick="openGithub()" data-i18n-title="project_url" v-html="info"></button>
                    <button class="tool-btn" style="width:24px; height:24px; color:var(--primary);" onclick="openManual()" data-i18n-title="manual_title" v-html="help"></button>
                </div>
            </h4>
            
            <div style="display:flex; gap:10px; margin-bottom:15px;">
                <div style="flex:1;">
                    <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;" data-i18n="ui_theme">界面主题:</div>
                    <select id="cfg-theme" style="width:100%; box-sizing:border-box;">
                        <option value="dark" data-i18n="dark_theme">暗黑 (Dark)</option>
                        <option value="light" data-i18n="light_theme">浅色 (Light)</option>
                    </select>
                </div>
                <div style="flex:1;">
                    <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;" data-i18n="ui_lang">界面语言:</div>
                    <select id="cfg-lang" style="width:100%; box-sizing:border-box;">
                        <option value="zh-CN">简体中文</option>
                        <option value="zh-TW">繁體中文</option>
                        <option value="en">English</option>
                    </select>
                </div>
            </div>

            <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;" data-i18n="xy_path_hint">XYplorer 路径 (支持填写exe或纯文件夹路径):</div>
            <div style="display:flex; gap:8px; margin-bottom:15px; align-items:center;">
                <input type="text" id="cfg-xy-path" placeholder="E:\\XYplorer" style="flex:1; box-sizing:border-box; margin:0;">
                <button class="settings-btn" style="width:auto; padding:5px 12px; height: 29px; white-space: nowrap;" onclick="testXYplorer()"><span v-html="check"></span> <span data-i18n="test_xy_path">测试路径</span></button>
            </div>
            
            <div style="border-top:1px dashed var(--border-color); margin-bottom:15px;"></div>
            <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;" data-i18n="settings_ai_api">AI API 地址 (Ollama):</div>
            <input type="text" id="cfg-ai-api" placeholder="http://localhost:11434/api/generate" style="width:100%; box-sizing:border-box; margin-bottom:15px;">
            
            <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;" data-i18n="settings_ai_model">AI 模型名称 (如 qwen2.5:0.5b):</div>
            <input type="text" id="cfg-ai-model" placeholder="qwen2.5:0.5b" style="width:100%; box-sizing:border-box; margin-bottom:20px;">
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:20px;">
                <button class="settings-btn" onclick="exportData()"><span v-html="export"></span> <span data-i18n="export_data">导出工作区数据</span></button>
                <button class="settings-btn" onclick="document.getElementById('import-data-file').click()"><span v-html="importIco"></span> <span data-i18n="import_data">导入工作区数据</span></button>
                <input type="file" id="import-data-file" accept=".json" style="display:none;" onchange="importData(event)">
                
                <button class="settings-btn" onclick="exportConfig()"><span v-html="export"></span> <span data-i18n="export_config">导出软件配置</span></button>
                <button class="settings-btn" onclick="document.getElementById('import-config-file').click()"><span v-html="importIco"></span> <span data-i18n="import_config">导入软件配置</span></button>
                <input type="file" id="import-config-file" accept=".json" style="display:none;" onchange="importConfig(event)">
                
                <button class="settings-btn" style="grid-column: span 2;" onclick="checkUpdate()"><span v-html="info"></span> <span data-i18n="check_update">检查更新</span></button>
            </div>

            <div style="display:flex; justify-content:flex-end; gap:8px;">
                <button class="settings-btn" style="width:auto; padding:6px 16px;" onclick="closeSettings()" data-i18n="cancel">取消</button>
                <button class="action-btn btn-search" style="width:auto; padding:6px 16px; border:none;" onclick="saveSettings()" data-i18n="save">保存设置</button>
            </div>
        </div>
    </div>

    <div id="color-modal" class="modal-overlay">
        <div class="modal-content" style="width: 330px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <h4 style="margin:0; color:var(--text-main); font-size: 14px;" data-i18n="edit_color">修改颜色</h4>
            </div>
            <div style="display:flex; gap:8px; align-items:center; margin-bottom: 8px;">
                <input type="color" id="native-color">
                <input type="text" id="hex-input" placeholder="#FFFFFF" style="flex:1; text-transform: uppercase;">
            </div>
            
            <div class="history-row" style="border-top: none; padding-top: 0; align-items: center;">
                <div class="palette-title" data-i18n="custom">自定义</div>
                <div class="palette-colors" id="pal-custom" style="min-height: 24px;"></div>
                <button class="settings-btn" onclick="addCustomColor()" style="padding:2px 6px; font-size:11px;" data-i18n="fav_color">收藏色</button>
            </div>
            
            <div class="theme-tabs">
                <div class="tab-btn active" onclick="switchThemeTab('dark')" data-i18n="dark_theme">暗黑主题</div>
                <div class="tab-btn" onclick="switchThemeTab('light')" data-i18n="light_theme">浅色主题</div>
            </div>
            
            <div id="view-dark" class="theme-view active">
                <div class="palette-row"><div class="palette-title">Cyber</div><div class="palette-colors" id="pal-cyber"></div></div>
                <div class="palette-row"><div class="palette-title">Ocean</div><div class="palette-colors" id="pal-ocean"></div></div>
                <div class="palette-row"><div class="palette-title">Gold</div><div class="palette-colors" id="pal-gold"></div></div>
                <div class="palette-row"><div class="palette-title">Morandi D</div><div class="palette-colors" id="pal-morandi-d"></div></div>
            </div>

            <div id="view-light" class="theme-view">
                <div class="palette-row"><div class="palette-title">Summer</div><div class="palette-colors" id="pal-summer"></div></div>
                <div class="palette-row"><div class="palette-title">Macaron</div><div class="palette-colors" id="pal-macaron"></div></div>
                <div class="palette-row"><div class="palette-title">Wood</div><div class="palette-colors" id="pal-wood"></div></div>
                <div class="palette-row"><div class="palette-title">Morandi L</div><div class="palette-colors" id="pal-morandi-l"></div></div>
            </div>
            
            <div class="history-row" style="border-top: 1px solid var(--border-color);">
                <div class="palette-title" data-i18n="hist_color">历史用色</div>
                <div class="palette-colors" id="pal-history" style="min-height: 48px;"></div>
            </div>
            
            <div style="margin-top:10px; text-align:right;">
                <button class="settings-btn" style="display:inline-flex; width:auto; padding:4px 12px;" onclick="closeColorModal()" data-i18n="cancel">取消</button>
                <button class="action-btn btn-search" style="display:inline-flex; width:auto; padding:4px 12px; border:none;" onclick="applyColorModal()" data-i18n="confirm">确定</button>
            </div>
        </div>
    </div>

    <script>
        // ======= 安全字符串处理函数 (修复各类引号导致的 UI 渲染 Bug) =======
        function _e(str) { return String(str||'').replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\\\'").replace(/"/g, '&quot;'); }
        function _h(str) { return String(str||'').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

        const SVGS = {
            info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`,
            help: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
            search: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>`,
            add: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>`,
            importIco: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>`,
            export: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>`,
            clear: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 4H8l-7 8 7 8h13a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2z"></path><line x1="18" y1="9" x2="12" y2="15"></line><line x1="12" y1="9" x2="18" y2="15"></line></svg>`,
            pin: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="17" x2="12" y2="22"></line><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 11.7V6h1a1 1 0 0 0 0-2H8a1 1 0 0 0 0 2h1v5.7a2 2 0 0 1-1.11 1.64l-1.78.9A2 2 0 0 0 5 15.24Z"></path></svg>`,
            pinActive: `<svg viewBox="0 0 24 24" fill="var(--primary)" stroke="currentColor" stroke-width="2"><line x1="12" y1="17" x2="12" y2="22"></line><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 11.7V6h1a1 1 0 0 0 0-2H8a1 1 0 0 0 0 2h1v5.7a2 2 0 0 1-1.11 1.64l-1.78.9A2 2 0 0 0 5 15.24Z"></path></svg>`,
            settings: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06-.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>`,
            edit: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>`,
            swap: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 7L20 7M20 7L16 3M20 7L16 11M16 17L4 17M4 17L8 21M4 17L8 13"/></svg>`,
            tooltip: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>`,
            delete: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`,
            arrowRight: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>`,
            arrowDown: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>`,
            palette: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="13.5" cy="6.5" r=".5"></circle><circle cx="17.5" cy="10.5" r=".5"></circle><circle cx="8.5" cy="7.5" r=".5"></circle><circle cx="6.5" cy="12.5" r=".5"></circle><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10c1.38 0 2.5-1.12 2.5-2.5 0-.53-.21-1.04-.59-1.41-.37-.38-.59-.89-.59-1.43 0-1.12 1.12-2.04 2.5-2.04h1.61c2.8 0 5.07-2.27 5.07-5.07C22 7.03 17.52 2 12 2z"></path></svg>`,
            move: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>`,
            copy: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`,
            expand: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>`,
            minimize: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline><line x1="14" y1="10" x2="21" y2="3"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>`,
            check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
            refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"></polyline><polyline points="23 20 23 14 17 14"></polyline><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"></path></svg>`,
            selectAll: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><path d="M9 12l2 2 4-4"></path></svg>`,
            excludeAll: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="9" x2="15" y2="15"></line><line x1="15" y1="9" x2="9" y2="15"></line></svg>`,
            tag: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"></path><line x1="7" y1="7" x2="7.01" y2="7"></line></svg>`,
            warning: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
            checkCircle: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`,
            xCircle: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`
        };
        
        const I18N = {
            'zh-CN': {
                '默认工作区': '默认工作区', '未分类': '未分类', '项目状态': '项目状态', 
                '重要': '重要', '紧急': '紧急', '待办': '待办', '搁置': '搁置', '完成': '完成',
                '?*': '含标签', '""': '无标签',
                
                'checking_update': '检查中...',
                'search_tags': '搜索标签',
                'match_desc': '描述',
                'search_in': '范围:', 's_group': '标签组', 's_tag': '标签', 's_remark': '备注', 's_desc': '描述',
                'search_ph': '输入标签名或备注 (上下键选择, Enter)', 'fuzzy': '模糊', 'exact': '精准', 'remember_search': '记忆搜索', 'remember_search_hint': '开启后，下次打开自动恢复上次的搜索词', 'search_no_input': '输入文字以开始检索...', 'search_no_match': '无匹配结果', 'search_limit': '仅显示前 {n} 条...',
                'domain_general': '通用领域', 'domain_audio': '音效 / 音频', 'domain_video': '影视 / 视频', 'domain_design': '设计 / 图像素材', 'domain_photo': '摄影 / 照片', 'domain_code': '编程 / 代码', 'domain_fashion': '时尚 / 穿搭', 'domain_office': '文档 / 办公',
                'batch_ucs_name': '批量文件名转UCS标签',
                'batch_ucs': '批量打UCS标签', 'toast_ucs_processing': '正在处理UCS标签，请稍候...', 'toast_ucs_success': '成功为 {n} 个文件添加了UCS标签！', 'toast_ucs_fail': '处理失败: ',
                'ai_filename_dict': 'AI 文件名匹配UCS标签 (不激活)', 'ai_filename_auto': 'AI 文件名自动生成标签 (激活)', 'ai_content_auto': 'AI 文本内容自动生成标签 (激活)', 'ai_filename_auto_en_zh': 'AI 文件名自动生成标签-英中 (激活)',
                'toast_ai_processing': 'AI 正在思考并处理标签，请耐心等待...', 'toast_ai_success': 'AI 处理完成！成功为 {n} 个文件打标。', 'toast_ai_fail': 'AI 处理失败: ',
                'settings_ai_api': 'AI API 地址 (Ollama):', 'settings_ai_model': 'AI 模型名称 (如 qwen2.5:0.5b):',
                'swap_alias': '切换显示别名/备注', 'toggle_tooltip': '开启/关闭悬浮提示',
                'ctx_select_or': '全选组内标签 (或)', 'ctx_exclude_all': '排除组内标签 (非)', 'ctx_clear_group': '清除组内状态',
                'export_workspace': '导出当前工作区', 'import_workspace': '导入到当前工作区', 'toast_export_ok': '工作区导出成功', 'toast_export_fail': '工作区导出取消或失败', 'toast_import_ok': '工作区导入成功', 'toast_import_err': '工作区导入失败',
                'set_alias': '设置翻译/备注', 'alias_remark': '别名/备注', 'descriptions': '描述', 'add_desc': '添加描述',
                'log_import_cfg_ok': '成功导入软件设置并重启', 'log_import_cfg_err': '导入软件设置失败: 解析错误', 'log_func_color_rst': '功能按钮颜色已恢复默认', 'log_sync_fail': '同步失败: ', 'log_ws_color_upd': '工作区颜色已更新', 'log_ws_color_rst': '工作区颜色已恢复默认', 'log_ws_keep_one': '至少需保留一个工作区！', 'log_tag_del': '标签 "{tag}" 已删除', 'log_grp_color_upd': '分组颜色已更新', 'log_grp_color_rst': '分组颜色已恢复默认', 'log_hist_del': '历史记录已删除', 'log_update_err': '检查更新异常: ',
                'test_xy_path': '测试路径', 'toast_test_ok': 'XYplorer 连接成功！', 'toast_test_fail': '未找到 XYplorer 或调用失败，请检查路径',
                'log_import_ok': '成功导入工作区数据', 'log_import_err': '导入数据失败: 解析错误', 'log_color_upd': '颜色已更新', 'log_color_rst': '颜色已恢复默认', 'log_sync_ok': 'XYplorer 批注同步成功', 'log_ws_del': '工作区已删除', 'log_uncat_rst': '未分类组已恢复默认标签',
                'check_update': '检查更新', 'project_url': '项目开源主页', 'update_found': '发现新版本！', 'go_to_download': '是否前往 GitHub 下载？', 'is_latest': '当前已是最新版本', 'update_fail': '检查更新失败，请检查网络连接',
                'search': '搜索', 'add_tag': '打标签', 'read_tag': '读标签', 'clear': '清空',
                'tab_type': '类型', 'tab_path': '路径', 'tab_name': '文件名', 'tab_remark': '备注', 'tab_label': '标注', 'tab_rating': '评分', 'tab_size': '大小/日期',
                'hint_type': '左键：包含 (OR) | 右键：排除 (NOT) | 拖拽排序', 'custom_ext': '自定义后缀名',
                'hint_path': '输入路径，单个如 C:\\\\ ；多个如 C:\\\\|D:\\\\ ；* (全盘)', 'desktop': '桌面', 'all_drives': '全盘',
                'hint_name': '名字包含A排除B，如 A+B,C-D 会智能转换为 (A & B) | (C & !D)',
                'hint_remark': '备注包含A排除B，如 A+B,C-D 会智能转换为 (A & B) | (C & !D)',
                'has_remark': '含备注', 'no_remark': '无备注',
                'hint_label': '点击选择标注，支持拖拽排序', 'sync_xy': '同步XYplorer批注', 'has_label': '含标注', 'no_label': '无标注',
                'hint_rating': '点击选择评分 (支持多选与拖拽)', 'unrated': '未评分',
                'size': '文件大小', 'date': '日期时间', 'date_c': '创建日期', 'date_m': '修改日期', 'date_a': '访问日期', 'age_c': '创建时间', 'age_m': '修改时间', 'age_a': '访问时间', 'value': '数值',
                'tag_group': '标签组',
                'edit_color': '修改分类颜色', 'reset_color': '恢复默认颜色', 'reset_uncat': '恢复默认标签', 'add_sub': '新建子组', 'batch_add_sub': '批量新建子组',
                'move_to': '移动到工作区', 'copy_to': '复制到工作区', 'del_group': '删除分组',
                'rename_group': '重命名分组', 'collapse_leaf': '折叠子组', 'expand_all_sub': '展开子组', 'add_tag_menu': '新建标签', 'batch_add_tag_menu': '批量新建标签',
                'edit_bg': '修改背景颜色', 'batch_add': '批量新建',
                'edit_tab_color': '修改选项卡颜色', 'rename_ws': '重命名工作区', 'dup_ws': '重复工作区', 'del_ws': '删除工作区',
                'paste_hint': '请在此处粘贴 (Ctrl+V) 要批量添加的项，每行一个。',
                'settings': '系统设置', 'ui_theme': '界面主题:', 'dark_theme': '暗黑 (Dark)', 'light_theme': '浅色 (Light)',
                'ui_lang': '界面语言:', 'xy_path_hint': 'XYplorer 路径 (支持填写exe或纯文件夹路径):',
                'export_data': '导出工作区数据', 'import_data': '导入工作区数据', 'export_config': '导出软件配置', 'import_config': '导入软件配置',
                'save': '保存设置', 'cancel': '取消', 'confirm': '确定', 'custom': '自定义', 'fav_color': '收藏色', 'hist_color': '历史用色',
                'search_title': '发送搜索', 'tag_title': '写入当前激活标签到所选文件', 'read_title': '读取选中文件标签并智能激活与归类', 'clear_title': '清除工作区全部复合筛选与激活标签',
                'clear_filter': '清除该组所有过滤', 'save_record': '确认并保存记录', 'clear_tree': '清除标签树状态', 'toggle_all': '展开/折叠全部',
                'expand_active': '仅展开激活组', 'show_active': '仅显示激活组', 'edit_mode': '进入/退出编辑模式', 'add_root': '新建根级分组 (右键可批量新建)',
                'new_ws': '新建工作区', 'view_all_ws': '查看所有工作区', 'pin_top': '窗口置顶',
                'syntax_ph': '自动生成 XYplorer 高级语法...', 'ph_path': '输入搜索路径...', 'ph_name': '包含A排除B，如 A+B,C-D', 'ph_remark': '包含A排除B，如 A+B,C-D',
                'no_record': '无记录', 'no_other_ws': '无其他工作区', 'delete': '删除',
                'confirm_del_ws': '确定要删除工作区 [{ws}] 吗？',
                'confirm_del_title': '确认删除',
                'manual_title': '使用指南',
                'batch_ext_custom': '自定义批量添加...', 'batch_ext_text': '批量添加 文本 后缀', 'batch_ext_image': '批量添加 图像 后缀', 'batch_ext_audio': '批量添加 音频 后缀', 'batch_ext_video': '批量添加 视频 后缀', 'batch_ext_doc': '批量添加 文档 后缀',
                'batch_processing': '批量处理中...',
                'batch_warning': 'XYplorer完成批量打签前请勿操作！',
                'batch_status': '正在分析文件并生成指令...',
                'batch_cancel': '取消操作',
                'batch_exit': '退出批量操作',
                'cancelling': '正在取消...',
                'batch_sent_cmds': '已发送命令数: {c} / 需处理文件总数: {t}',
                'ai_processing_status': 'AI 正在分析文件: {c} / {t}',
                
                'toast_ext_added': '自定义后缀已添加', 'toast_sync_ok': '同步成功', 'toast_sync_fail': '同步失败', 'toast_hist_saved': '历史记录已保存', 'toast_ws_keep_one': '至少需保留一个工作区！', 'toast_ws_deleted': '工作区已删除', 'toast_save_ok': '保存成功', 'toast_export_data_ok': '导出工作区数据成功', 'toast_export_config_ok': '导出软件配置成功', 'toast_import_data_ok': '导入工作区数据成功', 'toast_import_error': '导入失败: 解析错误', 'toast_batch_add_ok': '批量添加成功', 'toast_no_tags_act': '执行失败: 当前未激活任何要添加或移除的标签', 'toast_tag_cmd_sent': '标签修改指令已发送', 'toast_reading_clip': '正在读取剪贴板提取标签...', 'toast_no_docs': '未找到说明文档，请检查程序目录下的 Docs 文件夹', 'toast_clip_empty': '读取失败: 剪贴板为空', 'toast_clip_long': '内容较长或包含多行，请手动确认', 'toast_read_fail': '读取失败: 未解析到有效标签', 'toast_read_none': '未解析到有效标签', 'toast_read_success': '成功读取并激活 {n} 个标签', 'toast_no_uncat_op': '无法操作未分类组',

                'tt_photo': '所有可能包含 Exif 数据的图片格式', 'tt_media': '音频与视频',
                
                'syn_path': '路径: ', 'syn_all_drives': '* (全盘搜索)', 'syn_tags': '标签: ', 'syn_type_name': '类型/名称: ', 'syn_attr_rating': '属性/评分: ', 'syn_size_date': '大小/日期: '
            },
            'zh-TW': {
                '默认工作区': '預設工作區', '未分类': '未分類', '项目状态': '專案狀態', 
                '重要': '重要', '紧急': '緊急', '待办': '待辦', '搁置': '擱置', '完成': '完成',
                '?*': '含標籤', '""': '無標籤',
                
                '文本': '文字', '图像': '影像', '照片': '相片', '音频': '音訊', '视频': '視訊', '媒体': '媒體', '字体': '字型', '矢量图': '向量圖', '网页': '網頁', '文档': '文件', '压缩包': '壓縮檔', '可执行': '執行檔', '文件夹': '資料夾',
                
                'checking_update': '檢查中...',
                'search_tags': '搜尋標籤',
                'match_desc': '描述',
                'search_in': '範圍:', 's_group': '標籤組', 's_tag': '標籤', 's_remark': '備註', 's_desc': '描述',
                'search_ph': '輸入標籤名或備註 (上下鍵選擇, Enter)', 'fuzzy': '模糊', 'exact': '精準', 'remember_search': '記憶搜尋', 'remember_search_hint': '開啟後，下次打開自動恢復上次的搜尋詞', 'search_no_input': '輸入文字以開始檢索...', 'search_no_match': '無匹配結果', 'search_limit': '僅顯示前 {n} 條...',
                'domain_general': '通用領域', 'domain_audio': '音效 / 音訊', 'domain_video': '影視 / 視訊', 'domain_design': '設計 / 影像素材', 'domain_photo': '攝影 / 照片', 'domain_code': '程式設計 / 程式碼', 'domain_fashion': '時尚 / 穿搭', 'domain_office': '文件 / 辦公',
                'batch_ucs_name': '批次檔名轉UCS標籤',
                'batch_ucs': '批次打UCS標籤', 'toast_ucs_processing': '正在處理UCS標籤，請稍候...', 'toast_ucs_success': '成功為 {n} 個檔案新增了UCS標籤！', 'toast_ucs_fail': '處理失敗: ',
                'ai_filename_dict': 'AI 檔名匹配UCS標籤 (不啟動)', 'ai_filename_auto': 'AI 檔名自動生成標籤 (啟動)', 'ai_content_auto': 'AI 文本內容自動生成標籤 (啟動)', 'ai_filename_auto_en_zh': 'AI 檔名自動生成標籤-英中 (啟動)',
                'toast_ai_processing': 'AI 正在思考並處理標籤，請耐心等待...', 'toast_ai_success': 'AI 處理完成！成功為 {n} 個檔案打標。', 'toast_ai_fail': 'AI 處理失敗: ',
                'settings_ai_api': 'AI API 地址 (Ollama):', 'settings_ai_model': 'AI 模型名稱 (如 qwen2.5:0.5b):',
                'swap_alias': '切換顯示別名/備註', 'toggle_tooltip': '開啟/關閉懸浮提示',
                'ctx_select_or': '全選群組標籤 (或)', 'ctx_exclude_all': '排除群組標籤 (非)', 'ctx_clear_group': '清除群組狀態',
                'export_workspace': '匯出當前工作區', 'import_workspace': '匯入到當前工作區', 'toast_export_ok': '工作區匯出成功', 'toast_export_fail': '工作區匯出取消或失敗', 'toast_import_ok': '工作區匯入成功', 'toast_import_err': '工作區匯入失敗',
                'set_alias': '設定翻譯/備註', 'alias_remark': '別名/備註', 'descriptions': '描述', 'add_desc': '新增描述',
                'log_import_cfg_ok': '成功匯入軟體設定並重啟', 'log_import_cfg_err': '匯入軟體設定失敗: 解析錯誤', 'log_func_color_rst': '功能按鈕顏色已恢復預設', 'log_sync_fail': '同步失敗: ', 'log_ws_color_upd': '工作區顏色已更新', 'log_ws_color_rst': '工作區顏色已恢復預設', 'log_ws_keep_one': '至少需保留一個工作區！', 'log_tag_del': '標籤 "{tag}" 已刪除', 'log_grp_color_upd': '群組顏色已更新', 'log_grp_color_rst': '群組顏色已恢復預設', 'log_hist_del': '歷史紀錄已刪除', 'log_update_err': '檢查更新異常: ',
                'test_xy_path': '測試路徑', 'toast_test_ok': 'XYplorer 連接成功！', 'toast_test_fail': '未找到 XYplorer 或呼叫失敗，請檢查路徑',
                'log_import_ok': '成功匯入工作區資料', 'log_import_err': '匯入資料失敗: 解析錯誤', 'log_color_upd': '顏色已更新', 'log_color_rst': '顏色已恢復預設', 'log_sync_ok': 'XYplorer 批註同步成功', 'log_ws_del': '工作區已刪除', 'log_uncat_rst': '未分類群組已恢復預設標籤',
                'check_update': '檢查更新', 'project_url': '專案開源主頁', 'update_found': '發現新版本！', 'go_to_download': '是否前往 GitHub 下載？', 'is_latest': '當前已是最新版本', 'update_fail': '檢查更新失敗，請檢查網路連線',
                'search': '搜尋', 'add_tag': '打標籤', 'read_tag': '讀標籤', 'clear': '清空',
                'tab_type': '類型', 'tab_path': '路徑', 'tab_name': '檔名', 'tab_remark': '備註', 'tab_label': '標註', 'tab_rating': '評分', 'tab_size': '大小/日期',
                'hint_type': '左鍵：包含 (OR) | 右鍵：排除 (NOT) | 拖曳排序', 'custom_ext': '自訂副檔名',
                'hint_path': '輸入路徑，單個如 C:\\\\ ；多個如 C:\\\\|D:\\\\ ；* (全盤)', 'desktop': '桌面', 'all_drives': '全盤',
                'hint_name': '名字包含A排除B，如 A+B,C-D 會轉換為 (A & B) | (C & !D)',
                'hint_remark': '備註包含A排除B，如 A+B,C-D 會轉換為 (A & B) | (C & !D)',
                'has_remark': '含備註', 'no_remark': '無備註',
                'hint_label': '點擊選擇標註，支援拖曳排序', 'sync_xy': '同步XYplorer批註', 'has_label': '含標註', 'no_label': '無標註',
                'hint_rating': '點擊選擇評分 (支援多選與拖曳)', 'unrated': '未評分',
                'size': '檔案大小', 'date': '日期時間', 'date_c': '建立日期', 'date_m': '修改日期', 'date_a': '存取日期', 'age_c': '建立時間', 'age_m': '修改時間', 'age_a': '存取時間', 'value': '數值',
                'tag_group': '標籤群組',
                'edit_color': '修改顏色', 'reset_color': '恢復預設顏色', 'reset_uncat': '恢復預設標籤', 'add_sub': '新建子群組', 'batch_add_sub': '批次新建子群組',
                'move_to': '移動到工作區', 'copy_to': '複製到工作區', 'del_group': '刪除群組',
                'rename_group': '重新命名群組', 'collapse_leaf': '摺疊子群組', 'expand_all_sub': '展開子群組', 'add_tag_menu': '新建標籤', 'batch_add_tag_menu': '批次新建標籤',
                'edit_bg': '修改背景顏色', 'batch_add': '批次新建',
                'edit_tab_color': '修改索引標籤顏色', 'rename_ws': '重新命名工作區', 'dup_ws': '重複工作區', 'del_ws': '刪除工作區',
                'paste_hint': '請在此處貼上 (Ctrl+V) 要批次新增的項目，每行一個。',
                'settings': '系統設定', 'ui_theme': '介面主題:', 'dark_theme': '暗黑 (Dark)', 'light_theme': '淺色 (Light)',
                'ui_lang': '介面語言:', 'xy_path_hint': 'XYplorer 路徑 (支援填寫exe或純資料夾路徑):',
                'export_data': '匯出工作區資料', 'import_data': '匯入工作區資料', 'export_config': '匯出軟體設定', 'import_config': '匯入軟體設定',
                'save': '儲存設定', 'cancel': '取消', 'confirm': '確定', 'custom': '自訂', 'fav_color': '收藏色', 'hist_color': '歷史用色',
                'search_title': '發送搜尋', 'tag_title': '寫入當前啟動標籤到所選檔案', 'read_title': '讀取選中檔案標籤並智慧啟動與分類', 'clear_title': '清除工作區全部複合篩選與啟動標籤',
                'clear_filter': '清除該組所有過濾', 'save_record': '確認並儲存紀錄', 'clear_tree': '清除標籤樹狀態', 'toggle_all': '展開/摺疊全部',
                'expand_active': '僅展開啟動群組', 'show_active': '僅顯示啟動群組', 'edit_mode': '進入/退出編輯模式', 'add_root': '新建根級群組 (右鍵可批次新建)',
                'new_ws': '新建工作區', 'view_all_ws': '查看所有工作區', 'pin_top': '視窗置頂',
                'syntax_ph': '自動產生 XYplorer 高級語法...', 'ph_path': '輸入搜尋路徑...', 'ph_name': '包含A排除B，如 A+B,C-D', 'ph_remark': '包含A排除B，如 A+B,C-D',
                'no_record': '無紀錄', 'no_other_ws': '無其他工作區', 'delete': '刪除',
                'confirm_del_ws': '確定要刪除工作區 [{ws}] 嗎？',
                'confirm_del_title': '確認刪除',
                'manual_title': '使用指南',
                'batch_ext_custom': '自訂批次新增...', 'batch_ext_text': '批次新增 文字 副檔名', 'batch_ext_image': '批次新增 影像 副檔名', 'batch_ext_audio': '批次新增 音訊 副檔名', 'batch_ext_video': '批次新增 視訊 副檔名', 'batch_ext_doc': '批次新增 文件 副檔名',
                'batch_processing': '批次處理中...',
                'batch_warning': 'XYplorer完成批次打籤前請勿操作！',
                'batch_status': '正在分析檔案並生成指令...',
                'batch_cancel': '取消操作',
                'batch_exit': '退出批次操作',
                'cancelling': '正在取消...',
                'batch_sent_cmds': '已發送命令數: {c} / 需處理檔案總數: {t}',
                'ai_processing_status': 'AI 正在分析檔案: {c} / {t}',
                
                'toast_ext_added': '自訂副檔名已新增', 'toast_sync_ok': '同步成功', 'toast_sync_fail': '同步失敗', 'toast_hist_saved': '歷史紀錄已儲存', 'toast_ws_keep_one': '至少需保留一個工作區！', 'toast_ws_deleted': '工作區已刪除', 'toast_save_ok': '儲存成功', 'toast_export_data_ok': '匯出工作區資料成功', 'toast_export_config_ok': '匯出軟體設定成功', 'toast_import_data_ok': '匯入工作區資料成功', 'toast_import_error': '匯入失敗: 解析錯誤', 'toast_batch_add_ok': '批次新增成功', 'toast_no_tags_act': '執行失敗: 當前未啟動任何要新增或移除的標籤', 'toast_tag_cmd_sent': '標籤修改指令已發送', 'toast_reading_clip': '正在讀取剪貼簿提取標籤...', 'toast_no_docs': '未找到說明文件，請檢查程式目錄下的 Docs 資料夾', 'toast_clip_empty': '讀取失敗: 剪貼簿為空', 'toast_clip_long': '內容較長或包含多行，請手動確認', 'toast_read_fail': '讀取失敗: 未解析到有效標籤', 'toast_read_none': '未解析到有效標籤', 'toast_read_success': '成功讀取並啟動 {n} 個標籤', 'toast_no_uncat_op': '無法操作未分類群組',

                'tt_photo': '所有可能包含 Exif 資料的影像格式', 'tt_media': '音訊與視訊',
                
                'syn_path': '路徑: ', 'syn_all_drives': '* (全盤搜尋)', 'syn_tags': '標籤: ', 'syn_type_name': '類型/名稱: ', 'syn_attr_rating': '屬性/評分: ', 'syn_size_date': '大小/日期: '
            },
            'en': {
                '默认工作区': 'Default Workspace', '未分类': 'Uncategorized', '项目状态': 'Project Status', 
                '重要': 'Important', '紧急': 'Urgent', '待办': 'To Do', '搁置': 'On Hold', '完成': 'Completed',
                '?*': 'Has Tag', '""': 'No Tag',
                
                '文本': 'Text', '图像': 'Image', '照片': 'Photo', '音频': 'Audio', '视频': 'Video', '媒体': 'Media', '字体': 'Font', '矢量图': 'Vector', '网页': 'Web', '文档': 'Document', '压缩包': 'Archive', '可执行': 'Executable', '文件夹': 'Folder',
                
                'checking_update': 'Checking...',
                'search_tags': 'Search Tags',
                'match_desc': 'Desc',
                'search_in': 'In:', 's_group': 'Group', 's_tag': 'Tag', 's_remark': 'Remark', 's_desc': 'Desc',
                'search_ph': 'Search tags/remarks (Up/Down, Enter)', 'fuzzy': 'Fuzzy', 'exact': 'Exact', 'remember_search': 'Remember', 'remember_search_hint': 'Restore last search query', 'search_no_input': 'Type to start searching...', 'search_no_match': 'No match found', 'search_limit': 'Showing first {n} results...',
                'domain_general': 'General', 'domain_audio': 'Audio / SFX', 'domain_video': 'Video / Film', 'domain_design': 'Design / Assets', 'domain_photo': 'Photography', 'domain_code': 'Programming / Code', 'domain_fashion': 'Fashion', 'domain_office': 'Docs / Office',
                'batch_ucs_name': 'Batch Filename to UCS Tags',
                'batch_ucs': 'Batch UCS Tags', 'toast_ucs_processing': 'Processing UCS Tags...', 'toast_ucs_success': 'Successfully added UCS tags to {n} files!', 'toast_ucs_fail': 'Failed: ',
                'ai_filename_dict': 'AI Filename -> UCS Tags (No Active)', 'ai_filename_auto': 'AI Filename -> Auto Tags (Active)', 'ai_content_auto': 'AI Content -> Auto Tags (Active)', 'ai_filename_auto_en_zh': 'AI Filename -> Auto Tags En/Zh (Active)',
                'toast_ai_processing': 'AI is thinking and processing tags...', 'toast_ai_success': 'AI Tagging Complete! Successfully tagged {n} files.', 'toast_ai_fail': 'AI Process failed: ',
                'settings_ai_api': 'AI API URL (Ollama):', 'settings_ai_model': 'AI Model Name (e.g. qwen2.5:0.5b):',
                'swap_alias': 'Toggle Alias/Remark', 'toggle_tooltip': 'Toggle Hover Tooltip',
                'ctx_select_or': 'Select All in Group (OR)', 'ctx_exclude_all': 'Exclude All in Group (NOT)', 'ctx_clear_group': 'Clear Group State',
                'export_workspace': 'Export Workspace', 'import_workspace': 'Import Workspace', 'toast_export_ok': 'Workspace exported', 'toast_export_fail': 'Export cancelled or failed', 'toast_import_ok': 'Workspace imported', 'toast_import_err': 'Workspace import failed',
                'set_alias': 'Set Translation/Remark', 'alias_remark': 'Alias/Remark', 'descriptions': 'Descriptions', 'add_desc': 'Add Description',
                'log_import_cfg_ok': 'App config imported successfully, restarting', 'log_import_cfg_err': 'Failed to import app config: Parsing error', 'log_func_color_rst': 'Action button color restored to default', 'log_sync_fail': 'Sync failed: ', 'log_ws_color_upd': 'Workspace color updated', 'log_ws_color_rst': 'Workspace color restored to default', 'log_ws_keep_one': 'At least one workspace must be kept!', 'log_tag_del': 'Tag "{tag}" deleted', 'log_grp_color_upd': 'Group color updated', 'log_grp_color_rst': 'Group color restored to default', 'log_hist_del': 'History deleted', 'log_update_err': 'Update check exception: ',
                'test_xy_path': 'Test Path', 'toast_test_ok': 'XYplorer connected successfully!', 'toast_test_fail': 'XYplorer not found or failed, check path',
                'log_import_ok': 'Workspace data imported successfully', 'log_import_err': 'Import failed: Parsing error', 'log_color_upd': 'Color updated successfully', 'log_color_rst': 'Color restored to default', 'log_sync_ok': 'XYplorer labels synced successfully', 'log_ws_del': 'Workspace deleted', 'log_uncat_rst': 'Uncategorized group restored to default tags',
                'check_update': 'Check for Updates', 'project_url': 'Project Homepage', 'update_found': 'New version available!', 'go_to_download': 'Go to GitHub to download?', 'is_latest': 'You are using the latest version', 'update_fail': 'Update check failed, please check network',
                'search': 'Search', 'add_tag': 'Tag', 'read_tag': 'Read', 'clear': 'Clear',
                'tab_type': 'Type', 'tab_path': 'Path', 'tab_name': 'Name', 'tab_remark': 'Remark', 'tab_label': 'Label', 'tab_rating': 'Rating', 'tab_size': 'Size/Date',
                'hint_type': 'Left-click: Include (OR) | Right-click: Exclude (NOT) | Drag to sort', 'custom_ext': 'Custom Ext',
                'hint_path': 'Enter path, single e.g. C:\\\\ ; multiple e.g. C:\\\\|D:\\\\ ; * (All)', 'desktop': 'Desktop', 'all_drives': 'All Drives',
                'hint_name': 'Include A exclude B, e.g. A+B,C-D -> (A & B) | (C & !D)',
                'hint_remark': 'Include A exclude B, e.g. A+B,C-D -> (A & B) | (C & !D)',
                'has_remark': 'Has Remark', 'no_remark': 'No Remark',
                'hint_label': 'Click to select label, drag to sort', 'sync_xy': 'Sync XY Labels', 'has_label': 'Has Label', 'no_label': 'No Label',
                'hint_rating': 'Click to select rating (multi-select & drag to sort)', 'unrated': 'Unrated',
                'size': 'File Size', 'date': 'Date/Time', 'date_c': 'Created', 'date_m': 'Modified', 'date_a': 'Accessed', 'age_c': 'Age C', 'age_m': 'Age M', 'age_a': 'Age A', 'value': 'Value',
                'tag_group': 'Tags Group',
                'edit_color': 'Edit Color', 'reset_color': 'Reset Color', 'reset_uncat': 'Restore Default Tags', 'add_sub': 'New Subgroup', 'batch_add_sub': 'Batch New Subgroup',
                'move_to': 'Move to Workspace', 'copy_to': 'Copy to Workspace', 'del_group': 'Delete Group',
                'rename_group': 'Rename Group', 'collapse_leaf': 'Collapse Leaf Groups', 'expand_all_sub': 'Expand All Subgroups', 'add_tag_menu': 'New Tag', 'batch_add_tag_menu': 'Batch New Tag',
                'edit_bg': 'Edit Background Color', 'batch_add': 'Batch Add',
                'edit_tab_color': 'Edit Tab Color', 'rename_ws': 'Rename Workspace', 'dup_ws': 'Duplicate Workspace', 'del_ws': 'Delete Workspace',
                'paste_hint': 'Paste (Ctrl+V) items here, one per line.',
                'settings': 'Settings', 'ui_theme': 'UI Theme:', 'dark_theme': 'Dark', 'light_theme': 'Light',
                'ui_lang': 'UI Language:', 'xy_path_hint': 'XYplorer Path (.exe or folder):',
                'export_data': 'Export Workspace Data', 'import_data': 'Import Workspace Data', 'export_config': 'Export App Config', 'import_config': 'Import App Config',
                'save': 'Save', 'cancel': 'Cancel', 'confirm': 'OK', 'custom': 'Custom', 'fav_color': 'Favorite', 'hist_color': 'History',
                'search_title': 'Execute Search', 'tag_title': 'Apply active tags to selected files', 'read_title': 'Read tags from files & auto-activate', 'clear_title': 'Clear all filters and active tags',
                'clear_filter': 'Clear all filters in this group', 'save_record': 'Confirm & save history', 'clear_tree': 'Clear tag tree state', 'toggle_all': 'Expand/Collapse All',
                'expand_active': 'Expand active groups only', 'show_active': 'Show active groups only', 'edit_mode': 'Toggle Edit Mode', 'add_root': 'Add root group (Right click to batch add)',
                'new_ws': 'New Workspace', 'view_all_ws': 'View all workspaces', 'pin_top': 'Pin to top',
                'syntax_ph': 'Auto-generate XYplorer advanced syntax...', 'ph_path': 'Enter search path...', 'ph_name': 'Include A exclude B, e.g. A+B,C-D', 'ph_remark': 'Include A exclude B, e.g. A+B,C-D',
                'no_record': 'No records', 'no_other_ws': 'No other workspaces', 'delete': 'Delete',
                'confirm_del_ws': 'Are you sure you want to delete workspace [{ws}]?',
                'confirm_del_title': 'Confirm Delete',
                'manual_title': 'User Guide',
                'batch_ext_custom': 'Custom Batch Add...', 'batch_ext_text': 'Batch Add Text Exts', 'batch_ext_image': 'Batch Add Image Exts', 'batch_ext_audio': 'Batch Add Audio Exts', 'batch_ext_video': 'Batch Add Video Exts', 'batch_ext_doc': 'Batch Add Doc Exts',
                'batch_processing': 'Batch Processing...',
                'batch_warning': 'Do NOT operate until XYplorer finishes tagging!',
                'batch_status': 'Analyzing files and generating commands...',
                'batch_cancel': 'Cancel',
                'batch_exit': 'Exit Batch',
                'cancelling': 'Cancelling...',
                'batch_sent_cmds': 'Sent Commands: {c} / Total Files: {t}',
                'ai_processing_status': 'AI Analyzing: {c} / {t}',
                
                'toast_ext_added': 'Custom extension added', 'toast_sync_ok': 'Sync successful', 'toast_sync_fail': 'Sync failed', 'toast_hist_saved': 'History saved', 'toast_ws_keep_one': 'At least one workspace must be kept!', 'toast_ws_deleted': 'Workspace deleted', 'toast_save_ok': 'Saved successfully', 'toast_export_data_ok': 'Workspace data exported successfully', 'toast_export_config_ok': 'App config exported successfully', 'toast_import_data_ok': 'Workspace data imported successfully', 'toast_import_error': 'Import failed: Parsing error', 'toast_batch_add_ok': 'Batch add successful', 'toast_no_tags_act': 'Failed: No active tags to add or remove', 'toast_tag_cmd_sent': 'Tag modification command sent', 'toast_reading_clip': 'Reading clipboard for tags...', 'toast_no_docs': 'Manual not found, please check the Docs folder', 'toast_clip_empty': 'Read failed: Clipboard is empty', 'toast_clip_long': 'Content is long or multi-line, please confirm manually', 'toast_read_fail': 'Read failed: No valid tags parsed', 'toast_read_none': 'No valid tags parsed', 'toast_read_success': 'Successfully read and activated {n} tags', 'toast_no_uncat_op': 'Cannot operate on Uncategorized group',

                'tt_photo': 'All image formats that may contain Exif data.', 'tt_media': 'Audio & Video',
                
                'syn_path': 'Path: ', 'syn_all_drives': '* (All Drives Search)', 'syn_tags': 'Tags: ', 'syn_type_name': 'Type/Name: ', 'syn_attr_rating': 'Attr/Rating: ', 'syn_size_date': 'Size/Date: '
            }
        };

        function renderSVGs(root) {
            (root || document).querySelectorAll('[v-html]').forEach(el => { 
                let key = el.getAttribute('v-html');
                if (SVGS[key]) el.innerHTML = SVGS[key]; 
            });
        }
        
        let allTreeData = /*__INIT_DATA__*/{}; 
        let configData = /*__INIT_CONFIG__*/{};
        
        function t(key) {
            let lang = configData.lang || 'zh-CN';
            if(I18N[lang] && I18N[lang][key]) return I18N[lang][key];
            return I18N['zh-CN'][key] || key;
        }

        // --- 核心修复：新增系统级词汇专用翻译（防止误伤用户同名标签） ---
        function sysT(key) {
            const sysKeys = ['默认工作区', '未分类', '项目状态', '重要', '紧急', '待办', '搁置', '完成', '?*', '""'];
            if (sysKeys.includes(key)) return t(key);
            return key;
        }

        function reverseSysT(val) {
            const sysKeys = ['默认工作区', '未分类', '项目状态', '重要', '紧急', '待办', '搁置', '完成', '?*', '""'];
            let lang = configData.lang || 'zh-CN';
            let dict = I18N[lang] || I18N['zh-CN'];
            for (let k of sysKeys) {
                if (dict[k] === val) return k;
            }
            // 兜底
            for (let k of sysKeys) {
                if (I18N['zh-CN'][k] === val) return k;
            }
            return val;
        }

        // --- 进化：高维标签解析引擎 (名称@@别名@@@描述1@@@描述2...) ---
        function parseTag(raw) {
            if (raw.includes('@@@')) {
                let descParts = raw.split('@@@');
                let basePart = descParts[0];
                let aliasParts = basePart.split('@@');
                return { name: aliasParts[0], alias: aliasParts.length > 1 ? aliasParts[1] : '', descs: descParts.slice(1), raw: raw };
            } else {
                // 兼容旧版 @@ 分隔符的数据
                let parts = raw.split('@@');
                return { name: parts[0], alias: parts.length > 1 ? parts[1] : '', descs: parts.length > 2 ? parts.slice(2) : [], raw: raw };
            }
        }
        function buildTagRaw(name, alias, descs = []) {
            let res = name;
            if (alias) res += '@@' + alias;
            if (descs && descs.length > 0) res += '@@@' + descs.join('@@@');
            return res;
        }

        // --- 全局自适应悬浮气泡控制器 (升级版：防挤压智能翻转) ---
        function calcTooltipPos(e, tt) {
            let offset = 15; // 浮窗与鼠标的间距
            let x = e.clientX + offset; // 默认在鼠标右侧
            let y = e.clientY - tt.offsetHeight - offset; // 默认在鼠标上方

            // 如果上方被挡住，翻转到鼠标下方
            if (y < 0) y = e.clientY + offset;

            // 如果右侧被挡住，翻转到鼠标左侧，而不是强行挤压
            if (x + tt.offsetWidth > window.innerWidth) {
                x = e.clientX - tt.offsetWidth - offset;
                // 极端情况：如果左侧也放不下，贴着屏幕左边缘
                if (x < 0) x = 10; 
            }
            return { x: Math.max(0, x), y: Math.max(0, y) };
        }

        function showTooltip(e, content) {
            if (!state.enableTooltip || !content) return;
            const tt = document.getElementById('float-tooltip');
            tt.innerHTML = content; tt.style.display = 'block';
            let pos = calcTooltipPos(e, tt);
            tt.style.left = pos.x + 'px'; tt.style.top = pos.y + 'px';
        }
        
        function hideTooltip() { document.getElementById('float-tooltip').style.display = 'none'; }
        
        function moveTooltip(e) {
            const tt = document.getElementById('float-tooltip');
            if (tt.style.display === 'block') {
                let pos = calcTooltipPos(e, tt);
                tt.style.left = pos.x + 'px'; tt.style.top = pos.y + 'px';
            }
        }

        // --- 高维属性编辑面板控制器 ---
        let deCallback = null;
        function openDetailEdit(x, y, defAlias, defDescs = [], cb, titleStr = '') {
            deCallback = cb;
            const de = document.getElementById('detail-edit');
            const titleEl = document.getElementById('de-title');
            if(titleEl) titleEl.innerText = titleStr || t('set_alias');
            document.getElementById('de-alias').value = defAlias || '';
            const descList = document.getElementById('de-desc-list');
            descList.innerHTML = '';
            if (defDescs && defDescs.length > 0) defDescs.forEach(d => addDeDescRow(d));
            else addDeDescRow(''); 
            de.style.display = 'flex'; setSafePosition(de, x, y);
            setTimeout(() => { document.getElementById('de-alias').focus(); document.getElementById('de-alias').select(); }, 50);
        }
        function addDeDescRow(val = '') {
            const list = document.getElementById('de-desc-list'); const row = document.createElement('div');
            row.style.display = 'flex'; row.style.gap = '6px'; row.style.alignItems = 'flex-start';
            row.innerHTML = `<textarea class="de-desc-input" style="flex: 1; height: 46px; resize: vertical; font-family: inherit; font-size: 12px; padding: 6px 8px; border: 1px solid var(--border-color); border-radius: var(--radius); background: var(--bg-input); color: var(--text-main); outline: none;">${_h(val)}</textarea><button class="tool-btn" style="width: 24px; height: 24px; flex-shrink: 0; color: var(--red); margin-top: 2px;" onclick="this.parentElement.remove()" v-html="delete"></button>`;
            list.appendChild(row); renderSVGs(row);
        }

        // [新增] 动态自适应高度防止越界
        function adjustDetailEditPosition() {
            const de = document.getElementById('detail-edit');
            if (de && de.style.display !== 'none') {
                let rect = de.getBoundingClientRect();
                // 如果浮窗底部超出了视窗底部边界，自动将其向上推
                if (rect.bottom > window.innerHeight - 5) {
                    let newTop = window.innerHeight - rect.height - 5;
                    de.style.top = Math.max(0, newTop) + 'px';
                }
            }
        }
        function closeDetailEdit() { document.getElementById('detail-edit').style.display = 'none'; deCallback = null; }
        function submitDetailEdit() {
            const alias = document.getElementById('de-alias').value.trim();
            const descInputs = document.querySelectorAll('.de-desc-input');
            const descs = Array.from(descInputs).map(i => i.value.trim()).filter(v => v);
            document.getElementById('detail-edit').style.display = 'none';
            if (deCallback) { deCallback({ alias, descs }); deCallback = null; }
        }

        function updateI18n() {
            document.querySelectorAll('[data-i18n]').forEach(el => el.innerText = t(el.getAttribute('data-i18n')));
            document.querySelectorAll('[data-i18n-title]').forEach(el => el.title = t(el.getAttribute('data-i18n-title')));
            document.querySelectorAll('[data-i18n-ph]').forEach(el => el.placeholder = t(el.getAttribute('data-i18n-ph')));
        }

        function bindSubmenuEvents() {
            document.querySelectorAll('.has-submenu').forEach(el => {
                el.onmouseenter = function() {
                    let sub = this.querySelector('.submenu');
                    if(!sub) return;
                    sub.style.left = '100%'; sub.style.right = 'auto';
                    sub.style.top = '-4px'; sub.style.bottom = 'auto';
                    sub.style.display = 'flex';
                    
                    let rect = sub.getBoundingClientRect();
                    if(rect.right > window.innerWidth) {
                        sub.style.left = 'auto'; sub.style.right = '100%';
                    }
                    if(rect.bottom > window.innerHeight) {
                        sub.style.top = 'auto'; sub.style.bottom = '0';
                    }
                };
                el.onmouseleave = function() {
                    let sub = this.querySelector('.submenu');
                    if(sub) sub.style.display = 'none';
                };
            });
        }
        
        let gStartX = 0, gStartY = 0;
        let lastClickTime = {}; 
        
        document.addEventListener('mousedown', e => { 
            gStartX = e.clientX; gStartY = e.clientY; 
            // 阻止中键(鼠标滚轮按下)时触发浏览器默认的滚动箭头行为
            if (e.button === 1) {
                e.preventDefault();
            }
        });
        function isDragAction(e) { return Math.abs(e.clientX - gStartX) > 4 || Math.abs(e.clientY - gStartY) > 4; }

        let state = { editMode: false, allExpanded: true, activeOnly: false, filterOnly: false, showAlias: false, enableTooltip: true, tagStates: {}, expandedGroups: {}, isPinned: false };
        let extEditModeUI = false;
        let clickOrder = []; 
        let ctxTarget = null; let wsCtxTarget = null; let dragItem = null; let batchTarget = null;
        let actionBtnTarget = null;

        const presetTypesMap = { '文本':'{:Text}', '图像':'{:Image}', '照片':'{:Photo}', '音频':'{:Audio}', '视频':'{:Video}', '媒体':'{:Media}', '字体':'{:Font}', '矢量图':'{:Vector}', '网页':'{:Web}', '文档':'{:Document}', '压缩包':'{:Archive}', '可执行':'{:Executable}', '文件夹':'size:' };
        const defaultTypeOrder = Object.keys(presetTypesMap);
        const fallbackLabels = [ {n:'Red', c:'#FC7268'}, {n:'Orange', c:'#F6AB46'}, {n:'Yellow', c:'#EFDC4A'}, {n:'Green', c:'#86C45E'}, {n:'Blue', c:'#63A8EB'}, {n:'Purple', c:'#C18BE2'}, {n:'Black', c:'#4D4D4D'}, {n:'White', c:'#FFFFFF'} ];
        const defaultRatingOrder = ['unrated','1','2','3','4','5'];

        function showToast(msg, type='info') {
            const container = document.getElementById('toast-container') || (function(){
                let c = document.createElement('div');
                c.id = 'toast-container';
                document.body.appendChild(c);
                return c;
            })();
            let t = document.createElement('div');
            t.className = `toast ${type}`;
            t.innerText = msg;
            container.appendChild(t);
            setTimeout(() => t.classList.add('show'), 10);
            setTimeout(() => {
                t.classList.remove('show');
                setTimeout(() => t.remove(), 300);
            }, 3000);
        }

        function sysLog(msg, level='INFO') {
            try { pywebview.api.log_message(msg, level); } catch(e) {}
        }

        function currentTree() {
            if (!allTreeData || Object.keys(allTreeData).length === 0) allTreeData = {"默认工作区": { "未分类": { "_bg_color": "", "_tags": ["?*", '""'] } }};
            if (!allTreeData[configData.currentWs]) {
                let keys = Object.keys(allTreeData);
                if (keys.length > 0) { configData.currentWs = keys[0]; } 
                else { configData.currentWs = "默认工作区"; allTreeData["默认工作区"] = { "未分类": { "_bg_color": "", "_tags": ["?*", '""'] } }; }
            }
            return allTreeData[configData.currentWs];
        }

        function currentCompState() { let wsData = currentTree(); if (!wsData._compState) wsData._compState = { types: {}, path: "", name: "", remarkMode: "", remark: "", label: "", ratings: {}, rules: [] }; return wsData._compState; }
        
        let _saveTimer = null;
        function debouncedSaveConfig() {
            clearTimeout(_saveTimer);
            _saveTimer = setTimeout(() => {
                try { pywebview.api.save_config(configData); } catch(e) {}
            }, 300);
        }
        
        function saveCompState() { try{pywebview.api.save_data(allTreeData);}catch(e){} updateSyntax(); }

        window.addEventListener('DOMContentLoaded', () => {
            if(!configData.theme) configData.theme = 'dark';
            if(!configData.lang) configData.lang = 'zh-CN';
            
            applyTheme(configData.theme, false);
            updateI18n();
            bindSubmenuEvents();
            
            const qe = document.getElementById('quick-edit');
            const qInput = document.getElementById('edit-input');
            
            document.addEventListener('mousedown', e => {
                const cm = document.getElementById('ctx-menu'); const wm = document.getElementById('ws-ctx-menu');
                const bm = document.getElementById('batch-add-menu'); const wl = document.getElementById('ws-list-menu');
                const actM = document.getElementById('action-btn-ctx-menu');
                const extM = document.getElementById('ext-batch-menu');
                const de = document.getElementById('detail-edit');
                if (extM && extM.style.display === 'flex' && !extM.contains(e.target)) extM.style.display = 'none';
                if (de && de.style.display === 'flex' && !de.contains(e.target)) closeDetailEdit();
                
                document.querySelectorAll('.global-dropdown').forEach(el => { 
                    if (el.style.display === 'flex' && el.id !== 'tag-search-modal' && !el.contains(e.target) && !e.target.closest('#btn-ws-dropdown') && !e.target.classList.contains('hist-toggle') && !e.target.parentElement.classList.contains('hist-toggle'))
                        el.style.display = 'none'; 
                });
                if (cm.style.display === 'flex' && !cm.contains(e.target)) cm.style.display = 'none';
                if (wm.style.display === 'flex' && !wm.contains(e.target)) wm.style.display = 'none';
                if (bm.style.display === 'flex' && !bm.contains(e.target)) bm.style.display = 'none';
                if (actM.style.display === 'flex' && !actM.contains(e.target)) actM.style.display = 'none';
                
                if (wl.style.display === 'flex' && !wl.contains(e.target) && !e.target.closest('#btn-ws-dropdown')
                    && !wm.contains(e.target) && !qe.contains(e.target)) {
                    wl.style.display = 'none';
                }
                
                if (qe.style.display === 'block' && !qe.contains(e.target)) {
                    qe.style.display = 'none'; 
                    let val = e.button === 0 ? qInput.value.trim() : null;
                    if(qCallback) { qCallback(val); qCallback = null; }
                }
            });

            qInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    if(qe.style.display !== 'none') {
                        qe.style.display = 'none';
                        if (qCallback) { qCallback(qInput.value.trim()); qCallback = null; }
                    }
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    if(qe.style.display !== 'none') {
                        qe.style.display = 'none';
                        if (qCallback) { qCallback(null); qCallback = null; }
                    }
                }
            });

            if(!configData.orderType) configData.orderType = [...defaultTypeOrder];
            if(!configData.orderRating) configData.orderRating = [...defaultRatingOrder];
            
            setTimeout(() => {
                initColorPicker(); initExpandedState(currentTree(), ""); renderWsBar(); renderActionBtnColors(); initCompModule(); render();
                initResizeObserver();
                renderSVGs();
                document.querySelector('.main-content').classList.add('ready');
                document.getElementById('app-loader').style.opacity = '0';
                setTimeout(() => document.getElementById('app-loader').style.display = 'none', 400);
                // [新增] 启动软件时恢复别名状态
                state.showAlias = !!configData['showAlias_' + configData.currentWs];
                document.getElementById('btn-swap-alias').classList.toggle('active-green', state.showAlias);
                
                // [新增] 启动软件时恢复悬浮提示状态
                let initTooltip = configData['enableTooltip_' + configData.currentWs];
                state.enableTooltip = initTooltip !== undefined ? !!initTooltip : true;
                document.getElementById('btn-toggle-tooltip').classList.toggle('active-green', state.enableTooltip);
                
                initColorPicker(); initExpandedState(currentTree(), ""); renderWsBar(); renderActionBtnColors(); initCompModule(); render();
            }, 50);
            
            window.addEventListener('resize', () => setTimeout(updateWsVisibility, 100));
        });

        function applyTheme(theme, isUserAction=false) {
            configData.theme = theme;
            if(theme === 'light') document.body.setAttribute('data-theme', 'light');
            else document.body.removeAttribute('data-theme');
            let sel = document.getElementById('cfg-theme');
            if(sel) sel.value = theme;
            
            let hex = theme === 'light' ? '#F4F5F7' : '#1A1B1E';
            // 【高维修复】：确保 pywebview API 加载完毕后再投递命令，避免初始化瞬间因为 undefined 而被静默吞噬
            if (window.pywebview && window.pywebview.api) {
                pywebview.api.change_titlebar_theme(hex, theme === 'dark');
            } else {
                window.addEventListener('pywebviewready', () => {
                    pywebview.api.change_titlebar_theme(hex, theme === 'dark');
                });
            }
        }

        function applyLang(lang) {
            configData.lang = lang;
            updateI18n();
            renderWsBar();
            initCompModule();
            renderActionBtnColors(); // [新增] 强制刷新按钮映射色
            render();                // 强制刷新树状图映射色
            let sel = document.getElementById('cfg-lang');
            if(sel) sel.value = lang;
        }

        function exportData() { 
            pywebview.api.export_data().then(res => {
                if(res.success) showToast(t("toast_export_data_ok"), "success");
            });
        }
        function exportConfig() { 
            pywebview.api.export_config().then(res => {
                if(res.success) showToast(t("toast_export_config_ok"), "success");
            });
        }
        
        function importData(e) {
            let file = e.target.files[0];
            if (!file) return;
            let reader = new FileReader();
            reader.onload = function(evt) {
                try {
                    allTreeData = JSON.parse(evt.target.result);
                    initExpandedState(currentTree(), ""); // [修复] 导入全量数据后立即重建状态字典
                    saveCompState(); render(); refreshCompUI();
                    sysLog(t("log_import_ok"), "INFO");
                    showToast(t("toast_import_data_ok"), "success");
                } catch(err) { sysLog(t("log_import_err"), "ERROR"); showToast(t("toast_import_error"), "error"); }
            };
            reader.readAsText(file);
            e.target.value = '';
        }
        function importConfig(e) {
            let file = e.target.files[0];
            if (!file) return;
            let reader = new FileReader();
            reader.onload = function(evt) {
                try {
                    configData = JSON.parse(evt.target.result);
                    pywebview.api.save_config(configData).then(() => { window.location.reload(); });
                    sysLog(t("log_import_cfg_ok"), "INFO");
                } catch(err) { sysLog(t("log_import_cfg_err"), "ERROR"); showToast(t("toast_import_error"), "error");}
            };
            reader.readAsText(file);
            e.target.value = '';
        }

        function renderActionBtnColors() {
            if(!configData.actionBtnColors) return;
            ['search','add','read','clear'].forEach(id => {
                let rawColor = configData.actionBtnColors[id];
                // [修改] 让顶部的功能大按钮也支持自适应映射
                let color = getMappedColor(rawColor, configData.theme);
                let btn = document.getElementById(`btn-${id}`);
                if(btn) {
                    if(color) {
                        btn.style.backgroundColor = color;
                        btn.style.borderColor = getLighterColor(color);
                    } else {
                        btn.style.backgroundColor = '';
                        btn.style.borderColor = '';
                    }
                }
            });
        }

        function onActionBtnCtx(e, id) {
            e.preventDefault(); e.stopPropagation();
            actionBtnTarget = id;
            const menu = document.getElementById('action-btn-ctx-menu');
            
            let ucsBtn = document.getElementById('ctx-batch-ucs');
            if (ucsBtn) {
                ucsBtn.style.display = (id === 'add') ? 'flex' : 'none';
            }

            let ucsNameBtn = document.getElementById('ctx-batch-ucs-name');
            if (ucsNameBtn) {
                ucsNameBtn.style.display = (id === 'add') ? 'flex' : 'none';
            }

            // --- 下面是新增的 AI 菜单显示控制逻辑 ---
            let aiSep = document.getElementById('ai-sep'); 
            if (aiSep) { aiSep.style.display = (id === 'add') ? 'block' : 'none'; }
            
            let ai1 = document.getElementById('ctx-ai-filename-dict'); 
            if (ai1) { ai1.style.display = (id === 'add') ? 'flex' : 'none'; }
            
            let ai2 = document.getElementById('ctx-ai-filename-auto'); 
            if (ai2) { ai2.style.display = (id === 'add') ? 'flex' : 'none'; }
            
            let ai3 = document.getElementById('ctx-ai-content-auto'); 
            if (ai3) { ai3.style.display = (id === 'add') ? 'flex' : 'none'; }

            let ai4 = document.getElementById('ctx-ai-filename-auto-en-zh'); 
            if (ai4) { ai4.style.display = (id === 'add') ? 'flex' : 'none'; }
            
            menu.style.display = 'flex';
            setSafePosition(menu, e.clientX, e.clientY);
        }

        function execActionBtnColor() {
            document.getElementById('action-btn-ctx-menu').style.display = 'none';
            if (!actionBtnTarget) return;
            let id = actionBtnTarget;
            let defCols = { search: '#1E293B', add: '#064E3B', read: '#451A03', clear: '#450A0A' };
            let cur = (configData.actionBtnColors && configData.actionBtnColors[id]) ? configData.actionBtnColors[id] : defCols[id];
            openColorModal(cur, hex => {
                if(!configData.actionBtnColors) configData.actionBtnColors = {};
                configData.actionBtnColors[id] = hex;
                debouncedSaveConfig();
                renderActionBtnColors();
                sysLog(t("log_color_upd"), "INFO");
            });
        }
        
        function execActionBtnColorReset() {
            document.getElementById('action-btn-ctx-menu').style.display = 'none';
            if (!actionBtnTarget || !configData.actionBtnColors) return;
            let id = actionBtnTarget;
            delete configData.actionBtnColors[id];
            debouncedSaveConfig();
            renderActionBtnColors();
            sysLog(t("log_func_color_rst"), "INFO");
        }

        function initResizeObserver() {
            const synWrap = document.getElementById('syntax-wrapper');
            const compMod = document.getElementById('comp-module');
            const detailEdit = document.getElementById('detail-edit'); // [新增]
            if (configData.syntax_w) synWrap.style.width = configData.syntax_w;
            if (configData.syntax_h) synWrap.style.height = configData.syntax_h;
            if (configData.comp_h) compMod.style.height = configData.comp_h;

            let resizeTimer;
            const ro = new ResizeObserver(entries => {
                let changed = false;
                for (let entry of entries) {
                    if (entry.target.id === 'syntax-wrapper') {
                        configData.syntax_w = entry.target.style.width;
                        configData.syntax_h = entry.target.style.height;
                        changed = true;
                    } else if (entry.target.id === 'comp-module') {
                        configData.comp_h = entry.target.style.height;
                        changed = true;
                    } else if (entry.target.id === 'detail-edit') {
                        adjustDetailEditPosition(); // [新增] 只要发生尺寸变化（加减行/手动拖拽），立即修正位置
                    }
                }
                if (changed) {
                    clearTimeout(resizeTimer);
                    resizeTimer = setTimeout(() => { debouncedSaveConfig() }, 500);
                }
            });
            ro.observe(synWrap);
            ro.observe(compMod);
            if (detailEdit) ro.observe(detailEdit); // [新增]
        }

        function initExpandedState(node, path) { 
            // [修复] 将展开状态挂载到当前工作区数据树中，实现随标签一起持久化保存
            if (!node._expandedGroups) node._expandedGroups = {};
            state.expandedGroups = node._expandedGroups;
            function _traverse(nd, p) {
                for (let k in nd) { 
                    if (!k.startsWith('_')) { 
                        let cur = p ? p + '/' + k : k; 
                        if (state.expandedGroups[cur] === undefined) state.expandedGroups[cur] = true; 
                        _traverse(nd[k], cur); 
                    } 
                }
            }
            _traverse(node, path);
        }
        
        function togglePin() { 
            pywebview.api.toggle_pin(state.isPinned).then(newState => { 
                state.isPinned = newState;
                const btn = document.getElementById('btn-pin');
                btn.innerHTML = state.isPinned ? SVGS.pinActive : SVGS.pin;
                btn.style.color = state.isPinned ? 'var(--primary)' : 'var(--text-muted)';
            }); 
        }

       function openManual() {
            pywebview.api.open_manual(configData.lang || 'zh-CN').then(res => {
                if(res && !res.success) showToast(t("toast_no_docs"), "error");
            });
        }

        function openDateHelp() {
            document.getElementById('date-help-modal').style.display = 'flex';
        }
        function closeDateHelp() {
            document.getElementById('date-help-modal').style.display = 'none';
        }

        function openSettings() { 
            document.getElementById('cfg-xy-path').value = configData.xyPath || ""; 
            document.getElementById('cfg-theme').value = configData.theme || 'dark';
            document.getElementById('cfg-lang').value = configData.lang || 'zh-CN';
            document.getElementById('settings-modal').style.display = 'flex'; 
            document.getElementById('cfg-ai-api').value = configData.ai_api || "http://localhost:11434/api/generate";
            document.getElementById('cfg-ai-model').value = configData.ai_model || "qwen2.5:0.5b";
        }
        function closeSettings() { document.getElementById('settings-modal').style.display = 'none'; }
        function saveSettings() { 
            configData.xyPath = document.getElementById('cfg-xy-path').value.trim(); 
            applyTheme(document.getElementById('cfg-theme').value, true);
            applyLang(document.getElementById('cfg-lang').value);
            debouncedSaveConfig(); 
            closeSettings(); 
            showToast(t("toast_save_ok"), "success");
            configData.ai_api = document.getElementById('cfg-ai-api').value.trim(); 
            configData.ai_model = document.getElementById('cfg-ai-model').value.trim();
        }

        function testXYplorer() {
            let pathInput = document.getElementById('cfg-xy-path').value.trim();
            let pathToTest = pathInput || configData.xyPath || "";
            
            let btn = document.querySelector('button[onclick="testXYplorer()"]');
            let textSpan = btn.querySelector('span[data-i18n="test_xy_path"]');
            let originalText = textSpan.innerText;
            
            textSpan.innerText = t('checking_update');
            btn.disabled = true;
            
            pywebview.api.test_xy_path(pathToTest).then(res => {
                textSpan.innerText = originalText;
                btn.disabled = false;
                
                if (res && res.success) {
                    showToast(t("toast_test_ok"), "success");
                } else {
                    showToast(t("toast_test_fail"), "error");
                }
            });
        }

        function toggleCompModule() {
            const m = document.getElementById('comp-module'); const b = document.getElementById('comp-collapse-btn');
            if (m.classList.contains('collapsed')) { m.classList.remove('collapsed'); b.innerHTML = SVGS.arrowDown; } 
            else { m.classList.add('collapsed'); b.innerHTML = SVGS.arrowRight; }
        }

        function initCompModule() {
            let cs = currentCompState(); let tHtml = '';
            defaultTypeOrder.forEach(k => { if(!configData.orderType.includes(k)) configData.orderType.push(k); });
            
            configData.orderType.forEach(tName => { 
                if(presetTypesMap[tName]) {
                    let tooltip = "";
                    if (tName === '照片') tooltip = t('tt_photo');
                    else if (tName === '媒体') tooltip = t('tt_media');
                    let titleAttr = tooltip ? `title="${tooltip}"` : "";
                    
                    tHtml += `<div class="comp-btn" draggable="true" ${titleAttr} ondragstart="onDragStartComp(event, 'Type', '${tName}')" ondragover="onDragOverComp(event)" ondragleave="onDragLeaveComp(event)" ondrop="onDropComp(event, 'Type', '${tName}')" data-type="${tName}" onmouseup="onCompTypeClick(event, '${tName}')" oncontextmenu="event.preventDefault()">${t(tName)}</div>`; 
                }
            });
            document.getElementById('comp-type-container').innerHTML = tHtml;

            let lHtml = `<div class="comp-lbl-btn" data-val="any" onmouseup="onCompLabelClick(event, 'any')">${t('has_label')}</div>`;
            lHtml += `<div class="comp-lbl-btn" data-val="none" onmouseup="onCompLabelClick(event, 'none')">${t('no_label')}</div>`;
            
            let activeLabelsList = (configData.xyLabels && configData.xyLabels.length > 0) ? configData.xyLabels : fallbackLabels;
            let activeLabelNames = activeLabelsList.map(x => x.n);
            
            if(!configData.orderLabel || configData.orderLabel.length === 0) configData.orderLabel = [...activeLabelNames];
            activeLabelNames.forEach(k => { if(!configData.orderLabel.includes(k)) configData.orderLabel.push(k); });
            
            configData.orderLabel.forEach(lN => {
                let lblData = activeLabelsList.find(x => x.n === lN);
                if(lblData) {
                    let color = lblData.c || '#fff';
                    lHtml += `<div class="comp-lbl-btn" data-val="${lN}" draggable="true" ondragstart="onDragStartComp(event, 'Label', '${lN}')" ondragover="onDragOverComp(event)" ondragleave="onDragLeaveComp(event)" ondrop="onDropComp(event, 'Label', '${lN}')" onmouseup="onCompLabelClick(event, '${lN}')"><div class="lbl-dot" style="background:${color};"></div>${lN}</div>`;
                }
            });
            document.getElementById('comp-label-container').innerHTML = lHtml;

            let rHtml = '';
            defaultRatingOrder.forEach(k => { if(!configData.orderRating.includes(k)) configData.orderRating.push(k); });
            configData.orderRating.forEach(r => { let disp = r === 'unrated' ? t('unrated') : '★'.repeat(parseInt(r)); rHtml += `<div class="comp-btn" draggable="true" ondragstart="onDragStartComp(event, 'Rating', '${r}')" ondragover="onDragOverComp(event)" ondragleave="onDragLeaveComp(event)" ondrop="onDropComp(event, 'Rating', '${r}')" onmouseup="onCompRatingClick(event, '${r}')">${disp}</div>`; });
            document.getElementById('comp-rating-container').innerHTML = rHtml;
            document.getElementById('comp-input-path').value = cs.path || ""; document.getElementById('comp-input-name').value = cs.name || ""; document.getElementById('comp-input-remark').value = cs.remark || "";
            refreshCompUI(); renderCustomExts(); renderRules(); updateSyntax();
            updateI18n();
        }

        function switchCompTab(tabId) { document.querySelectorAll('.comp-tab').forEach(el => el.classList.remove('active')); document.querySelectorAll('.comp-body').forEach(el => el.classList.remove('active')); event.target.classList.add('active'); document.getElementById(`comp-${tabId}`).classList.add('active'); const m = document.getElementById('comp-module'); if (m.classList.contains('collapsed')) toggleCompModule(); }
        
        function toggleExtEditMode() { extEditModeUI = !extEditModeUI; document.getElementById('comp-ext-container').classList.toggle('ext-edit-mode', extEditModeUI); renderCustomExts(); }

        function renderCustomExts() {
            let cs = currentCompState(); 
            if (!cs.customExts) cs.customExts = [];
            if (!cs.orderExt) cs.orderExt = [...cs.customExts];
            
            if (configData.customExts && configData.customExts.length > 0) {
                cs.customExts = [...configData.customExts];
                cs.orderExt = configData.orderExt ? [...configData.orderExt] : [...cs.customExts];
                delete configData.customExts;
                delete configData.orderExt;
                debouncedSaveConfig();
                saveCompState();
            }

            let html = ''; 
            cs.customExts.forEach(e => { if(!cs.orderExt.includes(e)) cs.orderExt.push(e); }); 
            cs.orderExt = cs.orderExt.filter(e => cs.customExts.includes(e));
            
            cs.orderExt.forEach((ext) => {
                let v = cs.types[ext] || 0; let cls = v === 1 ? " s1" : (v === 2 ? " s2" : "");
                html += `
                <div class="comp-btn${cls}" draggable="true" ondragstart="onDragStartComp(event, 'Ext', '${ext}')" ondragover="onDragOverComp(event)" ondragleave="onDragLeaveComp(event)" ondrop="onDropComp(event, 'Ext', '${ext}')" onmouseup="onCustomExtClick(event, '${ext}')" oncontextmenu="event.preventDefault()">
                    ${ext}<div class="custom-ext-del" onclick="delCustomExt(event, '${ext}')" v-html="delete"></div>
                </div>`;
            });
            html += `<div class="add-tag-btn" onclick="addCustomExtPrompt(event)" oncontextmenu="triggerExtBatchMenu(event)" v-html="add"></div>`;
            document.getElementById('comp-ext-container').innerHTML = html; renderSVGs(document.getElementById('comp-ext-container'));
        }

        function addCustomExtPrompt(e) { 
            openQuickEdit(e.clientX, e.clientY, "", (val) => { 
                val = val ? val.trim() : ""; 
                let cs = currentCompState();
                if (!cs.customExts) cs.customExts = [];
                if (!cs.orderExt) cs.orderExt = [];
                if (val && !cs.customExts.includes(val)) { 
                    cs.customExts.push(val); 
                    cs.orderExt.push(val); 
                    saveCompState(); 
                    renderCustomExts(); 
                    showToast(t("toast_ext_added"), "success"); 
                } 
            }); 
        }

        // [修复] 补充丢失的类型按钮点击事件，使其能够正常激活"与"(左键)和"非"(右键)
        function onCompTypeClick(e, type) { 
            if (isDragAction(e)) return; 
            let now = Date.now(); if (now - (lastClickTime[`type_${type}`] || 0) < 150) return; lastClickTime[`type_${type}`] = now;
            
            let cs = currentCompState();
            let cur = cs.types[type] || 0; 
            
            if (e.button === 0) {
                let nextState = cur === 1 ? 0 : 1;
                // 如果左键包含，自动清除所有冲突的排除项
                if (nextState === 1) {
                    for (let k in cs.types) {
                        if (cs.types[k] === 2) delete cs.types[k];
                    }
                }
                cs.types[type] = nextState;
            } else if (e.button === 2) {
                let nextState = cur === 2 ? 0 : 2;
                // 如果右键排除，自动清除所有冲突的包含项
                if (nextState === 2) {
                    for (let k in cs.types) {
                        if (presetTypesMap[k] && k !== '文件夹') {
                            delete cs.types[k];
                        } else if (cs.types[k] === 1) {
                            delete cs.types[k];
                        }
                    }
                }
                cs.types[type] = nextState;
            }
            refreshCompUI(); saveCompState(); 
        }
        
        function onCustomExtClick(e, ext) { 
            if (isDragAction(e)) return; 
            if (e.target.closest && e.target.closest('.custom-ext-del')) return;
            
            let cs = currentCompState();
            if (!cs.customExts) cs.customExts = [];
            if (!cs.orderExt) cs.orderExt = [];

            if (e.altKey && e.button === 1) {
                e.preventDefault(); e.stopPropagation();
                openQuickEdit(e.clientX, e.clientY, ext, (val) => { 
                    if (val && val !== ext) { 
                        let idx = cs.customExts.indexOf(ext); if (idx > -1) cs.customExts[idx] = val; 
                        let oIdx = cs.orderExt.indexOf(ext); if (oIdx > -1) cs.orderExt[oIdx] = val; 
                        if(cs.types[ext] !== undefined) { cs.types[val] = cs.types[ext]; delete cs.types[ext]; } 
                        saveCompState(); renderCustomExts(); 
                    } 
                });
                return;
            }

            let now = Date.now(); if (now - (lastClickTime[`ext_${ext}`] || 0) < 150) return; lastClickTime[`ext_${ext}`] = now;

            if (extEditModeUI && e.button === 0) { 
                openQuickEdit(e.clientX, e.clientY, ext, (val) => { 
                    if (val && val !== ext) { 
                        let idx = cs.customExts.indexOf(ext); if (idx > -1) cs.customExts[idx] = val; 
                        let oIdx = cs.orderExt.indexOf(ext); if (oIdx > -1) cs.orderExt[oIdx] = val; 
                        if(cs.types[ext] !== undefined) { cs.types[val] = cs.types[ext]; delete cs.types[ext]; } 
                        saveCompState(); renderCustomExts(); 
                    } 
                }); 
                return; 
            } 
            
            let cur = cs.types[ext] || 0; 
            
            if (e.button === 0) {
                let nextState = cur === 1 ? 0 : 1;
                if (nextState === 1) {
                    for (let k in cs.types) {
                        if (cs.types[k] === 2) delete cs.types[k];
                    }
                }
                cs.types[ext] = nextState;
            } else if (e.button === 2) {
                let nextState = cur === 2 ? 0 : 2;
                if (nextState === 2) {
                    for (let k in cs.types) {
                        if (presetTypesMap[k] && k !== '文件夹') {
                            delete cs.types[k];
                        } else if (cs.types[k] === 1) {
                            delete cs.types[k];
                        }
                    }
                }
                cs.types[ext] = nextState;
            }
            renderCustomExts(); refreshCompUI(); saveCompState(); 
        }
        
        function delCustomExt(e, ext) { 
            e.stopPropagation(); 
            let cs = currentCompState();
            if (!cs.customExts) cs.customExts = [];
            if (!cs.orderExt) cs.orderExt = [];
            cs.customExts = cs.customExts.filter(x => x !== ext); 
            cs.orderExt = cs.orderExt.filter(x => x !== ext); 
            delete cs.types[ext]; 
            saveCompState(); renderCustomExts(); 
        }

        function onCompLabelClick(e, lbl) { 
            if(isDragAction(e)) return; 
            let now = Date.now(); if (now - (lastClickTime[`lbl_${lbl}`] || 0) < 150) return; lastClickTime[`lbl_${lbl}`] = now;
            let cs = currentCompState(); cs.label = cs.label === lbl ? "" : lbl; 
            refreshCompUI(); saveCompState(); 
        }

        function updateXYLabels() {
            pywebview.api.update_xy_labels(configData.xyPath).then(res => {
                if (res.success) {
                    configData.xyLabels = res.labels;
                    configData.orderLabel = res.labels.map(x => x.n); 
                    debouncedSaveConfig();
                    initCompModule(); 
                    sysLog(t("log_sync_ok"), "INFO");
                    showToast(t("toast_sync_ok"), "success");
                } else {
                    sysLog(t("log_sync_fail") + res.msg, "ERROR");
                    showToast(t("toast_sync_fail"), "error");
                }
            });
        }
        
        function onCompRatingClick(e, rate) { 
            if(isDragAction(e)) return; 
            let now = Date.now(); if (now - (lastClickTime[`rate_${rate}`] || 0) < 150) return; lastClickTime[`rate_${rate}`] = now;
            let cs = currentCompState(); cs.ratings[rate] = !cs.ratings[rate]; 
            refreshCompUI(); saveCompState(); 
        }
        
        function updateCompState(key, val) { currentCompState()[key] = val; saveCompState(); }
        function setCompPath(p) { document.getElementById('comp-input-path').value = p; updateCompState('path', p); }
        
        function confirmInput(key) {
            let val = document.getElementById(`comp-input-${key}`).value.trim();
            if (val || key === 'path') {
                updateCompState(key, val);
                pushHistory(key, val); 
                refreshCompUI();
                updateSyntax();
                showToast(t("toast_hist_saved"), "success");
            }
        }
        
        function applyRemarkPreset(mode) { 
            let cs = currentCompState();
            if (cs.remarkMode === mode) { cs.remarkMode = ""; }
            else { cs.remarkMode = mode; }
            refreshCompUI(); saveCompState();
        }

        function addRule(type) { 
            let cs = currentCompState(); 
            if (type === 'size') { 
                let op = document.getElementById('size-op').value; 
                let val = document.getElementById('size-val').value; 
                let unit = document.getElementById('size-unit').value; 
                if (!val) return; 
                let str = `size: ${op} ${val}${unit}`; 
                if (!cs.rules.includes(str)) cs.rules.push(str); 
            } else if (type === 'date') { 
                let dt = document.getElementById('date-type').value; 
                let op = document.getElementById('date-op').value; 
                let val = document.getElementById('date-val').value.trim(); 
                if (!val) return; 
                
                if (/[a-zA-Z]/.test(val)) {
                    op = ""; 
                    document.getElementById('date-op').value = "";
                }
                
                let str = op ? `${dt}: ${op} ${val}` : `${dt}: ${val}`;
                if (!cs.rules.includes(str)) cs.rules.push(str);
            } 
            renderRules(); 
            saveCompState(); 
        }
        function delRule(idx) { currentCompState().rules.splice(idx, 1); renderRules(); saveCompState(); }
        function renderRules() { 
            let html = ''; 
            let cs = currentCompState();
            
            cs.rules = cs.rules.map(r => {
                let match = r.match(/^(dateC|dateM|dateA|ageC|ageM|ageA):\\s*(>=|<=|==|>|<)?\\s*(.*)$/);
                if (match && /[a-zA-Z]/.test(match[3])) {
                    return `${match[1]}: ${match[3]}`; 
                }
                return r;
            });

            cs.rules.forEach((r, i) => { 
                html += `<div class="builder-tag" onclick="delRule(${i})" oncontextmenu="loadRuleToInput(event, ${i})" title="右键将此规则重新填入输入框">${r} <span style="margin-left:4px;" v-html="delete"></span></div>`; 
            }); 
            document.getElementById('rules-container').innerHTML = html; 
            renderSVGs(document.getElementById('rules-container')); 
        }

        function loadRuleToInput(e, idx) {
            e.preventDefault(); e.stopPropagation();
            let rule = currentCompState().rules[idx];
            if (!rule) return;
            
            if (rule.startsWith('size:')) {
                let match = rule.match(/^size:\\s*(>=|<=|==|>|<)?\\s*([0-9.]+)(MB|KB|GB)$/);
                if (match) {
                    if (match[1]) document.getElementById('size-op').value = match[1];
                    document.getElementById('size-val').value = match[2];
                    if (match[3]) document.getElementById('size-unit').value = match[3];
                }
            } else {
                let match = rule.match(/^(dateC|dateM|dateA|ageC|ageM|ageA):\\s*(>=|<=|==|>|<)?\\s*(.*)$/);
                if (match) {
                    document.getElementById('date-type').value = match[1];
                    document.getElementById('date-op').value = match[2] || "";
                    document.getElementById('date-val').value = match[3];
                }
            }
            showToast("已将规则回填至输入框", "info");
        }
        
        function clearCompFilters() { 
            let cs = currentCompState(); 
            cs.types = {}; cs.name = ""; cs.remarkMode = ""; cs.remark = ""; cs.label = ""; cs.ratings = {}; cs.rules = []; 
            document.getElementById('comp-input-name').value = ""; document.getElementById('comp-input-remark').value = ""; document.getElementById('size-val').value = ""; document.getElementById('date-val').value = ""; 
            refreshCompUI(); renderCustomExts(); renderRules(); saveCompState(); 
        }

        function refreshCompUI() {
            let cs = currentCompState();
            document.querySelectorAll('#comp-type-container .comp-btn').forEach(el => { let v = cs.types[el.dataset.type] || 0; el.className = "comp-btn" + (v === 1 ? " s1" : (v === 2 ? " s2" : "")); });
            document.querySelectorAll('#comp-ext-container .comp-btn').forEach(el => { let extName = el.childNodes[0].nodeValue.trim(); let v = cs.types[extName] || 0; el.className = "comp-btn" + (v === 1 ? " s1" : (v === 2 ? " s2" : "")); });
            document.querySelectorAll('#comp-label-container .comp-lbl-btn').forEach(el => { let val = el.dataset.val; el.className = "comp-lbl-btn" + (cs.label === val ? " active" : ""); });
            document.querySelectorAll('#comp-rating-container .comp-btn').forEach(el => { let text = el.innerText.trim(); let key = text === t('unrated') ? "unrated" : text.length.toString(); el.className = "comp-btn" + (cs.ratings[key] ? " s1" : ""); });
            
            document.getElementById('btn-remark-any').className = "comp-btn" + (cs.remarkMode === 'any' ? " s1" : "");
            document.getElementById('btn-remark-none').className = "comp-btn" + (cs.remarkMode === 'none' ? " s1" : "");
        }

        function toggleHistory(e, stateKey, forceShow=false) { 
            if(e) e.stopPropagation();
            let el = document.getElementById('global-hist-dropdown'); 
            let arrKey = `hist_${stateKey}_${configData.currentWs}`; 
            
            if (!forceShow && el.style.display === 'flex' && el.dataset.key === stateKey) { 
                el.style.display = 'none'; 
                return; 
            } 
            
            let arr = configData[arrKey] || []; 
            let html = ''; 
            arr.forEach(val => {
                let safeVal = _e(val);
                html += `<div class="hist-item">
                            <span class="hist-item-text" onclick="applyHistory('comp-input-${stateKey}', '${stateKey}', '${safeVal}')">${_h(val)}</span>
                            <span class="hist-del" onclick="delHistory(event, '${stateKey}', '${safeVal}')" title="${t('delete')}">×</span>
                         </div>`;
            }); 
            if (html === '') html = `<div style="padding:6px; color:var(--text-muted); font-size:11px;">${t('no_record')}</div>`; 
            el.innerHTML = html; 
            el.dataset.key = stateKey;
            
            let inputEl = document.getElementById('comp-input-' + stateKey);
            let wrapperRect = inputEl.parentElement.getBoundingClientRect();
            
            el.style.left = wrapperRect.left + 'px';
            el.style.top = (wrapperRect.bottom + 2) + 'px';
            el.style.width = wrapperRect.width + 'px';
            
            el.style.display = 'flex'; 
        }
        
        function delHistory(e, stateKey, val) {
            e.stopPropagation();
            let arrKey = `hist_${stateKey}_${configData.currentWs}`;
            if (configData[arrKey]) {
                configData[arrKey] = configData[arrKey].filter(x => x !== val);
                debouncedSaveConfig();
                toggleHistory(null, stateKey, true);
                sysLog(t("log_hist_del"), "INFO");
            }
        }
        
        function applyHistory(inputId, stateKey, val) { document.getElementById(inputId).value = val; updateCompState(stateKey, val); document.getElementById('global-hist-dropdown').style.display = 'none'; }
        
        function pushHistory(stateKey, val) { 
            if (!val) return; 
            let fullKey = `hist_${stateKey}_${configData.currentWs}`;
            let arr = configData[fullKey] || []; 
            arr = arr.filter(x => x !== val); 
            arr.unshift(val); 
            if (arr.length > 18) arr.pop(); 
            configData[fullKey] = arr; 
            debouncedSaveConfig();
        }

        function onDragStartComp(e, cat, name) { dragItem = { type: 'comp_'+cat, name: name }; e.dataTransfer.setData('text', 'dummy'); e.stopPropagation(); }
        function onDragOverComp(e) { e.preventDefault(); e.stopPropagation(); let el = e.currentTarget; let r = el.getBoundingClientRect(); if (e.clientX - r.left < r.width / 2) { el.classList.add('drag-left'); el.classList.remove('drag-right'); } else { el.classList.add('drag-right'); el.classList.remove('drag-left'); } }
        function onDragLeaveComp(e) { e.currentTarget.classList.remove('drag-left', 'drag-right'); }
        
        function onDropComp(e, cat, targetName) { 
            e.preventDefault(); e.stopPropagation(); 
            e.currentTarget.classList.remove('drag-left', 'drag-right'); 
            if(!dragItem || dragItem.type !== 'comp_'+cat || dragItem.name === targetName) return; 
            
            let arr;
            if (cat === 'Ext') {
                let cs = currentCompState();
                if (!cs.orderExt) cs.orderExt = [];
                arr = cs.orderExt;
            } else {
                let arrKey = 'order' + cat; arr = configData[arrKey]; 
            }
            if(!arr) return; 
            
            let sIdx = arr.indexOf(dragItem.name); 
            if(sIdx < 0) return; 
            arr.splice(sIdx, 1); 
            
            let tIdx = arr.indexOf(targetName); 
            if(tIdx < 0) tIdx = arr.length;
            
            let r = e.currentTarget.getBoundingClientRect(); 
            if(e.clientX - r.left >= r.width / 2) tIdx++; 
            arr.splice(tIdx, 0, dragItem.name); 
            
            if (cat === 'Ext') { saveCompState(); renderCustomExts(); }
            else { debouncedSaveConfig(); initCompModule(); }
        }

        // ========================== 工作区栏功能 ==========================
        function getWsList() {
            if (!configData.orderWs) configData.orderWs = Object.keys(allTreeData);
            let currentKeys = Object.keys(allTreeData);
            configData.orderWs = configData.orderWs.filter(k => currentKeys.includes(k));
            currentKeys.forEach(k => { if (!configData.orderWs.includes(k)) configData.orderWs.push(k); });
            return configData.orderWs;
        }

        function renderWsBar() {
            const container = document.getElementById('ws-tabs-scroll'); 
            let html = '';
            getWsList().forEach(ws => { 
                const isActive = ws === configData.currentWs; 
                // [修改] 让工作区选项卡背景色也支持自适应映射
                let rawBgColor = (configData.wsColors && configData.wsColors[ws]) ? configData.wsColors[ws] : '';
                let bgColor = getMappedColor(rawBgColor, configData.theme);
                let styleStr = isActive ? `background: var(--primary); color: #fff; border-color:var(--primary);` : (bgColor ? `background: ${bgColor};` : '');
                let sws = _e(ws);
                let hws = _h(sysT(ws));
                html += `<div class="ws-tab ${isActive ? 'active' : ''}" id="ws-tab-${_h(ws)}" style="${styleStr}" draggable="true" ondragstart="onDragStartWs(event, '${sws}')" ondragover="onDragOverWs(event)" ondragleave="onDragLeaveWs(event)" ondrop="onDropWs(event, '${sws}')" onclick="switchWs('${sws}')" oncontextmenu="onWsCtx(event, '${sws}')">${hws}</div>`; 
            });
            container.innerHTML = html; renderSVGs(container);
            setTimeout(updateWsVisibility, 50); 
        }
        
        function updateWsVisibility() {
            const container = document.getElementById('ws-tabs-scroll');
            const dynamicArea = document.getElementById('ws-dynamic-area');
            const activeTab = document.getElementById(`ws-tab-${_h(sysT(configData.currentWs))}`);
            
            if (!activeTab) return;
            const containerRect = container.getBoundingClientRect();
            const tabRect = activeTab.getBoundingClientRect();
            const isVisible = (tabRect.left >= containerRect.left && tabRect.right <= containerRect.right);
            
            if (!isVisible) {
                let sws = _e(configData.currentWs);
                dynamicArea.innerHTML = `<div class="ws-tab active" onclick="switchWs('${sws}')" oncontextmenu="onWsCtx(event, '${sws}')">${_h(t(configData.currentWs))}</div>`;
                dynamicArea.style.display = 'flex';
            } else {
                dynamicArea.style.display = 'none';
            }
        }
        
        function toggleWsDropdown(e) {
            const menu = document.getElementById('ws-list-menu');
            if(menu.style.display === 'flex') {
                menu.style.display = 'none';
                return;
            }
            e.stopPropagation();
            let html = '';
            getWsList().forEach(ws => { 
                const isActive = ws === configData.currentWs;
                let sws = _e(ws);
                
                // [修复] 获取工作区颜色并进行主题自适应映射，让下拉列表也能显示背景色
                let rawBgColor = (configData.wsColors && configData.wsColors[ws]) ? configData.wsColors[ws] : '';
                let bgColor = getMappedColor(rawBgColor, configData.theme);
                let styleStr = (!isActive && bgColor) ? `style="background: ${bgColor};"` : '';
                
                html += `<div class="menu-item ws-list-item ${isActive ? 'active' : ''}" ${styleStr}
                              onclick="switchWs('${sws}'); document.getElementById('ws-list-menu').style.display='none';"
                              oncontextmenu="onWsCtx(event, '${sws}'); ">
                            <span class="menu-text">${_h(sysT(ws))}</span>
                         </div>`;
            });
            menu.innerHTML = html;
            menu.style.display = 'flex';
            setSafePosition(menu, e.clientX - 100, e.clientY + 15);
        }

        function switchWs(ws) { 
            if (configData.currentWs === ws) return; 
            configData.currentWs = ws; 
            
            // [新增] 切换工作区时读取它的专属别名状态
            state.showAlias = !!configData['showAlias_' + ws];
            document.getElementById('btn-swap-alias').classList.toggle('active-green', state.showAlias);
            
            // [新增] 切换工作区时读取它的专属悬浮提示状态，默认开启
            let savedTooltip = configData['enableTooltip_' + ws];
            state.enableTooltip = savedTooltip !== undefined ? !!savedTooltip : true;
            document.getElementById('btn-toggle-tooltip').classList.toggle('active-green', state.enableTooltip);
            
            debouncedSaveConfig(); state.tagStates = {}; clickOrder = []; state.expandedGroups = {}; initExpandedState(currentTree(), ""); renderWsBar(); initCompModule(); render(); 
        }
        
        function addWs(e) { 
            openQuickEdit(e.clientX, e.clientY, t("new_ws"), val => { 
                if (val && !allTreeData[val]) { 
                    allTreeData[val] = { "未分类": { "_bg_color": "", "_tags": ["?*", '""'] }, "_compState": { types: {}, path: "", name: "", remarkMode: "", remark: "", label: "", ratings: {}, rules: [] } }; 
                    let wsList = getWsList();
                    if (!wsList.includes(val)) { wsList.push(val); configData.orderWs = wsList; debouncedSaveConfig(); }
                    saveCompState(); render(); refreshCompUI(); 
                    switchWs(val); 
                    setTimeout(()=> { document.getElementById('ws-tabs-scroll').scrollLeft = 9999; }, 100); 
                } 
            }); 
        }
        
        function setSafePosition(el, x, y) {
            let safeX = Math.min(x, window.innerWidth - el.offsetWidth - 5);
            let safeY = Math.min(y, window.innerHeight - el.offsetHeight - 5);
            el.style.left = Math.max(0, safeX) + 'px';
            el.style.top = Math.max(0, safeY) + 'px';
        }

        function onWsCtx(e, ws) { e.preventDefault(); e.stopPropagation(); wsCtxTarget = ws; const wm = document.getElementById('ws-ctx-menu'); wm.style.display = 'flex'; setSafePosition(wm, e.clientX, e.clientY); }
        
        function wsCtxAction(action) { 
            document.getElementById('ws-ctx-menu').style.display = 'none'; 
            let ws = wsCtxTarget; 
            if (action === 'color') {
                let cur = (configData.wsColors && configData.wsColors[ws]) ? configData.wsColors[ws] : '#333333';
                openColorModal(cur, hex => {
                    if(!configData.wsColors) configData.wsColors = {};
                    configData.wsColors[ws] = hex;
                    debouncedSaveConfig();
                    renderWsBar();
                    sysLog(t("log_ws_color_upd"), "INFO");
                });
            } else if (action === 'color-reset') {
                if(configData.wsColors) delete configData.wsColors[ws];
                debouncedSaveConfig();
                renderWsBar();
                sysLog(t("log_ws_color_rst"), "INFO");
            } else if (action === 'rename') { 
                openQuickEdit(gStartX, gStartY, ws, val => {
                    if (val && val !== ws && !allTreeData[val]) { 
                        let keys = getWsList();
                        let idx = keys.indexOf(ws);
                        if (idx !== -1) keys[idx] = val;
                        configData.orderWs = keys;
                        
                        let newAll = {}; 
                        for (let k of keys) { 
                            if (k === val) newAll[val] = allTreeData[ws]; 
                            else newAll[k] = allTreeData[k]; 
                        } 
                        allTreeData = newAll; 

                        ['path', 'name', 'remark'].forEach(k => {
                            if (configData[`hist_${k}_${ws}`]) {
                                configData[`hist_${k}_${val}`] = configData[`hist_${k}_${ws}`];
                                delete configData[`hist_${k}_${ws}`];
                            }
                        });
                        
                        if (configData.currentWs === ws) { configData.currentWs = val; } 
                        debouncedSaveConfig();
                        saveCompState(); renderWsBar(); render(); refreshCompUI(); // [修复] 强制刷新顶部工作区栏
                    } 
                }); 
            } else if (action === 'duplicate') { 
                let newWs = ws + " Copy"; let count = 1; 
                while(allTreeData[newWs]) { count++; newWs = `${ws} Copy ${count}`; } 
                
                // 【高维修复】：先获取旧的 keys 列表并插入新名字
                // 彻底避免 getWsList() 的内部校验把新工作区提前当成野孩子塞到末尾
                let keys = getWsList();
                let idx = keys.indexOf(ws);
                if (idx !== -1) keys.splice(idx + 1, 0, newWs);
                else keys.push(newWs);
                configData.orderWs = keys;

                // 然后再把数据安全地复制进字典
                allTreeData[newWs] = JSON.parse(JSON.stringify(allTreeData[ws])); 

                ['path', 'name', 'remark'].forEach(k => {
                    if (configData[`hist_${k}_${ws}`]) {
                        configData[`hist_${k}_${newWs}`] = [...configData[`hist_${k}_${ws}`]];
                    }
                });

                debouncedSaveConfig();
                
                let newAll = {}; for (let k of keys) newAll[k] = allTreeData[k]; allTreeData = newAll;
                saveCompState(); renderWsBar(); render(); refreshCompUI(); // [修复] 强制刷新顶部工作区栏
            } else if (action === 'delete') {
            if (Object.keys(allTreeData).length <= 1) { 
                    showToast(t("toast_ws_keep_one"), "error"); 
                    sysLog(t("log_ws_keep_one"), "ERROR"); 
                    return; 
                } 
                showConfirmModal(t('confirm_del_ws').replace('{ws}', ws), () => {
                    let keys = getWsList();
                    let wsIndex = keys.indexOf(ws);
                    
                    let fallbackWs = "";
                    if (wsIndex > 0) {
                        fallbackWs = keys[wsIndex - 1]; 
                    } else {
                        fallbackWs = keys[1]; 
                    }

                    let wasCurrent = (configData.currentWs === ws); 

                    delete allTreeData[ws]; 

                    ['path', 'name', 'remark'].forEach(k => {
                        delete configData[`hist_${k}_${ws}`];
                    });

                    if (wasCurrent) { 
                        configData.currentWs = fallbackWs; 
                    } 
                    
                    configData.orderWs = keys.filter(k => k !== ws);
                    debouncedSaveConfig();
                    
                    if (wasCurrent) { 
                        state.tagStates = {}; 
                        clickOrder = []; 
                        initExpandedState(currentTree(), ""); 
                    } 
                    
                    saveCompState(); 
                    
                    renderWsBar();
                    render(); 
                    refreshCompUI(); 
                    
                    sysLog(t("log_ws_del"), "INFO");
                    showToast(t("toast_ws_deleted"), "success");
                });
            }
        }

        function onDragStartWs(e, ws) { dragItem = { type: 'ws', name: ws }; e.dataTransfer.setData('text', 'dummy'); }
        function onDragOverWs(e) { 
            e.preventDefault(); e.stopPropagation(); 
            let el = e.currentTarget; 
            let r = el.getBoundingClientRect(); 
            if (e.clientX - r.left < r.width / 2) { el.classList.add('drag-left'); el.classList.remove('drag-right'); } 
            else { el.classList.add('drag-right'); el.classList.remove('drag-left'); } 
        }
        function onDragLeaveWs(e) { e.currentTarget.classList.remove('drag-left', 'drag-right'); }
        
        function onDropWs(e, targetWs) { 
            e.preventDefault(); 
            e.currentTarget.classList.remove('drag-left', 'drag-right'); 
            if (!dragItem || dragItem.type !== 'ws' || dragItem.name === targetWs) return; 
            
            let keys = getWsList();
            let sIdx = keys.indexOf(dragItem.name); 
            if (sIdx > -1) keys.splice(sIdx, 1); 
            
            let tIdx = keys.indexOf(targetWs); 
            if (tIdx < 0) tIdx = keys.length;
            
            let rect = e.currentTarget.getBoundingClientRect(); 
            if (e.clientX - rect.left >= rect.width / 2) tIdx++; 
            keys.splice(tIdx, 0, dragItem.name); 
            
            configData.orderWs = keys;
            debouncedSaveConfig();
            
            let newAll = {}; for (let k of keys) newAll[k] = allTreeData[k]; allTreeData = newAll; 
            
            // 【高维修复】：补上缺失的视觉同步咒语，拖拽完成后强制重新渲染顶部工作区栏！
            saveCompState(); 
            renderWsBar(); 
            render(); 
            refreshCompUI(); 
        }

        function saveDataAndRenderAll() {
            saveCompState(); 
            render(); 
            refreshCompUI();
        }

        function toggleTool(toolName) {
            if (toolName === 'editMode') {
                state.editMode = !state.editMode;
                document.getElementById('btn-edit').classList.toggle('active-orange', state.editMode);
                render();
                return;
            }
            if (toolName === 'showAlias') {
                state.showAlias = !state.showAlias;
                document.getElementById('btn-swap-alias').classList.toggle('active-green', state.showAlias);
                configData['showAlias_' + configData.currentWs] = state.showAlias; // [新增] 保存当前工作区的别名状态
                debouncedSaveConfig(); // [新增] 写入本地
                render();
                return;
            }
            if (toolName === 'enableTooltip') {
                state.enableTooltip = !state.enableTooltip;
                document.getElementById('btn-toggle-tooltip').classList.toggle('active-green', state.enableTooltip);
                configData['enableTooltip_' + configData.currentWs] = state.enableTooltip;
                debouncedSaveConfig();
                return;
            }
            if (toolName !== 'activeOnly') state.activeOnly = false;
            if (toolName !== 'filterOnly') state.filterOnly = false; 
            state[toolName] = !state[toolName];
            document.getElementById('btn-active').classList.toggle('active-green', state.activeOnly); 
            document.getElementById('btn-filter').classList.toggle('active-green', state.filterOnly); 
            
            if (state.activeOnly) { 
                for (let k in state.expandedGroups) state.expandedGroups[k] = false; 
                forceExpandActive(currentTree(), ""); 
            } else if (!state.filterOnly && !state.activeOnly) { 
                state.allExpanded = false; 
                toggleAll(); 
                return; 
            } 
            render();
        }

        function forceExpandActive(node, path) { for (let k in node) { if (!k.startsWith('_')) { let p = path ? path + '/' + k : k; if (checkActiveBubble(node[k], p)) { state.expandedGroups[p] = true; forceExpandActive(node[k], p); } } } }
        function toggleAll(e) { 
            let targetState = !state.allExpanded; 

            if (e && e.altKey) {
                if (e.button === 0) { 
                    targetState = true;
                } else if (e.button === 2) { 
                    targetState = false;
                } else {
                    return; 
                }
            } else if (e && e.button === 2) {
                return; 
            }

            state.allExpanded = targetState; 
            state.activeOnly = false; 
            state.filterOnly = false; 
            document.getElementById('btn-active').classList.remove('active-green'); 
            document.getElementById('btn-filter').classList.remove('active-green'); 
            document.getElementById('btn-toggle').innerHTML = state.allExpanded ? SVGS.expand : SVGS.minimize; 
            for (let k in state.expandedGroups) state.expandedGroups[k] = state.allExpanded; 
            saveCompState(); // [修复] 保存全局折叠状态
            render(); 
        }
        
        function clearAll() { state.tagStates = {}; clickOrder = []; render(); }
        function clearAllActiveTags() { state.tagStates = {}; clickOrder = []; render(); }

        function render() {
            const root = document.getElementById('tree');
            if (state.editMode) root.classList.add('edit-mode'); else root.classList.remove('edit-mode');
            let html = ''; let tNode = currentTree();
            if (tNode["未分类"]) { let uncatHtml = buildGroup("未分类", tNode["未分类"], "未分类", 0); if (uncatHtml) html += uncatHtml; }
            for (let k in tNode) { if (!k.startsWith('_') && k !== "未分类") { let gHtml = buildGroup(k, tNode[k], k, 0); if (gHtml) html += gHtml; } }
            root.innerHTML = html; 
            renderSVGs(root); updateSyntax();
        }

        function buildGroup(name, node, path, level) {
            let sp = _e(path);
            let sn = _e(name);
            let dn = (state.showAlias && node._alias) ? _h(node._alias) : _h(sysT(name)); 

            let isExpanded = state.expandedGroups[path]; let hasActive = checkActiveBubble(node, path);
            if (state.filterOnly && !hasActive) return "";

            let hasTags = node._tags && node._tags.length > 0;
            let hasSubgroups = false;
            for (let k in node) { if (!k.startsWith('_')) { hasSubgroups = true; break; } }
            let isExpandable = hasTags || hasSubgroups;

            let canAddTags = (level > 0) || (name === "未分类"); 
            let isRoot = level === 0;
            // [修改] 提取原始颜色后，经过引擎进行主题自适应转换
            let rawSelfColor = node._bg_color; 
            let selfColor = getMappedColor(rawSelfColor, configData.theme); 
            let finalColor = isRoot ? (selfColor || 'transparent') : (selfColor || (node._parentBg && node._parentBg !== 'transparent' ? getLighterColor(node._parentBg) : 'transparent'));
            
            let dynTextColor = (finalColor && finalColor !== 'transparent') ? getContrastColor(finalColor) : '';
            let bgStyle = isRoot ? (selfColor ? `background: ${finalColor}; border-color: transparent; --group-text: ${dynTextColor}; --group-arrow: ${dynTextColor};` : ``) : ``;
            let html = `<div class="group ${isRoot ? 'group-root' : 'group-sub'} ${isExpanded ? '' : 'collapsed'}" data-path="${sp}" data-type="group" style="${bgStyle}">`;
            
            let arrowIcon = isExpanded ? 'arrowDown' : 'arrowRight';
            let addBtnHtml = (!state.editMode && canAddTags) ? `<div class="add-tag-btn btn-plus-icon" style="margin-left:4px;" onclick="addTag(event, '${sp}')" oncontextmenu="triggerBatchAddMenu(event, 'tag', '${sp}')" v-html="add"></div>` : '';
            let headerAddBtn = !hasTags ? addBtnHtml : '';

            if (!isRoot) {
                let subBarStyle = `background:${finalColor};`;
                if (dynTextColor) subBarStyle += ` --sub-arrow: ${dynTextColor};`;
                html += `<div class="group-sub-bar" style="${subBarStyle}" onmouseup="onGroupClick(event, '${sp}', '${sn}')">`;
                html += isExpandable ? `<span v-html="${arrowIcon}"></span>` : ``;
                html += `</div>`;
                html += `<div class="group-sub-main">`;
            }

            // [修复] 只有真正存在别名或描述时，才激活悬浮气泡
            let gTooltipHtml = '';
            if (node._alias || (node._descriptions && node._descriptions.length > 0)) {
                // [动态切换] 开启别名显示时，气泡标题显示原名(黄色)；否则显示别名(黄绿色)
                let gTitle = state.showAlias ? name : node._alias;
                let gTitleColor = state.showAlias ? 'var(--hl-tag)' : 'var(--hl-remark)'; // [修改]
                
                if (gTitle) gTooltipHtml += `<div><strong style="color:${gTitleColor};">${_h(gTitle)}</strong></div>`;
                if (node._descriptions && node._descriptions.length > 0) {
                    if (gTitle) gTooltipHtml += `<div style="border-top:1px solid var(--border-color); margin: 6px 0;"></div>`;
                    gTooltipHtml += `<div style="color:var(--text-muted); line-height:1.4;">` + node._descriptions.map(d => _h(d)).join('<div style="border-top:1px dashed var(--border-color); margin: 4px 0; opacity: 0.5;"></div>') + `</div>`;
                }
            }
            let encodedGTooltip = _e(gTooltipHtml);
            let gHoverAttr = gTooltipHtml ? `onmouseenter="showTooltip(event, '${encodedGTooltip}')" onmousemove="moveTooltip(event)" onmouseleave="hideTooltip()"` : '';

            if (isRoot) {
                html += `<div class="group-header" draggable="true" ondragstart="onDragStartTree(event, 'group', '${sp}', '${sn}')" ondragover="onDragOverTree(event)" ondragleave="onDragLeaveTree(event)" ondrop="onDropTree(event, '${sp}', '${sn}')" onmouseup="onGroupClick(event, '${sp}', '${sn}')" oncontextmenu="onGroupCtx(event, '${sp}', ${isRoot}, '${sn}')">`;
                html += isExpandable ? `<span class="group-arrow" v-html="${arrowIcon}"></span>` : `<span class="group-arrow" style="visibility:hidden;" v-html="arrowRight"></span>`;
                html += `<span class="group-title" ${gHoverAttr} data-name="${_h(name)}">${dn}</span><span class="group-dot ${hasActive ? 'show' : ''}">●</span>${headerAddBtn}</div>`;
            } else {
                html += `<div class="group-header" draggable="true" ondragstart="onDragStartTree(event, 'group', '${sp}', '${sn}')" ondragover="onDragOverTree(event)" ondragleave="onDragLeaveTree(event)" ondrop="onDropTree(event, '${sp}', '${sn}')" onmouseup="onGroupClick(event, '${sp}', '${sn}')" oncontextmenu="onGroupCtx(event, '${sp}', ${isRoot}, '${sn}')">`;
                html += `<span class="group-title" ${gHoverAttr} data-name="${_h(name)}">${dn}</span><span class="group-dot ${hasActive ? 'show' : ''}">●</span>${headerAddBtn}</div>`;
            }

            html += `<div class="group-content"><div class="tags-area" ondragover="onDragOverTreeArea(event)" ondragleave="onDragLeaveTreeArea(event)" ondrop="onDropTreeArea(event, '${sp}')">`;
            if (hasTags) {
                let tagBgColor = (isRoot && finalColor && finalColor !== 'transparent') ? getLighterColor(finalColor) : finalColor;
                
                node._tags.forEach(tagRaw => {
                    let pt = parseTag(tagRaw);
                    let tagStr = pt.name; 
                    let st = _e(tagStr);
                    let ht = (state.showAlias && pt.alias) ? _h(pt.alias) : _h(sysT(tagStr)); 
                    let key = `${path}|${tagStr}`; 
                    let tState = state.tagStates[key] || 0; 
                    let cls = tState === 1 ? 's1' : (tState === 2 ? 's2' : (tState === 3 ? 's3' : ''));
                    
                    let styleStr = '';
                    if (tState === 0 && tagBgColor && tagBgColor !== 'transparent') {
                        let textColor = getContrastColor(tagBgColor);
                        styleStr = `style="--bg-btn: ${tagBgColor}; --border-color: ${tagBgColor}; --btn-text: ${textColor};"`;
                    }

                    // [修复] 只有真正存在别名或描述时，才激活悬浮气泡
                    let tTooltipHtml = '';
                    if (pt.alias || (pt.descs && pt.descs.length > 0)) {
                        // [动态切换] 开启别名显示时，气泡标题显示原名(黄色)；否则显示别名(黄绿色)
                        let tTitle = state.showAlias ? pt.name : pt.alias;
                        let tTitleColor = state.showAlias ? 'var(--hl-tag)' : 'var(--hl-remark)'; // [修改]
                        
                        if (tTitle) tTooltipHtml += `<div><strong style="color:${tTitleColor};">${_h(tTitle)}</strong></div>`;
                        if (pt.descs && pt.descs.length > 0) {
                            if (tTitle) tTooltipHtml += `<div style="border-top:1px solid var(--border-color); margin: 6px 0;"></div>`;
                            tTooltipHtml += `<div style="color:var(--text-muted); line-height:1.4;">` + pt.descs.map(d => _h(d)).join('<div style="border-top:1px dashed var(--border-color); margin: 4px 0; opacity: 0.5;"></div>') + `</div>`;
                        }
                    }
                    let encodedTTooltip = _e(tTooltipHtml);
                    let tHoverAttr = tTooltipHtml ? `onmouseenter="showTooltip(event, '${encodedTTooltip}')" onmousemove="moveTooltip(event)" onmouseleave="hideTooltip()"` : '';

                    html += `
                    <div class="tag-btn ${cls}" ${styleStr} ${tHoverAttr} draggable="true" ondragstart="onDragStartTree(event, 'tag', '${sp}', '${st}')" ondragover="onDragOverTreeTag(event)" ondragleave="onDragLeaveTree(event)" ondrop="onDropTreeTag(event, '${sp}', '${st}')" onmouseup="onTagClick(event, '${sp}', '${st}', '${_e(pt.alias)}')"" oncontextmenu="event.preventDefault()">
                        ${ht}<div class="tag-del" onmousedown="event.stopPropagation();" onmouseup="delTagBtn(event, '${sp}', '${st}')" v-html="delete"></div>
                    </div>`;
                });
                if (!state.editMode && canAddTags) html += `<div class="add-tag-btn btn-plus-icon" onclick="addTag(event, '${sp}')" oncontextmenu="triggerBatchAddMenu(event, 'tag', '${sp}')" v-html="add"></div>`;
            }
            html += `</div><div class="subgroups-area">`;
            for (let k in node) { if (!k.startsWith('_')) { node[k]._parentBg = finalColor; let subHtml = buildGroup(k, node[k], path + '/' + k, level + 1); if (subHtml) html += subHtml; } }
            html += `</div></div>`;
            
            if (!isRoot) html += `</div>`; 
            html += `</div>`;
            return html;
        }
        
        function onDragOverTreeArea(e) {
            e.preventDefault(); e.stopPropagation();
            if (dragItem && dragItem.type === 'tag') e.currentTarget.style.backgroundColor = 'rgba(0, 188, 212, 0.05)';
        }
        function onDragLeaveTreeArea(e) {
            e.currentTarget.style.backgroundColor = '';
        }
        function onDropTreeArea(e, targetPath) {
            e.preventDefault(); e.stopPropagation();
            e.currentTarget.style.backgroundColor = '';
            if (!dragItem || dragItem.type !== 'tag') return;
            
            let srcNode = getNodeByPath(dragItem.path);
            let sIdx = srcNode._tags.findIndex(t => parseTag(t).name === dragItem.name);
            if (sIdx > -1) srcNode._tags.splice(sIdx, 1);
            
            let tgtNode = getNodeByPath(targetPath);
            if (!tgtNode._tags) tgtNode._tags = [];
            if (!tgtNode._tags.some(t => parseTag(t).name === dragItem.name)) tgtNode._tags.push(dragItem.name);
            
            saveCompState(); render(); refreshCompUI();
        }

        function onTagClick(e, path, tag, alias='') {
            // 将同一个标签的短时间多次点击当成一次，完美实现你的需求
            if (isThrottled('t_' + path + '_' + tag)) return;

            if (isDragAction(e)) return;
            if (e.target.closest && e.target.closest('.tag-del')) return;

            // 新增：Ctrl + 中键 设置标签属性 (包含描述)
            if (e.ctrlKey && e.button === 1) {
                e.preventDefault(); e.stopPropagation();
                let node = getNodeByPath(path);
                let tagRaw = node._tags.find(t => parseTag(t).name === tag);
                let pt = parseTag(tagRaw);
                openDetailEdit(e.clientX, e.clientY, pt.alias, pt.descs, (res) => {
                    if (res) {
                        let idx = node._tags.findIndex(t => parseTag(t).name === tag);
                        if (idx > -1) {
                            node._tags[idx] = buildTagRaw(tag, res.alias, res.descs);
                            saveCompState(); render();
                        }
                    }
                }, t('set_alias'));
                return;
            }
            
            // Alt + 中键 (e.button === 1)：重命名标签名称
            if (e.altKey && e.button === 1) {
                e.preventDefault(); e.stopPropagation();
                openQuickEdit(e.clientX, e.clientY, tag, (val) => { 
                    if (val && val !== tag) { 
                        let node = getNodeByPath(path); 
                        let idx = node._tags.findIndex(t => parseTag(t).name === tag);
                        if (idx > -1) { 
                            let oldPt = parseTag(node._tags[idx]);
                            node._tags[idx] = buildTagRaw(val.trim(), oldPt.alias, oldPt.descs); 
                            if (state.tagStates[`${path}|${tag}`] !== undefined) {
                                state.tagStates[`${path}|${val.trim()}`] = state.tagStates[`${path}|${tag}`];
                                delete state.tagStates[`${path}|${tag}`];
                            }
                            let cIdx = clickOrder.indexOf(`${path}|${tag}`);
                            if (cIdx > -1) clickOrder[cIdx] = `${path}|${val.trim()}`;
                            saveCompState(); render(); refreshCompUI(); 
                        } 
                    } 
                });
                return;
            }

            if (state.editMode) { 
                e.stopPropagation(); 
                if (e.button === 0) {
                    openQuickEdit(e.clientX, e.clientY, tag, (val) => { 
                        if (val && val !== tag) { 
                            let node = getNodeByPath(path); 
                            let idx = node._tags.findIndex(t => parseTag(t).name === tag);
                            if (idx > -1) { 
                                let oldPt = parseTag(node._tags[idx]);
                                node._tags[idx] = buildTagRaw(val.trim(), oldPt.alias, oldPt.descs); 
                                saveCompState(); render(); refreshCompUI(); 
                            } 
                        } 
                    }); 
                } 
                return; 
            }
            
            // ...以下保持原有的左右键点击切换状态逻辑（只需在 if-else 末尾前补上即可）...
            let key = `${path}|${tag}`; 
            let now = Date.now(); if (now - (lastClickTime[key] || 0) < 150) return; lastClickTime[key] = now;
            let cur = state.tagStates[key] || 0; let nextState = 0;
            if (e.button === 0) nextState = cur === 1 ? 0 : 1; else if (e.button === 2) nextState = cur === 2 ? 0 : 2; else if (e.button === 1) nextState = cur === 3 ? 0 : 3; 
            if (cur === nextState) return; 
            
            state.tagStates[key] = nextState; 

            if (nextState !== 0) {
                if (tag === '""') {
                    Object.keys(state.tagStates).forEach(k => {
                        if (k !== key && state.tagStates[k] !== 0) {
                            state.tagStates[k] = 0;
                            clickOrder = clickOrder.filter(x => x !== k);
                        }
                    });
                } else if (tag === '?*') {
                    Object.keys(state.tagStates).forEach(k => {
                        if (k !== key && state.tagStates[k] !== 0) {
                            let otherTag = k.split('|')[1];
                            if (otherTag === '""' || state.tagStates[k] === 1 || state.tagStates[k] === 3) {
                                state.tagStates[k] = 0;
                                clickOrder = clickOrder.filter(x => x !== k);
                            }
                        }
                    });
                } else {
                    Object.keys(state.tagStates).forEach(k => {
                        let otherTag = k.split('|')[1];
                        if (otherTag === '""' && state.tagStates[k] !== 0) {
                            state.tagStates[k] = 0;
                            clickOrder = clickOrder.filter(x => x !== k);
                        }
                        if (otherTag === '?*' && state.tagStates[k] !== 0 && (nextState === 1 || nextState === 3)) {
                            state.tagStates[k] = 0;
                            clickOrder = clickOrder.filter(x => x !== k);
                        }
                    });
                }
            }

            if (nextState !== 0) {
                if (!clickOrder.includes(key)) clickOrder.push(key);
            } else {
                clickOrder = clickOrder.filter(k => k !== key);
            }
            render();
        }

        function parseQueryStr(str) {
            if (!str) return ""; str = str.replace(/，/g, ',').replace(/（/g, '(').replace(/）/g, ')'); let groups = str.split(',');
            let parsed = groups.map(g => {
                let tokens = g.split(/([+-])/); let res = ""; let isNot = false;
                for (let i=0; i<tokens.length; i++) { let t = tokens[i].trim(); if (t === '+') { isNot = false; continue; } if (t === '-') { isNot = true; continue; } if (t) { if(res !== "") res += " & "; res += (isNot ? "!" : "") + t; } }
                return res;
            }).filter(g => g);
            if (parsed.length > 1) return parsed.map(g => `(${g})`).join(" | "); return parsed[0] || "";
        }

        function buildFilterPayload() {
            let cs = currentCompState(); 
            let tagSyn = "";
            let standaloneTags = [];
            let excludeTags = []; // 新增：专门用于收集要排除的标签
            let actualTagsCount = 0;
            
            clickOrder.forEach((key) => {
                let stateVal = state.tagStates[key]; if (!stateVal) return;
                let tag = key.split('|')[1];
                
                // 处理特殊标签（含标签/无标签）
                if (tag === '?*' || tag === '""') {
                    if (stateVal === 1) standaloneTags.push(tag === '?*' ? 'tags:?*' : '!tags:?*');
                    if (stateVal === 2) standaloneTags.push(tag === '?*' ? '!tags:?*' : 'tags:?*');
                    return;
                }
                
                // 取消强制翻译，保留用户自定义的标签原名
                let formattedTag = tag;
                
                // 【高维修复】：若标签含有 '&' 符号，自动套上英文双引号
                // 防止 XYplorer 将 "R&B" 误判为 "R AND B" 的逻辑运算
                if (formattedTag.includes('&')) {
                    formattedTag = `"${formattedTag}"`;
                }
                
                if (stateVal === 2) {
                    // 如果是排除(红色)，则丢入单独的排除数组
                    excludeTags.push(formattedTag);
                } else {
                    // 如果是包含/或者(绿色/蓝色)，正常拼接到包含链中
                    if (actualTagsCount === 0) tagSyn += formattedTag; 
                    else { 
                        if (stateVal === 1) tagSyn += ` & ${formattedTag}`; 
                        else if (stateVal === 3) tagSyn += ` | ${formattedTag}`; 
                    }
                    actualTagsCount++;
                }
            });
            
            let typeArr = []; let hasFolder = false; let hasNotFolder = false;
            let typeExcludes = [];
            
            for (let k in cs.types) {
                if (k === '文件夹') { if (cs.types[k] === 1) hasFolder = true; if (cs.types[k] === 2) hasNotFolder = true; continue; }
                let realType = presetTypesMap[k] || k; 
                if (cs.types[k] === 1) typeArr.push(realType); 
                if (cs.types[k] === 2) typeExcludes.push(`!${realType}`);
            }
            let typeStr = typeArr.length > 0 ? `/types=${typeArr.join(';')}` : "";
            
            let nameParsed = parseQueryStr(cs.name); let remarkParsed = parseQueryStr(cs.remark);
            let nameStr = nameParsed ? `name:${nameParsed}` : ""; 
            
            let remarkStr = remarkParsed ? `cmt:${remarkParsed}` : "";
            if (cs.remarkMode === 'any') remarkStr = remarkStr ? `cmt:?* & ${remarkStr}` : `cmt:?*`;
            if (cs.remarkMode === 'none') remarkStr = `!cmt:?*`; 
            
            let labelStr = "";
            if (cs.label === 'none') labelStr = `!lbl:?*`;
            else if (cs.label === 'any') labelStr = `lbl:?*`;
            else if (cs.label) labelStr = `lbl:${cs.label}`;
            
            let rateArr = []; 
            for (let k in cs.ratings) { 
                if (cs.ratings[k]) rateArr.push(k === "unrated" ? '!(1 | 2 | 3 | 4 | 5)' : k); 
            }
            let rateStr = rateArr.length > 0 ? `${rateArr.join(' | ')} /fld=rating` : "";
            
            // 语法编译时：智能将同一类型的2个日期合并为区间格式
            let processedRules = [];
            let dateMap = {};
            cs.rules.forEach(r => {
                let match = r.match(/^(dateC|dateM|dateA|ageC|ageM|ageA):\\s*(.*)$/);
                if (match) {
                    let dt = match[1];
                    if (!dateMap[dt]) dateMap[dt] = [];
                    dateMap[dt].push(match[2]);
                } else {
                    processedRules.push(r);
                }
            });
            
            for (let dt in dateMap) {
                let vals = dateMap[dt];
                
                // 智能检测：如果值中包含英文字母(如 dw, m, d, dy 等高级语法)，则不合并，保持独立运算
                let hasLetters = vals.some(v => /[a-zA-Z]/.test(v.replace(/^(>=|<=|==|>|<)\\s*/, '')));
                
                if (vals.length === 2 && !hasLetters) {
                    let v1 = vals[0].replace(/^(>=|<=|==|>|<)\\s*/, '').trim();
                    let v2 = vals[1].replace(/^(>=|<=|==|>|<)\\s*/, '').trim();
                    if (!isNaN(Number(v1)) && !isNaN(Number(v2))) {
                        if (Number(v1) > Number(v2)) { let temp = v1; v1 = v2; v2 = temp; }
                    } else {
                        if (v1 > v2) { let temp = v1; v1 = v2; v2 = temp; }
                    }
                    processedRules.push(`${dt}: ${v1} - ${v2}`);
                } else {
                    vals.forEach(v => processedRules.push(`${dt}: ${v}`));
                }
            }
            
            let ruleStr = processedRules.join(" & ");
            if (hasFolder) ruleStr = ruleStr ? "size: & " + ruleStr : "size:"; if (hasNotFolder) ruleStr = ruleStr ? "!size: & " + ruleStr : "!size:";
            
            let cores = []; 
            if (tagSyn) cores.push(`tags:${tagSyn}`); 
            if (standaloneTags.length > 0) cores.push(standaloneTags.join(" & "));
            // 核心修改2：如果有排除标签，将它们统一合并为一个独立的不包含语法 !(tags:A | B)
            if (excludeTags.length > 0) cores.push(`!(tags:${excludeTags.join(" | ")})`); 
            
            if (nameStr) cores.push(nameStr); 
            if (remarkStr) cores.push(remarkStr); 
            if (labelStr) cores.push(labelStr); 
            if (ruleStr) cores.push(ruleStr);
            if (typeExcludes.length > 0) cores.push(typeExcludes.join(" & "));
            
            let finalFilter = cores.join(" & "); 
            
            if (rateStr) finalFilter += (finalFilter ? " " : "") + rateStr;
            if (typeStr) finalFilter += (finalFilter ? " " : "") + typeStr;
            
            let pathLine = cs.path ? `${t('syn_path')}${cs.path}` : `${t('syn_path')}${t('syn_all_drives')}`;
            
            let displayTagSyn = [];
            if (tagSyn) displayTagSyn.push(`tags:${tagSyn}`);
            if (standaloneTags.length > 0) displayTagSyn.push(standaloneTags.join(" & "));
            // 核心修改3：顶部语法框里展示出独立的排除语法
            if (excludeTags.length > 0) displayTagSyn.push(`!(tags:${excludeTags.join(" | ")})`); 
            
            let line1 = displayTagSyn.length > 0 ? `${t('syn_tags')}${displayTagSyn.join(" & ")}` : "";
            
            let line2 = [typeStr, typeExcludes.join(" & "), nameStr].filter(Boolean).join("  &  "); 
            if (line2) line2 = `${t('syn_type_name')}` + line2; 
            let line3 = [remarkStr, labelStr, rateStr].filter(Boolean).join("  &  "); if (line3) line3 = `${t('syn_attr_rating')}` + line3; 
            let line4 = ruleStr ? `${t('syn_size_date')}${ruleStr}` : "";
            
            let displayStr = [pathLine, line1, line2, line3, line4].filter(Boolean).join("\\n");
            return { single: finalFilter, display: displayStr };
        }
        function updateSyntax() { document.getElementById('syntax-input').value = buildFilterPayload().display; }

        function execSearch() { 
            let cs = currentCompState(); 
            pushHistory('path', cs.path); 
            pushHistory('name', cs.name); 
            pushHistory('remark', cs.remark); 
            
            let p = cs.path || "*"; let f = buildFilterPayload().single; 
            try{pywebview.api.execute_search(p, f, configData.xyPath); showToast(t("search_title"), "success"); }catch(e){} 
        }
        
        function execAddTags() { 
            let activeTags = []; 
            let removeTags = []; 
            
            clickOrder.forEach(key => { 
                let tag = key.split('|')[1];
                if (tag !== '?*' && tag !== '""') {
                    // 取消强制翻译，保留用户自定义的标签原名
                    let translatedTag = tag;
                    
                    if (state.tagStates[key] === 1) {
                        activeTags.push(translatedTag); 
                    } else if (state.tagStates[key] === 2) {
                        removeTags.push(translatedTag); 
                    }
                }
            });
            
            if (activeTags.length === 0 && removeTags.length === 0) {
                return showToast(t("toast_no_tags_act"), "error"); 
            }
            
            let cmd = ""; 
            if (removeTags.length > 0) {
                // 修复：严格去除逗号之间的空格 (,,1,2)，防止英文/欧洲系统的系统区域格式(List Separator)导致解析失败
                cmd += `tag '${removeTags.join(',')}',,1,2; `;
            }
            if (activeTags.length > 0) {
                // 修复：严格去除逗号之间的空格 (,,1)
                cmd += `tag '${activeTags.join(',')}',,1; `;
            }
            cmd = "::" + cmd.trim();
            
            try {
                pywebview.api.execute_script(cmd, configData.xyPath); 
                showToast(t("toast_tag_cmd_sent"), "success"); 
            } catch(e) {} 
        }
        
        function execReadTags() { 
            let cmd = `::copytext tagitems('tags', , , 1);`; 
            try { pywebview.api.execute_script(cmd, configData.xyPath); } catch(e) {} 
            
            showToast(t("toast_reading_clip"), "info");
            setTimeout(() => {
                pywebview.api.read_clipboard_safe().then(text => {
                    try { pywebview.api.focus_window(); } catch(e) {}

                    if (!text) {
                        showToast(t("toast_clip_empty"), "error");
                        return;
                    }
                    
                    if (text.includes('\\n') || text.includes('\\r') || text.length > 500) {
                        showToast(t("toast_clip_long"), "info");
                        batchTarget = { type: 'read_tags' };
                        document.getElementById('batch-title').innerHTML = `<span v-html="importIco"></span> <span data-i18n="read_tag">${t('read_tag')}</span>`;
                        document.getElementById('batch-textarea').value = text;
                        document.getElementById('batch-modal').style.display = 'flex';
                        renderSVGs(document.getElementById('batch-title'));
                        setTimeout(() => document.getElementById('batch-textarea').focus(), 150);
                        return;
                    }
                    
                    let tags = text.split(/[|\\n,]/).map(t => t.trim()).filter(Boolean);
                    tags = [...new Set(tags)];
                    
                    if (tags.length === 0) {
                        showToast(t("toast_read_fail"), "error");
                        return;
                    }
                    
                    clearAllActiveTags();
                    activateTagsFromText(tags);
                    showToast(t("toast_read_success").replace('{n}', tags.length), "success");
                });
            }, 600);
        }
        
        // ======= 新增：批量操作通讯总线控制器 =======
        function showBatchProgressOverlay() {
            document.getElementById('batch-progress-overlay').style.display = 'flex';
            document.getElementById('batch-progress-status').innerText = t('batch_status');
            document.getElementById('batch-cancel-btn').style.display = 'block';
            document.getElementById('batch-done-btn').style.display = 'none';
        }

        function updateBatchProgress(sentCmds, totalFiles) {
            let s = t('batch_sent_cmds').replace('{c}', sentCmds).replace('{t}', totalFiles);
            document.getElementById('batch-progress-status').innerText = s;
        }

        function updateAiProgress(processed, totalFiles) {
            let s = t('ai_processing_status').replace('{c}', processed).replace('{t}', totalFiles);
            document.getElementById('batch-progress-status').innerText = s;
        }

        function finishBatchProgress(success, msg) {
            let iconSvg = success ? 'checkCircle' : 'xCircle';
            let iconColor = success ? 'var(--green)' : 'var(--red)';
            
            // 使用 innerHTML 生成带 SVG 的组合结构，保证图标和文字完美垂直居中对齐
            document.getElementById('batch-progress-status').innerHTML = `<div style="display:flex; align-items:center; justify-content:center; gap:6px;"><span style="width:16px; height:16px; color:${iconColor}; display:flex; align-items:center;" v-html="${iconSvg}"></span><span>${_h(msg)}</span></div>`;
            renderSVGs(document.getElementById('batch-progress-status'));
            
            document.getElementById('batch-cancel-btn').style.display = 'none';
            document.getElementById('batch-done-btn').style.display = 'block';
        }

        function closeBatchProgressOverlay() {
            document.getElementById('batch-progress-overlay').style.display = 'none';
        }

        function cancelBatchOperation() {
            if (window.pywebview && window.pywebview.api) {
                document.getElementById('batch-progress-status').innerText = t('cancelling');
                pywebview.api.cancel_batch();
            }
        }
        
        // ======= 改写原有的批量执行入口 (剥除文字内的 Emoji) =======
        function execBatchUCS() {
            document.getElementById('action-btn-ctx-menu').style.display = 'none';
            showBatchProgressOverlay();
            pywebview.api.batch_ucs_tags(configData.xyPath).then(res => {
                if (res && res.success) finishBatchProgress(true, t("toast_ucs_success").replace('{n}', res.count));
                else finishBatchProgress(false, t("toast_ucs_fail") + (res ? res.msg : ""));
            });
        }
        
        function execBatchUCSName() {
            document.getElementById('action-btn-ctx-menu').style.display = 'none';
            showBatchProgressOverlay();
            pywebview.api.batch_ucs_name_tags(configData.xyPath).then(res => {
                if (res && res.success) finishBatchProgress(true, t("toast_ucs_success").replace('{n}', res.count));
                else finishBatchProgress(false, t("toast_ucs_fail") + (res ? res.msg : ""));
            });
        }

        function execAITagging(mode, domain = "通用") {
            document.getElementById('action-btn-ctx-menu').style.display = 'none';
            showBatchProgressOverlay();
            pywebview.api.ai_batch_process(configData.xyPath, mode, domain).then(res => {
                if (res && res.success) {
                    finishBatchProgress(true, t("toast_ai_success").replace('{n}', res.count));
                    if ((mode === 'auto_name' || mode === 'auto_content' || mode === 'auto_name_en_zh') && res.tags && res.tags.length > 0) {
                        clearAllActiveTags(); 
                        activateTagsFromText(res.tags);
                    }
                } else { 
                    finishBatchProgress(false, t("toast_ai_fail") + (res ? res.msg : "")); 
                }
            });
        }
        
        function activateTagsFromText(tags) { 
            let tree = currentTree(); let changed = false; 
            tags.forEach(rawT => { 
                if (!rawT || rawT.includes("Ctrl+V") || rawT.includes("剪贴板")) return; 
                
                let tKey = reverseSysT(rawT);
                let pt = parseTag(tKey); // [修改] 智能剥离别名
                
                let foundPath = findTagPath(tree, "", pt.name); // [修改] 用纯净的英文名去查找
                if (foundPath) { 
                    state.tagStates[`${foundPath}|${pt.name}`] = 1; 
                    if (!clickOrder.includes(`${foundPath}|${pt.name}`)) clickOrder.push(`${foundPath}|${pt.name}`); 
                    let parts = foundPath.split('/'); let curP = ""; 
                    parts.forEach(p => { curP += (curP?"/":"")+p; state.expandedGroups[curP] = true; }); 
                    changed = true; 
                } else { 
                    if (!tree["未分类"]) tree["未分类"] = { "_bg_color": "", "_tags": ["?*", '""'] }; 
                    if (!tree["未分类"]._tags.some(t => parseTag(t).name === pt.name)) tree["未分类"]._tags.push(tKey); // [修改] 写入完整的 English@@中文
                    state.tagStates[`未分类|${pt.name}`] = 1; 
                    if (!clickOrder.includes(`未分类|${pt.name}`)) clickOrder.push(`未分类|${pt.name}`); 
                    state.expandedGroups["未分类"] = true; 
                    changed = true; 
                } 
            });
            
            if (changed) { 
                state.activeOnly = true;
                document.getElementById('btn-active').classList.add('active-green');
                state.filterOnly = false;
                document.getElementById('btn-filter').classList.remove('active-green');
                
                for (let k in state.expandedGroups) state.expandedGroups[k] = false;
                forceExpandActive(currentTree(), "");
                saveCompState(); render(); refreshCompUI(); 
            } 
        }

        function findTagPath(node, path, tag) { if (node._tags && node._tags.some(t => parseTag(t).name === tag)) return path; for (let k in node) { if (!k.startsWith('_')) { let res = findTagPath(node[k], path ? path+'/'+k : k, tag); if (res) return res; } } return null; }
        function clearAllFiltersAndTags() { clearCompFilters(); clearAll(); showToast(t("clear_title"), "success"); }
        function checkActiveBubble(node, path) { if (node._tags && node._tags.some(t => state.tagStates[`${path}|${parseTag(t).name}`])) return true; for (let k in node) { if (!k.startsWith('_') && checkActiveBubble(node[k], path + '/' + k)) return true; } return false; }

        // 【高维重构】：独立元素节流器。
        // 彻底解决快速点击不同标签/组名时，后续点击被误判为双击而失效的“断触”现象。
        let clickThrottleMap = {};
        function isThrottled(key, ms = 250) {
            let now = Date.now();
            if (clickThrottleMap[key] && now - clickThrottleMap[key] < ms) return true;
            clickThrottleMap[key] = now;
            return false;
        }

        function onGroupClick(e, path, name) { 
            // 将同一个组名的短时间多次点击当成一次，但不影响你光速连点不同的组
            if (isThrottled('g_' + path)) return;

            if (isDragAction(e)) return;
            
            // 新增：Ctrl + 中键 设置组名属性 (包含描述)
            if (e.ctrlKey && e.button === 1) {
                e.preventDefault(); e.stopPropagation();
                let parent = getParentNode(path);
                let node = parent[name];
                let oldAlias = node._alias || '';
                let oldDescs = node._descriptions || [];
                
                openDetailEdit(e.clientX, e.clientY, oldAlias, oldDescs, (res) => {
                    if (res) {
                        let trimmed = res.alias.trim();
                        let newNode = {};
                        if (trimmed) newNode._alias = trimmed;
                        if (res.descs && res.descs.length > 0) newNode._descriptions = res.descs;
                        if (node.hasOwnProperty('_bg_color')) newNode._bg_color = node._bg_color;
                        if (node.hasOwnProperty('_tags')) newNode._tags = node._tags;
                        
                        for (let k in node) {
                            if (k !== '_alias' && k !== '_descriptions' && k !== '_bg_color' && k !== '_tags') {
                                newNode[k] = node[k];
                            }
                        }
                        parent[name] = newNode;
                        saveCompState(); render(); 
                    }
                }, t('set_alias'));
                return;
            }

            // Alt + 中键 (e.button === 1)：重命名
            if (e.altKey && e.button === 1) {
                e.preventDefault(); e.stopPropagation();
                if (name === "未分类") return;
                openQuickEdit(e.clientX, e.clientY, name, (val) => { 
                    if (val && val !== name) { 
                        let parent = getParentNode(path); let newObj = {}; 
                        for (let k in parent) { if (k === name) newObj[val] = parent[name]; else newObj[k] = parent[k]; } 
                        for (let k in parent) delete parent[k]; 
                        for (let k in newObj) parent[k] = newObj[k]; 
                        let newPath = path.substring(0, path.lastIndexOf('/') + 1) + val; 
                        state.expandedGroups[newPath] = state.expandedGroups[path]; 
                        saveCompState(); render(); refreshCompUI(); 
                    } 
                });
                return;
            }
            
            // Alt + 左键 (e.button === 0)：展开子组
            if (e.altKey && e.button === 0) {
                e.preventDefault(); e.stopPropagation();
                ctxTarget = { path: path, name: name };
                ctxAction('expand-all');
                return;
            }

            if (e.button !== 0) return; // 仅放行普通的左键点击进入原逻辑
            
            if (state.editMode) { 
                e.stopPropagation(); if (name === "未分类") return; 
                openQuickEdit(e.clientX, e.clientY, name, (val) => { 
                    if (val && val !== name) { 
                        let parent = getParentNode(path); let newObj = {}; 
                        for (let k in parent) { if (k === name) newObj[val] = parent[name]; else newObj[k] = parent[k]; } 
                        for (let k in parent) delete parent[k]; 
                        for (let k in newObj) parent[k] = newObj[k]; 
                        let newPath = path.substring(0, path.lastIndexOf('/') + 1) + val; 
                        state.expandedGroups[newPath] = state.expandedGroups[path]; 
                        saveCompState(); render(); refreshCompUI(); 
                    } 
                }); 
            } else { 
                let node = getNodeByPath(path);
                let hasTags = node._tags && node._tags.length > 0;
                let hasSubgroups = false;
                for (let k in node) { if (!k.startsWith('_')) { hasSubgroups = true; break; } }
                if (!hasTags && !hasSubgroups) return; 

                state.expandedGroups[path] = !state.expandedGroups[path]; 
                saveCompState(); // [修复] 保存点击后的折叠状态
                render(); 
            } 
        }
        function addRootGroup(e) { openQuickEdit(e.clientX, e.clientY, "", (val) => { if (val && !currentTree()[val]) { currentTree()[val] = {"_tags": [], "_bg_color": ""}; initExpandedState(currentTree(), ""); /* [修复] 注册新根组 */ saveCompState(); render(); refreshCompUI(); } }); }
        
        // 加入了 e.stopPropagation() 以防止在组名栏点击+号时触发展开操作
        function addTag(e, path) { 
            e.stopPropagation(); 
            openQuickEdit(e.clientX, e.clientY, "", (val) => { 
                if (val) { 
                    let node = getNodeByPath(path); 
                    if (!node._tags) node._tags = []; 
                    if (!node._tags.some(t => parseTag(t).name === val)) { 
                        node._tags.push(val); 
                        saveCompState(); render(); 
                    } 
                } 
            }); 
        }

        function delTagBtn(e, path, tag) { 
            e.stopPropagation(); e.preventDefault(); 
            let node = getNodeByPath(path); 
            node._tags = node._tags.filter(t => parseTag(t).name !== tag); 
            delete state.tagStates[`${path}|${tag}`]; 
            clickOrder = clickOrder.filter(k => k !== `${path}|${tag}`); 
            saveCompState(); render(); refreshCompUI(); 
            sysLog(t("log_tag_del").replace('{tag}', tag), "INFO");
        }

        const ctxMenu = document.getElementById('ctx-menu');
        function onGroupCtx(e, path, isRoot, name) { 
            // Alt + 右键：折叠子组 (直接执行动作，不弹出菜单)
            if (e.altKey) {
                e.preventDefault(); e.stopPropagation();
                ctxTarget = { path: path, name: name };
                ctxAction('collapse-leaf');
                return;
            }

            e.preventDefault(); e.stopPropagation(); ctxTarget = { path, isRoot, name }; 
            let isUncat = (name === '未分类');
            document.getElementById('ctx-del').style.display = isUncat ? 'none' : 'flex'; 
            let renameBtn = document.getElementById('ctx-rename');
            if (renameBtn) renameBtn.style.display = isUncat ? 'none' : 'flex';
            let expBtn = document.getElementById('ctx-expand');
            if (expBtn) expBtn.style.display = isUncat ? 'none' : 'flex';
            let colBtn = document.getElementById('ctx-collapse');
            if (colBtn) colBtn.style.display = isUncat ? 'none' : 'flex';
            
            let rstUncatBtn = document.getElementById('ctx-reset-uncat');
            if (rstUncatBtn) rstUncatBtn.style.display = isUncat ? 'flex' : 'none';
            
            ctxMenu.style.display = 'flex'; setSafePosition(ctxMenu, e.clientX, e.clientY);
            
            let wsKeys = getWsList().filter(w => w !== configData.currentWs); 
            
            let sMove = document.getElementById('sub-move'); let sCopy = document.getElementById('sub-copy'); 
            if (wsKeys.length > 0) { 
                sMove.innerHTML = ''; sCopy.innerHTML = ''; 
                wsKeys.forEach(w => { 
                    let sw = _e(w); let hw = _h(sysT(w));
                    sMove.innerHTML += `<div class="submenu-item" onclick="execWsTransfer('move', '${sw}')">${hw}</div>`; 
                    sCopy.innerHTML += `<div class="submenu-item" onclick="execWsTransfer('copy', '${sw}')">${hw}</div>`; 
                }); 
            } else { 
                sMove.innerHTML = `<div class="submenu-item" style="color:var(--text-muted);">${t('no_other_ws')}</div>`; 
                sCopy.innerHTML = `<div class="submenu-item" style="color:var(--text-muted);">${t('no_other_ws')}</div>`; 
            } 
        }
        
        function ctxAction(action) { 
            ctxMenu.style.display = 'none'; let p = ctxTarget.path, n = ctxTarget.name; 
            
            // --- 新增：批量组内标签操作逻辑 ---
            if (action === 'select-all-or') {
                let node = getNodeByPath(p); let allT = getAllTagsInGroup(node, p); let changed = false;
                allT.forEach(item => {
                    if(item.tag === '""' || item.tag === '?*') return; // 跳过特殊标签
                    let key = `${item.path}|${item.tag}`;
                    if(state.tagStates[key] === 1 || state.tagStates[key] === 2) { delete state.tagStates[key]; clickOrder = clickOrder.filter(x => x !== key); }
                    if(state.tagStates[key] !== 3) { state.tagStates[key] = 3; if(!clickOrder.includes(key)) clickOrder.push(key); changed = true; }
                });
                if (changed) { // 清除冲突的特殊过滤
                    Object.keys(state.tagStates).forEach(k => { let otherTag = k.split('|')[1]; if(otherTag === '""' || otherTag === '?*') { delete state.tagStates[k]; clickOrder = clickOrder.filter(x => x !== k); } });
                }
                saveCompState(); render(); refreshCompUI();
            }
            else if (action === 'exclude-all') {
                let node = getNodeByPath(p); let allT = getAllTagsInGroup(node, p); let changed = false;
                allT.forEach(item => {
                    if(item.tag === '""' || item.tag === '?*') return; // 跳过特殊标签
                    let key = `${item.path}|${item.tag}`;
                    if(state.tagStates[key] === 1 || state.tagStates[key] === 3) { delete state.tagStates[key]; clickOrder = clickOrder.filter(x => x !== key); }
                    if(state.tagStates[key] !== 2) { state.tagStates[key] = 2; if(!clickOrder.includes(key)) clickOrder.push(key); changed = true; }
                });
                if (changed) { // 清除冲突的特殊过滤
                    Object.keys(state.tagStates).forEach(k => { let otherTag = k.split('|')[1]; if(otherTag === '""' || otherTag === '?*') { delete state.tagStates[k]; clickOrder = clickOrder.filter(x => x !== k); } });
                }
                saveCompState(); render(); refreshCompUI();
            }
            else if (action === 'clear-group') {
                let node = getNodeByPath(p); let allT = getAllTagsInGroup(node, p);
                allT.forEach(item => {
                    let key = `${item.path}|${item.tag}`;
                    if (state.tagStates[key] !== undefined) { delete state.tagStates[key]; clickOrder = clickOrder.filter(x => x !== key); }
                });
                saveCompState(); render(); refreshCompUI();
            }
            // --- 批量逻辑结束 ---
            
            else if (action === 'color') { let node = getNodeByPath(p); openColorModal(node._bg_color || "", (newHex) => { if (newHex) { node._bg_color = newHex; saveCompState(); render(); refreshCompUI(); sysLog(t("log_grp_color_upd"), "INFO"); } }); }
            else if (action === 'color-reset') { let node = getNodeByPath(p); delete node._bg_color; saveCompState(); render(); refreshCompUI(); sysLog(t("log_grp_color_rst"), "INFO"); }
            else if (action === 'reset-uncat') {
                if (n !== "未分类") return;
                let node = getNodeByPath(p);
                node._tags = ["?*", '""'];
                // 同步清理被删除标签的激活状态，防止产生幽灵过滤项
                Object.keys(state.tagStates).forEach(k => {
                    if (k.startsWith(p + '|') && k !== (p + '|?*') && k !== (p + '|""')) {
                        delete state.tagStates[k];
                        clickOrder = clickOrder.filter(x => x !== k);
                    }
                });
                saveCompState(); render(); refreshCompUI();
                sysLog(t("log_uncat_rst"), "INFO");
            }
            else if (action === 'rename') {
                if (n === "未分类") return; 
                openQuickEdit(gStartX, gStartY, n, (val) => { 
                    if (val && val !== n) { 
                        let parent = getParentNode(p); let newObj = {}; 
                        for (let k in parent) { if (k === n) newObj[val] = parent[n]; else newObj[k] = parent[k]; } 
                        for (let k in parent) delete parent[k]; 
                        for (let k in newObj) parent[k] = newObj[k]; 
                        let newPath = p.substring(0, p.lastIndexOf('/') + 1) + val; 
                        state.expandedGroups[newPath] = state.expandedGroups[p]; 
                        saveCompState(); render(); refreshCompUI(); 
                    } 
                });
            }
            else if (action === 'expand-all') {
                if (n === "未分类") return;
                let node = getNodeByPath(p);
                function _expandAll(nd, curPath) {
                    state.expandedGroups[curPath] = true;
                    for(let k in nd) { if(!k.startsWith('_')) _expandAll(nd[k], curPath + '/' + k); }
                }
                _expandAll(node, p);
                saveCompState(); // [修复] 保存状态
                render(); 
            }
            else if (action === 'collapse-leaf') {
                if (n === "未分类") return;
                let node = getNodeByPath(p);
                function _isLeaf(nd) {
                    for(let k in nd) if(!k.startsWith('_')) return false; // 如果有子字典说明不是叶子
                    return true;
                }
                function _collapseLeaf(nd, curPath, isRoot) {
                    if (!isRoot && _isLeaf(nd)) {
                        state.expandedGroups[curPath] = false; // 叶子节点折叠
                    } else {
                        if (isRoot) state.expandedGroups[curPath] = true; // 确保右键的母组保持展开
                        for(let k in nd) { if(!k.startsWith('_')) _collapseLeaf(nd[k], curPath + '/' + k, false); }
                    }
                }
                _collapseLeaf(node, p, true);
                saveCompState(); // [修复] 保存状态
                render();
            }
            else if (action === 'add') { openQuickEdit(gStartX, gStartY, "", val => { if (val) { getNodeByPath(p)[val] = {"_tags": []}; state.expandedGroups[p] = true; initExpandedState(currentTree(), ""); /* [修复] 注册新子组 */ saveCompState(); render(); refreshCompUI(); } }); }
            else if (action === 'batch-add') { batchTarget = { type: 'subgroup', path: p }; executeBatchAddMenu(); }
            else if (action === 'add-tag') {
                openQuickEdit(gStartX, gStartY, "", val => {
                    if (val) {
                        let node = getNodeByPath(p);
                        if (!node._tags) node._tags = [];
                        if (!node._tags.includes(val)) { node._tags.push(val); saveCompState(); render(); refreshCompUI(); }
                    }
                });
            }
            else if (action === 'batch-add-tag') { batchTarget = { type: 'tag', path: p }; executeBatchAddMenu(); }
            else if (action === 'delete') { if (n === "未分类") return; let parent = getParentNode(p); delete parent[n]; saveCompState(); render(); refreshCompUI(); } 
        }
        function execWsTransfer(action, targetWs) { ctxMenu.style.display = 'none'; if (ctxTarget.name === "未分类") return showToast(t("toast_no_uncat_op"), "error"); let parent = getParentNode(ctxTarget.path); let dataCopy = JSON.parse(JSON.stringify(parent[ctxTarget.name])); allTreeData[targetWs][ctxTarget.name] = dataCopy; if (action === 'move') delete parent[ctxTarget.name]; saveCompState(); render(); refreshCompUI(); }

        function getNodeByPath(pathStr) { let parts = pathStr.split('/'); let curr = currentTree(); for (let p of parts) curr = curr[p]; return curr; }
        function getParentNode(pathStr) { let parts = pathStr.split('/'); let curr = currentTree(); for (let i = 0; i < parts.length - 1; i++) curr = curr[parts[i]]; return curr; }

        function getNodeByPath(pathStr) { let parts = pathStr.split('/'); let curr = currentTree(); for (let p of parts) curr = curr[p]; return curr; }
        function getParentNode(pathStr) { let parts = pathStr.split('/'); let curr = currentTree(); for (let i = 0; i < parts.length - 1; i++) curr = curr[parts[i]]; return curr; }

        // --- 新增：递归获取当前组及其所有子组内的全部标签 ---
        function getAllTagsInGroup(node, path) {
            let tags = [];
            if (node._tags) {
                node._tags.forEach(tRaw => { tags.push({ path: path, tag: parseTag(tRaw).name }); });
            }
            for (let k in node) {
                if (!k.startsWith('_')) {
                    tags = tags.concat(getAllTagsInGroup(node[k], path ? path + '/' + k : k));
                }
            }
            return tags;
        }

        function onDragStartTree(e, type, path, name) { dragItem = { type, path, name }; e.dataTransfer.setData('text', 'dummy'); e.stopPropagation(); }
        function onDragLeaveTree(e) { e.currentTarget.classList.remove('drag-top', 'drag-bottom', 'drag-center', 'drag-left', 'drag-right'); }
        
        function onDragOverTree(e) { 
            e.preventDefault(); e.stopPropagation(); 
            let el = e.currentTarget; 
            el.classList.remove('drag-top', 'drag-bottom', 'drag-center'); 
            
            if (dragItem.type === 'tag') { 
                let name = el.querySelector('.group-title').dataset.name; 
                let isRoot = el.parentElement.classList.contains('group-root'); 
                if (!isRoot || name === "未分类") el.classList.add('drag-center'); 
                return; 
            } 
            
            let r = el.getBoundingClientRect(); 
            let y = e.clientY - r.top; 
            
            if (y < r.height * 0.25) el.classList.add('drag-top'); 
            else if (y > r.height * 0.75) el.classList.add('drag-bottom'); 
            else el.classList.add('drag-center'); 
        }
        
        function onDropTree(e, targetPath, targetName) { 
            e.preventDefault(); e.stopPropagation(); 
            e.currentTarget.classList.remove('drag-top', 'drag-bottom', 'drag-center'); 
            
            if (dragItem.type === 'tag') { 
                let name = e.currentTarget.querySelector('.group-title').dataset.name; 
                let isRoot = e.currentTarget.parentElement.classList.contains('group-root'); 
                if (isRoot && name !== "未分类") return; 
                let srcNode = getNodeByPath(dragItem.path); 
                srcNode._tags = srcNode._tags.filter(t => t !== dragItem.name); 
                let tgtNode = getNodeByPath(targetPath); 
                if (!tgtNode._tags) tgtNode._tags = []; 
                if (!tgtNode._tags.some(t => parseTag(t).name === dragItem.name)) tgtNode._tags.push(dragItem.name); 
            } 
            else if (dragItem.type === 'group') { 
                if (targetPath === dragItem.path || targetPath.startsWith(dragItem.path + '/')) return; 
                if (dragItem.name === "未分类" || targetName === "未分类") return; 
                
                let r = e.currentTarget.getBoundingClientRect(); 
                let y = e.clientY - r.top; 
                
                let tgtParent = getParentNode(targetPath);
                let srcParent = getParentNode(dragItem.path); 
                let movingData = srcParent[dragItem.name]; 
                
                delete srcParent[dragItem.name]; 
                
                if (y >= r.height * 0.25 && y <= r.height * 0.75) { 
                    getNodeByPath(targetPath)[dragItem.name] = movingData; 
                    state.expandedGroups[targetPath] = true; 
                } else { 
                    let newDict = {}; 
                    for (let k in tgtParent) {
                        if (k.startsWith('_')) newDict[k] = tgtParent[k];
                    }
                    if (tgtParent["未分类"]) newDict["未分类"] = tgtParent["未分类"]; 
                    
                    let keys = Object.keys(tgtParent).filter(k => !k.startsWith('_') && k !== "未分类" && k !== dragItem.name); 
                    
                    let tIdx = keys.indexOf(targetName);
                    if (y < r.height * 0.25) {
                        keys.splice(tIdx, 0, dragItem.name); 
                    } else {
                        keys.splice(tIdx + 1, 0, dragItem.name); 
                    }
                    
                    keys.forEach(k => {
                        if (k === dragItem.name) newDict[k] = movingData;
                        else newDict[k] = tgtParent[k];
                    });
                    
                    for (let k in tgtParent) delete tgtParent[k]; 
                    for (let k in newDict) tgtParent[k] = newDict[k]; 
                } 
            } 
            saveCompState(); render(); refreshCompUI(); 
        }
        
        function onDragOverTreeTag(e) { e.preventDefault(); e.stopPropagation(); if (dragItem.type !== 'tag') return; let el = e.currentTarget; el.classList.remove('drag-left', 'drag-right'); let r = el.getBoundingClientRect(); if (e.clientX - r.left < r.width / 2) el.classList.add('drag-left'); else el.classList.add('drag-right'); }
        
        function onDropTreeTag(e, targetPath, targetTag) { 
            e.preventDefault(); e.stopPropagation(); 
            e.currentTarget.classList.remove('drag-left', 'drag-right'); 
            if (!dragItem || dragItem.type !== 'tag') return; 
            if (dragItem.path === targetPath && dragItem.name === targetTag) return; 
            
            let srcNode = getNodeByPath(dragItem.path); 
            let sIdx = srcNode._tags.findIndex(t => parseTag(t).name === dragItem.name);
            if (sIdx > -1) srcNode._tags.splice(sIdx, 1); 
            
            let tgtNode = getNodeByPath(targetPath); 
            if (!tgtNode._tags) tgtNode._tags = []; 
            let tIdx = tgtNode._tags.findIndex(t => parseTag(t).name === targetTag);  
            if (tIdx < 0) tIdx = tgtNode._tags.length;
            
            let r = e.currentTarget.getBoundingClientRect(); 
            if (e.clientX - r.left >= r.width / 2) tIdx++; 
            tgtNode._tags.splice(tIdx, 0, dragItem.name); 
            saveCompState(); render(); refreshCompUI(); 
        }

        function triggerBatchAddMenu(e, type, path, forcedX, forcedY) {
            if(e) { e.preventDefault(); e.stopPropagation(); }
            batchTarget = { type, path };
            const menu = document.getElementById('batch-add-menu');
            
            // 核心功能：右键 + 号时，如果是根目录级别，动态显示出导出/导入工作区选项
            const showIO = (type === 'root');
            document.getElementById('ws-io-separator').style.display = showIO ? 'block' : 'none';
            document.getElementById('ws-export-btn').style.display = showIO ? 'flex' : 'none';
            document.getElementById('ws-import-btn').style.display = showIO ? 'flex' : 'none';

            menu.style.display = 'flex';
            setSafePosition(menu, e ? e.clientX : forcedX, e ? e.clientY : forcedY);
            renderSVGs(menu);
        }

        async function exportCurrentWorkspace() {
            document.getElementById('batch-add-menu').style.display = 'none';
            let wsData = currentTree();
            let res = await pywebview.api.export_workspace(JSON.stringify(wsData, null, 2), configData.currentWs);
            if (res && res.success) showToast(t('toast_export_ok'), 'success');
            else if (res && !res.success && res.msg !== "Cancelled") showToast(t('toast_export_fail'), 'error');
        }

        function importToWorkspace() {
            document.getElementById('batch-add-menu').style.display = 'none';
            document.getElementById('import-ws-file').click();
        }

        function handleImportWorkspace(e) {
            let file = e.target.files[0]; if (!file) return;
            let reader = new FileReader();
            reader.onload = function(evt) {
                try {
                    let data = JSON.parse(evt.target.result);
                    let tree = currentTree();
                    for (let k in data) {
                        if (k === '_compState') continue;
                        if (!tree[k]) tree[k] = data[k];
                        else {
                            let existingTags = tree[k]._tags || [];
                            let newTags = data[k]._tags || [];
                            newTags.forEach(tRaw => { if (!existingTags.some(et => parseTag(et).name === parseTag(tRaw).name)) existingTags.push(tRaw); });
                            tree[k]._tags = existingTags;
                            if (data[k]._bg_color) tree[k]._bg_color = data[k]._bg_color;
                            if (data[k]._alias) tree[k]._alias = data[k]._alias;
                            for (let child in data[k]) {
                                if (child.startsWith('_')) continue;
                                if (!tree[k][child]) tree[k][child] = data[k][child];
                                else {
                                    let cExistingTags = tree[k][child]._tags || [];
                                    let cNewTags = data[k][child]._tags || [];
                                    cNewTags.forEach(tRaw => { if (!cExistingTags.some(et => parseTag(et).name === parseTag(tRaw).name)) cExistingTags.push(tRaw); });
                                    tree[k][child]._tags = cExistingTags;
                                    if (data[k][child]._parentBg) tree[k][child]._parentBg = data[k][child]._parentBg;
                                    if (data[k][child]._alias) tree[k][child]._alias = data[k][child]._alias;
                                }
                            }
                        }
                    }
                    initExpandedState(currentTree(), ""); // [修复] 立即扫描并注册新导入节点的展开状态
                    saveCompState(); render(); refreshCompUI(); 
                    showToast(t('toast_import_ok'), 'success');
                } catch (err) { showToast(t('toast_import_err'), 'error'); }
                e.target.value = '';
            };
            reader.readAsText(file);
        }

        function executeBatchAddMenu() {
            document.getElementById('batch-add-menu').style.display = 'none';
            document.getElementById('batch-title').innerHTML = `<span v-html="add"></span> <span data-i18n="batch_add">${t('batch_add')}</span>`;
            renderSVGs(document.getElementById('batch-title'));
            document.getElementById('batch-textarea').value = "";
            document.getElementById('batch-modal').style.display = 'flex';
            setTimeout(() => document.getElementById('batch-textarea').focus(), 150);
        }

        function closeBatchModal() { document.getElementById('batch-modal').style.display = 'none'; }

        let currentConfirmCallback = null;

        function showConfirmModal(msg, callback, type = 'delete') {
            document.getElementById('confirm-msg').innerText = msg;
            currentConfirmCallback = callback;
            
            const modal = document.getElementById('confirm-modal');
            const content = modal.querySelector('.modal-content');
            let header = document.getElementById('confirm-header');
            let titleIcon = document.getElementById('confirm-title-icon');
            let titleText = document.getElementById('confirm-title-text');
            let confirmBtn = document.getElementById('confirm-btn');
            
            // 动态改变弹窗主题颜色和文字
            if (type === 'update') {
                header.style.color = 'var(--primary)';
                titleIcon.innerHTML = SVGS.info;
                titleText.innerText = t('update_found');
                confirmBtn.innerText = t('confirm');
                confirmBtn.style.background = 'var(--primary)';
            } else {
                header.style.color = 'var(--red)';
                titleIcon.innerHTML = SVGS.delete;
                titleText.innerText = t('confirm_del_title');
                confirmBtn.innerText = t('delete');
                confirmBtn.style.background = 'var(--red)';
            }
            
            modal.style.display = 'flex';
            content.style.position = 'absolute';
            content.style.margin = '0';
            
            let w = content.offsetWidth; let h = content.offsetHeight;
            let x = (window.innerWidth - w) / 2; let y = gStartY - h / 2;
            x = Math.max(10, x);
            y = Math.max(10, Math.min(y, window.innerHeight - h - 10));
            content.style.left = x + 'px'; content.style.top = y + 'px';
        }

        function closeConfirmModal() {
            document.getElementById('confirm-modal').style.display = 'none';
            currentConfirmCallback = null;
        }

        function executeConfirm() {
            if (currentConfirmCallback) {
                currentConfirmCallback();
            }
            closeConfirmModal();
        }

        function confirmBatchAdd() {
            let text = document.getElementById('batch-textarea').value;
            
            if (batchTarget && batchTarget.type === 'read_tags') {
                let tags = text.split(/[|\\n,]/).map(t => t.trim()).filter(Boolean);
                tags = [...new Set(tags)]; 
                
                if (tags.length === 0) {
                    showToast(t("toast_read_none"), "error");
                } else {
                    clearAllActiveTags();
                    activateTagsFromText(tags);
                    showToast(t("toast_read_success").replace('{n}', tags.length), "success");
                }
                return closeBatchModal();
            }

            let lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
            lines = [...new Set(lines)];

            if(lines.length === 0) return closeBatchModal();

            if(batchTarget.type === 'ext') {
                let cs = currentCompState();
                if (!cs.customExts) cs.customExts = [];
                if (!cs.orderExt) cs.orderExt = [];
                lines.forEach(val => {
                    if (!cs.customExts.includes(val)) {
                        cs.customExts.push(val);
                        cs.orderExt.push(val);
                    }
                });
                saveCompState();
                renderCustomExts();
            } else if (batchTarget.type === 'root') {
                lines.forEach(val => {
                    if (!currentTree()[val]) currentTree()[val] = {"_tags": [], "_bg_color": ""};
                });
                initExpandedState(currentTree(), ""); // [修复] 注册新批量根组
                saveCompState(); render(); refreshCompUI();
            } else if (batchTarget.type === 'tag') {
                let node = getNodeByPath(batchTarget.path);
                if (!node._tags) node._tags = [];
                lines.forEach(val => {
                    if (!node._tags.includes(val)) node._tags.push(val);
                });
                saveCompState(); render(); refreshCompUI();
            } else if (batchTarget.type === 'subgroup') {
                let node = getNodeByPath(batchTarget.path);
                lines.forEach(val => {
                    if(!node[val]) node[val] = {"_tags": []};
                });
                state.expandedGroups[batchTarget.path] = true;
                initExpandedState(currentTree(), ""); // [修复] 注册新批量子组
                saveCompState(); render(); refreshCompUI();
            }
            showToast(t("toast_batch_add_ok"), "success");
            closeBatchModal();
        }

        const palettes = { cyber: ['#0B0C10', '#1A1B26', '#311B92', '#4A148C', '#004D40', '#00221C'], ocean: ['#0D1B2A', '#1A252C', '#102027', '#00332A', '#001F3F', '#0A1128'], gold: ['#2A191B', '#3E2723', '#4E342E', '#3E2723', '#263238', '#212121'], morD: ['#2A2D34', '#3B3F46', '#4C525A', '#5E656E', '#1F2229', '#15171C'], summer:['#E3F2FD', '#E8F5E9', '#FFF3E0', '#FCE4EC', '#F3E5F5', '#E0F7FA'], macaron:['#FFB7B2', '#FFDAC1', '#E2F0CB', '#B5EAD7', '#C7CEEA', '#F1CBFF'], wood: ['#F5F5DC', '#FAF0E6', '#FFF8DC', '#FFEBCD', '#FFE4C4', '#FFDEAD'], morL: ['#F5F5F5', '#EBEBEB', '#E0E0E0', '#D6D6D6', '#FAFAFA', '#FFFFFF'] };
        function initColorPicker() { const createRow = (colors, id) => { let html = ''; colors.forEach(c => html += `<div class="color-swatch" style="background:${c};" onclick="selectColor('${c}')"></div>`); document.getElementById(id).innerHTML = html; }; createRow(palettes.cyber, 'pal-cyber'); createRow(palettes.ocean, 'pal-ocean'); createRow(palettes.gold, 'pal-gold'); createRow(palettes.morD, 'pal-morandi-d'); createRow(palettes.summer, 'pal-summer'); createRow(palettes.macaron, 'pal-macaron'); createRow(palettes.wood, 'pal-wood'); createRow(palettes.morL, 'pal-morandi-l'); refreshDynamicColors(); document.getElementById('hex-input').addEventListener('input', e => { let v = e.target.value; if (/^#[0-9A-F]{6}$/i.test(v)) { document.getElementById('native-color').value = v; e.target.style.borderBottom = `3px solid ${v}`; } }); document.getElementById('native-color').addEventListener('input', e => { selectColor(e.target.value.toUpperCase()); }); }
        function refreshDynamicColors() { const createSwatches = (colors, id) => { let html = ''; colors.forEach(c => html += `<div class="color-swatch" style="background:${c};" onclick="selectColor('${c}')"></div>`); document.getElementById(id).innerHTML = html; }; createSwatches(configData.customColors.slice(0, 18), 'pal-custom'); createSwatches(configData.colorHistory.slice(0, 18), 'pal-history'); }
        function switchThemeTab(theme) { document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active')); document.querySelectorAll('.theme-view').forEach(el => el.classList.remove('active')); event.target.classList.add('active'); document.getElementById(`view-${theme}`).classList.add('active'); }
        function selectColor(hex) { let input = document.getElementById('hex-input'); let nColor = document.getElementById('native-color'); input.value = hex; input.style.borderBottom = `3px solid ${hex}`; nColor.value = hex; }
        function addCustomColor() { let hex = document.getElementById('hex-input').value.trim().toUpperCase(); if (/^#[0-9A-F]{6}$/i.test(hex)) { if (!configData.customColors.includes(hex)) { configData.customColors.unshift(hex); if(configData.customColors.length > 18) configData.customColors.pop(); debouncedSaveConfig(); refreshDynamicColors(); } } }
        function openColorModal(currentHex, cb) { colorCallback = cb; selectColor(currentHex || '#2A2A2A'); document.getElementById('color-modal').style.display = 'flex'; }
        function closeColorModal() { document.getElementById('color-modal').style.display = 'none'; }
        function applyColorModal() { let hex = document.getElementById('hex-input').value.trim().toUpperCase(); if (/^#[0-9A-F]{6}$/i.test(hex)) { configData.colorHistory = configData.colorHistory.filter(c => c !== hex); configData.colorHistory.unshift(hex); if(configData.colorHistory.length > 18) configData.colorHistory.pop(); debouncedSaveConfig(); refreshDynamicColors(); closeColorModal(); if(colorCallback) colorCallback(hex); } }
        
        let qCallback = null;
        function triggerExtBatchMenu(e) {
            e.preventDefault(); e.stopPropagation();
            const menu = document.getElementById('ext-batch-menu');
            menu.style.display = 'flex';
            setSafePosition(menu, e.clientX, e.clientY);
            renderSVGs(menu);
        }

        function addCommonExts(category) {
            document.getElementById('ext-batch-menu').style.display = 'none';
            const exts = {
                'text': ['txt', 'md', 'json', 'xml', 'csv', 'log', 'ini'],
                'image': ['jpg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico'],
                'audio': ['mp3', 'wav', 'flac', 'm4a', 'aac', 'ogg'],
                'video': ['mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm'],
                'document': ['doc', 'docx', 'pdf', 'xls', 'xlsx', 'ppt', 'pptx']
            }[category];
            if (!exts) return;
            
            let cs = currentCompState();
            if (!cs.customExts) cs.customExts = [];
            if (!cs.orderExt) cs.orderExt = [];
            
            exts.forEach(val => {
                if (!cs.customExts.includes(val)) {
                    cs.customExts.push(val);
                    cs.orderExt.push(val);
                }
            });
            saveCompState();
            renderCustomExts();
            showToast(t("toast_batch_add_ok"), "success");
        }
        
        function openQuickEdit(x, y, defVal, cb, placeholderHint = '') { 
            qCallback = cb; 
            const qe = document.getElementById('quick-edit');
            const qInput = document.getElementById('edit-input');
            qInput.value = defVal; 
            qInput.placeholder = placeholderHint || "Enter 确认 / Esc 取消"; // 新增占位符支持
            qe.style.display = 'block'; 
            setSafePosition(qe, x, y);
            setTimeout(() => { qInput.focus(); qInput.select(); }, 50); 
        }
        function getLighterColor(hex) { if (!hex || hex === 'transparent') return '#00bcd4'; let r = parseInt(hex.slice(1,3), 16), g = parseInt(hex.slice(3,5), 16), b = parseInt(hex.slice(5,7), 16); r = Math.min(255, r + 40); g = Math.min(255, g + 40); b = Math.min(255, b + 40); return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1); }
        function getContrastColor(hex) { if (!hex || hex === 'transparent') return ''; let c = hex.startsWith('#') ? hex.slice(1) : hex; if (c.length === 3) c = c.split('').map(x => x + x).join(''); let r = parseInt(c.slice(0, 2), 16), g = parseInt(c.slice(2, 4), 16), b = parseInt(c.slice(4, 6), 16); let yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000; return yiq >= 128 ? '#111111' : '#FFFFFF'; }

        function getLighterColor(hex) { if (!hex || hex === 'transparent') return '#00bcd4'; let r = parseInt(hex.slice(1,3), 16), g = parseInt(hex.slice(3,5), 16), b = parseInt(hex.slice(5,7), 16); r = Math.min(255, r + 40); g = Math.min(255, g + 40); b = Math.min(255, b + 40); return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1); }
        function getContrastColor(hex) { if (!hex || hex === 'transparent') return ''; let c = hex.startsWith('#') ? hex.slice(1) : hex; if (c.length === 3) c = c.split('').map(x => x + x).join(''); let r = parseInt(c.slice(0, 2), 16), g = parseInt(c.slice(2, 4), 16), b = parseInt(c.slice(4, 6), 16); let yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000; return yiq >= 128 ? '#111111' : '#FFFFFF'; }

        // --- 新增：智能主题颜色映射引擎 (HSL 亮度自适应翻转) ---
        function getMappedColor(hex, currentTheme) {
            if (!hex || hex === 'transparent' || !hex.startsWith('#')) return hex;
            let c = hex.slice(1);
            if (c.length === 3) c = c.split('').map(x => x + x).join('');
            if (c.length !== 6) return hex;

            // 1. Hex 转 RGB
            let r = parseInt(c.slice(0, 2), 16) / 255, g = parseInt(c.slice(2, 4), 16) / 255, b = parseInt(c.slice(4, 6), 16) / 255;
            let max = Math.max(r, g, b), min = Math.min(r, g, b);
            let h = 0, s = 0, l = (max + min) / 2;

            // 2. RGB 转 HSL
            if (max !== min) {
                let d = max - min;
                s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
                switch (max) {
                    case r: h = (g - b) / d + (g < b ? 6 : 0); break;
                    case g: h = (b - r) / d + 2; break;
                    case b: h = (r - g) / d + 4; break;
                }
                h /= 6;
            }

            // 3. 核心：根据主题进行亮度 (Lightness) 翻转
            let isDarkColor = l < 0.55; 
            if (currentTheme === 'light' && isDarkColor) {
                // 【调整明度】：把 0.85 降低为 0.70 或 0.75。数值越小，颜色越深、越厚重。
                l = 0.78 + (l * 0.1); 
                
                // 【调整饱和度】：加入这一行。乘以 1.2 表示把原颜色的饱和度放大 20%，让颜色更鲜艳不发灰。
                // (Math.min确保饱和度不会超过最大值1)
                s = Math.min(1, s * 1.2); 
            } else if (currentTheme === 'dark' && !isDarkColor) {
                // 如果在暗色主题下遇到亮色 -> 映射为安全的暗色区间 (0.15 ~ 0.3)
                l = 0.15 + ((1 - l) * 0.15);
            } else {
                return hex; // 颜色已经适配当前主题，直接放行
            }

            // 4. HSL 重新转回 Hex
            let hue2rgb = (p, q, t) => {
                if (t < 0) t += 1; if (t > 1) t -= 1;
                if (t < 1/6) return p + (q - p) * 6 * t;
                if (t < 1/2) return q;
                if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
                return p;
            };

            let q = l < 0.5 ? l * (1 + s) : l + s - l * s;
            let p = 2 * l - q;
            let rr = Math.round(hue2rgb(p, q, h + 1/3) * 255);
            let gg = Math.round(hue2rgb(p, q, h) * 255);
            let bb = Math.round(hue2rgb(p, q, h - 1/3) * 255);

            let toHex = x => { let hx = x.toString(16); return hx.length === 1 ? '0' + hx : hx; };
            return `#${toHex(rr)}${toHex(gg)}${toHex(bb)}`.toUpperCase();
        }
        
        // ==========================================
        // --- 标签全局检索系统 (增强版) ---
        // ==========================================
        let flattenedTagsCache = [];
        let currentSearchIndex = -1; // 用于键盘上下键选择

        // 构建缓存 (提取标签路径、别名)
        function buildTagCache() {
            flattenedTagsCache = [];
            let tree = currentTree();
            
            function traverse(node, currentPath, displayPath) {
                if (node._tags) {
                    node._tags.forEach(tRaw => {
                        let pt = parseTag(tRaw);
                        if (pt.name !== '?*' && pt.name !== '""') {
                            flattenedTagsCache.push({
                                raw: tRaw,
                                name: pt.name,
                                alias: pt.alias,
                                descs: pt.descs,
                                path: currentPath,
                                displayPath: displayPath ? `${displayPath} / ` : ""
                            });
                        }
                    });
                }
                for (let k in node) {
                    if (!k.startsWith('_')) {
                        let dn = (state.showAlias && node[k]._alias) ? node[k]._alias : sysT(k);
                        traverse(node[k], currentPath ? currentPath + '/' + k : k, displayPath ? `${displayPath} / ${dn}` : dn);
                    }
                }
            }
            if (tree["未分类"]) traverse({"未分类": tree["未分类"]}, "未分类", sysT("未分类"));
            for(let k in tree) { if(k !== "未分类" && !k.startsWith('_')) traverse(tree[k], k, sysT(k)); }
        }

        // 【记忆即刻生效修补】
        function toggleSearchMemory(isMem) {
            configData.searchMemory = isMem;
            if (isMem) {
                // 隔离记录：读取当前工作区并加上后缀
                let ws = configData.currentWs;
                configData['lastSearchQuery_' + ws] = document.getElementById('tag-search-input').value.trim().toLowerCase();
                let modeEl = document.querySelector('input[name="search_mode"]:checked');
                configData['lastSearchMode_' + ws] = modeEl ? modeEl.value : 'fuzzy';
            }
            debouncedSaveConfig();
        }

        function toggleSearchMemory(isMem) {
            configData.searchMemory = isMem;
            if (isMem) {
                // 【逻辑升级】隔离记录：不仅记录文字和模式，一并记录三大范围勾选状态
                let ws = configData.currentWs;
                configData['lastSearchQuery_' + ws] = document.getElementById('tag-search-input').value.trim().toLowerCase();
                let modeEl = document.querySelector('input[name="search_mode"]:checked');
                configData['lastSearchMode_' + ws] = modeEl ? modeEl.value : 'fuzzy';
                
                // 【找到这段并补充 InGroup】
                configData['lastSearchInGroup_' + ws] = document.getElementById('search-in-group').checked; // [新增]
                configData['lastSearchInTag_' + ws] = document.getElementById('search-in-tag').checked;
                configData['lastSearchInRemark_' + ws] = document.getElementById('search-in-remark').checked;
                configData['lastSearchInDesc_' + ws] = document.getElementById('search-in-desc').checked;
            }
            debouncedSaveConfig();
        }

        function openTagSearch(e) {
            e.stopPropagation();
            buildTagCache(); 
            const modal = document.getElementById('tag-search-modal');
            const input = document.getElementById('tag-search-input');
            const memToggle = document.getElementById('search-memory-toggle');
            
            modal.style.display = 'flex';
            setSafePosition(modal, e.clientX - 190, e.clientY + 20);
            
            // 【逻辑升级】恢复记忆设定（读取包含范围勾选的状态）
            memToggle.checked = !!configData.searchMemory;
            if (configData.searchMemory) {
                let ws = configData.currentWs;
                let savedQuery = configData['lastSearchQuery_' + ws];
                let savedMode = configData['lastSearchMode_' + ws] || 'fuzzy';
                
                // 【找到这段并补充 sGroup】
                let sGroup = configData['lastSearchInGroup_' + ws]; // [新增]
                let sTag = configData['lastSearchInTag_' + ws];
                let sRem = configData['lastSearchInRemark_' + ws];
                let sDesc = configData['lastSearchInDesc_' + ws];
                
                // 只要不是明确保存过 false，默认就是勾选状态 (true)
                document.getElementById('search-in-group').checked = sGroup !== false; // [新增]
                document.getElementById('search-in-tag').checked = sTag !== false; 
                document.getElementById('search-in-remark').checked = sRem !== false;
                document.getElementById('search-in-desc').checked = sDesc !== false;
                
                if (savedQuery) {
                    input.value = savedQuery;
                    let rb = document.querySelector(`input[name="search_mode"][value="${savedMode}"]`);
                    if (rb) rb.checked = true;
                } else {
                    input.value = '';
                }
            } else {
                input.value = '';
                document.getElementById('search-in-tag').checked = true;
                document.getElementById('search-in-remark').checked = true;
                document.getElementById('search-in-desc').checked = true;
            }
            
            currentSearchIndex = -1; // 重置选中项
            doTagSearch(); // 立即触发一次渲染
            
            setTimeout(() => { 
                input.focus(); 
                input.select(); 
            }, 50);
        }

        function closeTagSearch() {
            document.getElementById('tag-search-modal').style.display = 'none';
        }

        // 监听面板内的点击，防止冒泡导致误关
        document.getElementById('tag-search-modal').addEventListener('mousedown', function(e) {
            e.stopPropagation();
        });

        // 修改原有的全局点击拦截规则：点击其他地方关闭搜索框
        document.addEventListener('mousedown', e => {
            const tagSearchModal = document.getElementById('tag-search-modal');
            if (tagSearchModal && tagSearchModal.style.display === 'flex' && !tagSearchModal.contains(e.target) && !e.target.closest('button[data-i18n-title="search_tags"]')) {
                tagSearchModal.style.display = 'none';
            }
        });

        // 【智能高亮核心算法】
        function highlightText(text, query, mode, highlightClass) {
            if (!query) return _h(text);
            if (mode === 'exact') {
                // 【终极降维方案】：完全不写任何带反斜杠的正则字面量代码！
                // 动态生成反斜杠字符 (ASCII 92)，利用字符串切割拼接，完美绕过 Python 审查
                let bs = String.fromCharCode(92); 
                let specialChars = ['.', '*', '+', '?', '^', '$', '{', '}', '(', ')', '|', '[', ']', bs];
                let escapedQuery = query;
                for (let i = 0; i < specialChars.length; i++) {
                    escapedQuery = escapedQuery.split(specialChars[i]).join(bs + specialChars[i]);
                }
                const regex = new RegExp(`(${escapedQuery})`, 'gi');
                return _h(text).replace(regex, `<span class="${highlightClass}">$1</span>`);
            } else {
                // 模糊匹配字符高亮
                let result = '';
                let qIdx = 0;
                let qLower = query.toLowerCase();
                for (let i = 0; i < text.length; i++) {
                    let char = text[i];
                    if (qIdx < qLower.length && char.toLowerCase() === qLower[qIdx]) {
                        result += `<span class="${highlightClass}">${_h(char)}</span>`;
                        qIdx++;
                    } else {
                        result += _h(char);
                    }
                }
                return result;
            }
        }

        function doTagSearch() {
            const query = document.getElementById('tag-search-input').value.trim().toLowerCase();
            const mode = document.querySelector('input[name="search_mode"]:checked').value;
            const resultsContainer = document.getElementById('tag-search-results');
            
            // 【补充 inGroup 变量】
            let inGroup = document.getElementById('search-in-group').checked;
            let inTag = document.getElementById('search-in-tag').checked;
            let inRemark = document.getElementById('search-in-remark').checked;
            let inDesc = document.getElementById('search-in-desc').checked;
            
            // 实时储存勾选状态
            if (configData.searchMemory) {
                let ws = configData.currentWs;
                configData['lastSearchQuery_' + ws] = query;
                configData['lastSearchMode_' + ws] = mode;
                configData['lastSearchInTag_' + ws] = inTag;
                configData['lastSearchInRemark_' + ws] = inRemark;
                configData['lastSearchInDesc_' + ws] = inDesc;
                debouncedSaveConfig();
            }

            if (!query) {
                resultsContainer.innerHTML = `<div style="padding: 10px; color: var(--text-muted); font-size: 12px; text-align: center;">${t('search_no_input')}</div>`;
                return;
            }

            // --- 核心：智能打分引擎 ---
            let scoredResults = [];
            for (let i = 0; i < flattenedTagsCache.length; i++) {
                let item = flattenedTagsCache[i];
                let score = 0;
                let isMatch = false;

                // 【补充提取路径名 gLow】
                let gLow = item.displayPath ? item.displayPath.toLowerCase() : "";
                let nLow = item.name.toLowerCase();
                let aLow = item.alias ? item.alias.toLowerCase() : "";

                // 智能打分器：判断匹配并计算权重得分
                const checkMatch = (text, weight) => {
                    if (!text) return 0;
                    if (mode === 'exact') {
                        let idx = text.indexOf(query);
                        if (idx > -1) {
                            isMatch = true;
                            if (text === query) return weight * 100;         // 完全一致：绝对最高分
                            if (idx === 0) return weight * 10;               // 开头匹配：次高分
                            return weight + (50 / (text.length || 1));       // 包含匹配：越短分越高
                        }
                    } else {
                        // 模糊匹配逻辑
                        let p = 0, q = 0, firstMatchIdx = -1;
                        let continuous = 0, maxContinuous = 0;
                        while (p < text.length && q < query.length) {
                            if (text[p] === query[q]) {
                                if (firstMatchIdx === -1) firstMatchIdx = p;
                                continuous++;
                                maxContinuous = Math.max(maxContinuous, continuous);
                                q++;
                            } else {
                                continuous = 0;
                            }
                            p++;
                        }
                        if (q === query.length) {
                            isMatch = true;
                            if (text === query) return weight * 100;
                            if (firstMatchIdx === 0) return weight * 10;
                            // 模糊匹配加分：连字越多、总长度越短，分越高
                            return weight + maxContinuous + (50 / (text.length || 1));
                        }
                    }
                    return 0;
                };

                // 分别在勾选的维度中计算得分 (基础权重：标签名100，备注50，描述10)
                // 【在调用 checkMatch 的地方，增加对 gLow 的计算】
                // 分组名的权重设为 30（次于备注，高于描述）
                if (inGroup) score += checkMatch(gLow, 30);
                if (inTag) score += checkMatch(nLow, 100);
                if (inRemark && item.alias) score += checkMatch(aLow, 50);
                if (inDesc && item.descs && item.descs.length > 0) {
                    let bestDescScore = 0;
                    for (let d of item.descs) {
                        let dScore = checkMatch(d.toLowerCase(), 10);
                        if (dScore > bestDescScore) bestDescScore = dScore;
                    }
                    score += bestDescScore;
                }

                if (isMatch) {
                    scoredResults.push({ item: item, score: score, index: i });
                }
            }

            // 根据得分降序排列，同分则按原本在树状图里的顺序排列
            scoredResults.sort((a, b) => {
                if (b.score !== a.score) return b.score - a.score;
                return a.index - b.index;
            });

            // 提取排序后的结果
            let results = scoredResults.map(sr => sr.item);

            const MAX_RESULTS = 100;
            let displayResults = results.slice(0, MAX_RESULTS);

            if (displayResults.length === 0) {
                resultsContainer.innerHTML = `<div style="padding: 10px; color: var(--text-muted); font-size: 12px; text-align: center;">${t('search_no_match')}</div>`;
                return;
            }

            // --- 渲染逻辑 ---
            let html = '';
            displayResults.forEach((item, idx) => {
                // 【将原来死板的 _h(item.displayPath) 替换为支持高亮的 highlightText】
                // 这里我为你借用了 hl-desc (蓝色) 作为路径的高亮色，清爽且有辨识度
                let pathHtml = highlightText(item.displayPath, inGroup ? query : "", mode, 'hl-desc'); 
                
                let nameHtml = highlightText(item.name, inTag ? query : "", mode, 'hl-match');
                let aliasHtml = item.alias ? `<span style="opacity: 0.7; margin-left: 4px; font-size: 12px;">(${highlightText(item.alias, inRemark ? query : "", mode, 'hl-remark')})</span>` : '';
                
                let descMatchHtml = '';
                if (inDesc && query && item.descs && item.descs.length > 0) {
                    let qLow = query.toLowerCase();
                    let matchedD = item.descs.find(d => {
                        let tLow = d.toLowerCase();
                        if (mode === 'exact') return tLow.includes(qLow);
                        
                        let p = 0, q = 0;
                        while (p < tLow.length && q < qLow.length) {
                            if (tLow[p] === qLow[q]) q++;
                            p++;
                        }
                        return q === qLow.length;
                    });
                    
                    if (matchedD) {
                        descMatchHtml = `<div style="font-size: 11px; color: var(--text-muted); margin-top: 4px; background: rgba(128,128,128,0.1); padding: 3px 6px; border-radius: 4px; display: inline-block;">[${t('match_desc')}] ${highlightText(matchedD, query, mode, 'hl-desc')}</div>`;
                    }
                }

                let tooltipHtml = '';
                if (item.alias || (item.descs && item.descs.length > 0)) {
                    let sTitle = state.showAlias ? item.name : item.alias;
                    let sTitleColor = state.showAlias ? 'var(--hl-tag)' : 'var(--hl-remark)';
                    
                    if (sTitle) tooltipHtml += `<div><strong style="color:${sTitleColor};">${_h(sTitle)}</strong></div>`;
                    if (item.descs && item.descs.length > 0) {
                        if (sTitle) tooltipHtml += `<div style="border-top:1px solid var(--border-color); margin: 6px 0;"></div>`;
                        tooltipHtml += `<div style="color:var(--text-muted); line-height:1.4;">` + item.descs.map(d => _h(d)).join('<div style="border-top:1px dashed var(--border-color); margin: 4px 0; opacity: 0.5;"></div>') + `</div>`;
                    }
                }
                let hoverAttr = tooltipHtml ? `onmouseenter="showTooltip(event, '${_e(tooltipHtml)}')" onmousemove="moveTooltip(event)" onmouseleave="hideTooltip()"` : '';
                
                html += `
                <div class="search-result-item" data-idx="${idx}" onclick="activateSearchedTag('${item.path}', '${item.name}')" ${hoverAttr}>
                    <div class="search-path-col" title="${_e(item.displayPath)}">${pathHtml}</div>
                    <div class="search-tag-col" style="display: flex; flex-direction: column; justify-content: center;">
                        <div>${nameHtml} ${aliasHtml}</div>
                        ${descMatchHtml}
                    </div>
                </div>`;
            });
            
            if (results.length > MAX_RESULTS) {
                html += `<div style="padding: 8px; color: var(--primary); font-size: 11px; text-align: center; border-top: 1px dashed var(--border-color);">${t('search_limit').replace('{n}', MAX_RESULTS)}</div>`;
            }

            resultsContainer.innerHTML = html;
            currentSearchIndex = -1; 
        }

        // --- 键盘劫持与导航逻辑 ---
        document.getElementById('tag-search-input').addEventListener('keydown', function(e) {
            const results = document.querySelectorAll('.search-result-item');
            if (e.key === 'Escape') {
                e.preventDefault();
                closeTagSearch();
                return;
            }
            if (results.length === 0) return;

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                currentSearchIndex = (currentSearchIndex + 1) % results.length;
                updateSearchSelection(results);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                currentSearchIndex = (currentSearchIndex - 1 + results.length) % results.length;
                updateSearchSelection(results);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (currentSearchIndex >= 0 && currentSearchIndex < results.length) {
                    results[currentSearchIndex].click();
                } else if (results.length > 0) {
                    results[0].click(); // 没主动选择时，默认触发第一条
                }
            }
        });

        function updateSearchSelection(resultsList) {
            resultsList.forEach((el, idx) => {
                if (idx === currentSearchIndex) {
                    el.classList.add('selected');
                    // 确保选中项滚动到视野内
                    el.scrollIntoView({ block: 'nearest' });
                } else {
                    el.classList.remove('selected');
                }
            });
        }

        function activateSearchedTag(path, tag) {
            let key = `${path}|${tag}`;
            
            state.tagStates[key] = 1;
            if (!clickOrder.includes(key)) clickOrder.push(key);

            let parts = path.split('/');
            let curP = "";
            parts.forEach(p => { 
                curP += (curP ? "/" : "") + p; 
                state.expandedGroups[curP] = true; 
            });

            // 【Bug修复】：彻底解绑，只开启“仅显示激活组”，关闭“仅展开激活组”
            state.activeOnly = false;
            document.getElementById('btn-active').classList.remove('active-green');
            
            state.filterOnly = true; 
            document.getElementById('btn-filter').classList.add('active-green');

            saveCompState();
            render();
            refreshCompUI();
        }
        
        // ======= 版本更新与链接逻辑 =======
        const CURRENT_VERSION = '/*__INIT_VERSION__*/';
        
        function openGithub() {
            pywebview.api.open_url('https://github.com/C21H21NO2S/XYplorerTagHelper');
        }

        // 版本号比对算法 (支持 1.2.2 与 1.2.10 的正确比对)
        function cmpVer(v1, v2) {
            let p1 = v1.split('.').map(Number), p2 = v2.split('.').map(Number);
            for(let i = 0; i < Math.max(p1.length, p2.length); i++) {
                let n1 = p1[i] || 0, n2 = p2[i] || 0;
                if(n1 > n2) return 1;
                if(n1 < n2) return -1;
            }
            return 0;
        }

        async function checkUpdate() {
            let btn = document.querySelector('button[onclick="checkUpdate()"]');
            // 核心修复：只获取带有文字的 span，绝对不触碰前面的 SVG 图标
            let textSpan = btn.querySelector('span[data-i18n="check_update"]');
            
            // 保存原文字
            let originalText = textSpan.innerText;
            // 替换为本地化的“检查中...”
            textSpan.innerText = t('checking_update');
            btn.disabled = true;
            
            try {
                let res = await fetch('https://api.github.com/repos/C21H21NO2S/XYplorerTagHelper/releases/latest');
                if (!res.ok) throw new Error('Network response was not ok');
                let data = await res.json();
                
                if (data.tag_name) {
                    let latest = data.tag_name.replace('v', ''); // 将 'v1.2.3' 转为 '1.2.3'
                    
                    if (cmpVer(latest, CURRENT_VERSION) > 0) {
                        // 注意这里结尾加了 'update' 标志
                        showConfirmModal(`${t('update_found')} (v${latest})\n\n${t('go_to_download')}`, () => {
                            pywebview.api.open_url('https://github.com/C21H21NO2S/XYplorerTagHelper/releases/latest');
                        }, 'update');
                    } else {
                        showToast(t('is_latest'), 'success');
                    }
                }
            } catch (err) {
                showToast(t('update_fail'), 'error');
                sysLog(t("log_update_err") + err.message, "ERROR");
            } finally {
                // 恢复原文字与按钮状态，无需重新调用 renderSVGs
                textSpan.innerText = originalText;
                btn.disabled = false;
            }
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    initial_data = json.dumps(load_tags(), ensure_ascii=False)
    
    cfg = load_config()
    initial_config = json.dumps(cfg, ensure_ascii=False)
    
    api = Api()
    
    w_width = cfg.get('win_width', 850)
    w_height = cfg.get('win_height', 700)
    w_x = cfg.get('win_x', None)
    w_y = cfg.get('win_y', None)
    
    if not isinstance(w_x, int) or not isinstance(w_y, int) or w_x < -10000 or w_y < -10000:
        w_x, w_y = None, None
        
    theme = cfg.get('theme', 'dark')
    startup_bg_color = '#1A1B1E' if theme == 'dark' else '#F4F5F7'
    
    # === 核心修复：自动提取标题中的版本号并注入到前端 ===
    curr_ver = WINDOW_TITLE.split(' ')[-1]
    html_str = html_template.replace("/*__INIT_DATA__*/{}", initial_data).replace("/*__INIT_CONFIG__*/{}", initial_config).replace("/*__INIT_VERSION__*/", curr_ver)
    
    window = webview.create_window(
        WINDOW_TITLE, 
        html=html_str, # 使用替换后的 html_str
        js_api=api, 
        width=w_width, 
        height=w_height,
        x=w_x,
        y=w_y,
        min_size=(450, 500),
        background_color=startup_bg_color
    )
    
    def on_shown():
        try:
            hex_color = '#F4F5F7' if theme == 'light' else '#1A1B1E'
            api.change_titlebar_theme(hex_color, theme == 'dark')
        except:
            pass

    window.events.shown += on_shown

    def on_closing():
        try:
            curr_cfg = load_config()
            saved = False
            
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
                if not hwnd:
                    hwnd = ctypes.windll.user32.GetForegroundWindow()
                if hwnd:
                    try:
                        dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
                        if dpi == 0: dpi = 96
                    except AttributeError:
                        dpi = 96
                    scale = dpi / 96.0

                    rect = wintypes.RECT()
                    # 【高维修复】：放弃 DwmGetWindowAttribute(..., 9)，改用标准的 GetWindowRect！
                    # DWM 属性 9 获取的是“不包含不可见调整边框”的视觉大小，而 create_window 接收的是包含边框的总大小。
                    # 反复把剥除边框的视觉尺寸喂给生成引擎，就会导致窗口不断被“吃掉”边框厚度而越来越小。
                    # GetWindowRect 获取的绝对物理边界，完美对称了窗口创建所需的尺寸。
                    if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                        w = int((rect.right - rect.left) / scale)
                        h = int((rect.bottom - rect.top) / scale)
                        x = int(rect.left / scale)
                        y = int(rect.top / scale)
                        
                        if w > 0 and h > 0 and x > -10000 and y > -10000:
                            curr_cfg['win_width'] = w
                            curr_cfg['win_height'] = h
                            curr_cfg['win_x'] = x
                            curr_cfg['win_y'] = y
                            saved = True

            if not saved:
                if window.width and window.height:
                    curr_cfg['win_width'] = window.width
                    curr_cfg['win_height'] = window.height
                if window.x is not None and window.y is not None and window.x > -10000 and window.y > -10000:
                    curr_cfg['win_x'] = window.x
                    curr_cfg['win_y'] = window.y
                    
            save_config(curr_cfg)
        except Exception as e:
            write_log(f"Failed to save window state: {e}", "ERROR")
        
    window.events.closing += on_closing

    webview.start()
