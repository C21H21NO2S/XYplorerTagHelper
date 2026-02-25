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

# ==========================================
# 1. 基础配置与本地数据管理 (兼容 PyInstaller 打包)
# ==========================================
WINDOW_TITLE = 'XYplorerTagHelper 1.2.2'

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
        "theme": "dark", "lang": "zh-CN"
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

    def log_message(self, msg, level="INFO"):
        write_log(msg, level)
        print(f"[{level}] {msg}")

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
                self.log_message(f"窗口聚焦失败: {e}", "ERROR")
        threading.Thread(target=_focus, daemon=True).start()

    def change_titlebar_theme(self, color_hex, is_dark):
        def _apply():
            time.sleep(0.2) 
            try:
                if os.name == 'nt':
                    import ctypes
                    
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
                        attr_dark = 20 if build >= 22000 else 19
                        val_dark = ctypes.c_int(1 if is_dark else 0)
                        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr_dark, ctypes.byref(val_dark), ctypes.sizeof(val_dark))
                        
                        if build >= 22000:
                            hex_str = color_hex.lstrip('#')
                            r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
                            color_ref = ctypes.c_int(r | (g << 8) | (b << 16))
                            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color_ref), ctypes.sizeof(color_ref))
                            
                        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
            except Exception as e:
                self.log_message(f"更改原生标题栏主题失败: {e}", "ERROR")
                
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
                self.log_message(f"无法打开输出目录: {e}", "ERROR")

    def get_data(self): return load_tags()
    def save_data(self, data): return save_tags(data)
    def get_config(self): return load_config()
    def save_config(self, data): return save_config(data)

    def export_data(self):
        try:
            now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"XYplorerTagHelper-数据_{now_str}.json"
            save_path = os.path.join(OUTPUT_DIR, filename)
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self.get_data(), f, ensure_ascii=False, indent=4)
            self.log_message(f"成功导出工作区数据至: {save_path}", "INFO")
            self._open_output_folder()
            return {"success": True, "msg": "数据导出成功"}
        except Exception as e:
            self.log_message(f"导出数据异常: {e}", "ERROR")
            return {"success": False, "msg": str(e)}

    def export_config(self):
        try:
            now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"XYplorerTagHelper-软件设置_{now_str}.json"
            save_path = os.path.join(OUTPUT_DIR, filename)
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self.get_config(), f, ensure_ascii=False, indent=4)
            self.log_message(f"成功导出软件设置至: {save_path}", "INFO")
            self._open_output_folder()
            return {"success": True, "msg": "设置导出成功"}
        except Exception as e:
            self.log_message(f"导出设置异常: {e}", "ERROR")
            return {"success": False, "msg": str(e)}

    def execute_search(self, path, syntax, xy_path):
        path = path.strip() or "*"
        syntax = syntax.strip()
        
        # 修复 Bug: 当仅有 /types= 等纯 switch 语法时，路径后只用 ?
        if syntax.startswith("/"):
            feed_script = f"::goto '{path}?{syntax}';"
        elif syntax:
            feed_script = f"::goto '{path}?:{syntax}';"
        else:
            feed_script = f"::goto '{path}?';"
            
        exe_path = self._normalize_xy_path(xy_path)
        self.log_message(f"执行搜索命令: {exe_path} /feed=\"{feed_script}\"")
        try:
            if os.path.exists(exe_path):
                subprocess.Popen(f'"{exe_path}" /feed="{feed_script}"', shell=True)
            else:
                self.log_message(f"执行失败: 未找到 XYplorer.exe", "ERROR")
        except Exception as e:
            self.log_message(f"执行搜索异常: {e}", "ERROR")

    def execute_script(self, script, xy_path):
        script = script.strip()
        exe_path = self._normalize_xy_path(xy_path)
        self.log_message(f"执行脚本命令: {exe_path} /feed=\"{script}\"")
        try:
            if os.path.exists(exe_path):
                subprocess.Popen(f'"{exe_path}" /feed="{script}"', shell=True)
            else:
                self.log_message(f"执行失败: 未找到 XYplorer.exe", "ERROR")
        except Exception as e:
            self.log_message(f"执行脚本异常: {e}", "ERROR")

    def read_clipboard_safe(self):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW 
            result = subprocess.check_output(['powershell', '-NoProfile', '-command', 'Get-Clipboard'], startupinfo=startupinfo, text=True, timeout=3)
            return result.strip()
        except Exception as e:
            self.log_message(f"安全读取剪贴板异常: {e}", "ERROR")
            return ""

    def update_xy_labels(self, xy_path):
        try:
            exe_path = self._normalize_xy_path(xy_path)
            if not exe_path or not os.path.exists(exe_path):
                return {"success": False, "msg": "未找到 XYplorer.exe"}
            data_dir = os.path.join(os.path.dirname(exe_path), "Data")
            tag_file = os.path.join(data_dir, "tag.dat")
            if not os.path.exists(tag_file):
                return {"success": False, "msg": f"找不到数据文件"}
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
            else: return {"success": False, "msg": "未在 tag.dat 中找到 Labels 配置"}
        except Exception as e:
            return {"success": False, "msg": str(e)}

    def open_manual(self, lang):
        # 根据前端传来的语言标识，寻找对应的 html
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
                os.startfile(filepath) # 自动调用系统默认浏览器打开
                return {"success": True}
            else:
                self.log_message(f"找不到说明文档: {filepath}", "ERROR")
                return {"success": False}
        except Exception as e:
            self.log_message(f"打开文档失败: {e}", "ERROR")
            return {"success": False}

    def open_url(self, url):
            try:
                webbrowser.open(url)
                return {"success": True}
            except Exception as e:
                self.log_message(f"打开链接失败: {e}", "ERROR")
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
        }
        
        body { margin: 0; padding: 0; background: var(--bg-main); color: var(--text-main); font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 13px; height: 100vh; box-sizing: border-box; display: flex; flex-direction: column; overflow: hidden; user-select: none; }
        
        /* Modern Scrollbar */
        ::-webkit-scrollbar { width: 6px; height: 6px; display: none; }
        .tree-container::-webkit-scrollbar, .comp-body::-webkit-scrollbar, textarea::-webkit-scrollbar, .ws-tabs-scroll::-webkit-scrollbar, .global-dropdown::-webkit-scrollbar { display: block; }
        ::-webkit-scrollbar-track { background: transparent; border-radius: 10px; }
        ::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

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
        .comp-btn { background: var(--bg-btn); color: var(--text-main); border: 1px solid var(--border-color); padding: 4px 10px; border-radius: var(--radius); font-size: 12px; font-weight: bold; position: relative; }
        .comp-btn:hover { background: var(--bg-btn-hover); color: var(--primary); border-color: var(--primary); }
        .comp-btn.s1 { background: var(--green); color: #fff; border-color: transparent; } 
        .comp-btn.s2 { background: var(--red); color: #fff; border-color: transparent; } 
        
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
        .group-title { font-weight: bold; font-size: 13px; pointer-events: none;}
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

        /* 标签按钮紧凑化 */
        .tag-btn { position: relative; height: 25px; padding: 0 8px; background: var(--bg-btn); color: var(--btn-text, var(--text-main)); border: 1px solid var(--border-color); border-radius: var(--radius); font-size: 12px; font-weight: bold; display: inline-flex; align-items: center; justify-content: center; box-sizing: border-box; white-space: nowrap; transition: 0.1s; }
        .tag-btn:hover { background: var(--bg-btn-hover); border-color: var(--primary); color: var(--primary); }
        .tag-btn.s1 { background: var(--blue); color: #fff; border-color: transparent; } 
        .tag-btn.s2 { background: var(--red); color: #fff; border-color: transparent; } 
        .tag-btn.s3 { background: var(--green); color: #fff; border-color: transparent; } 
        
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
    </style>
</head>
<body>

    <div id="app-loader">L O A D I N G ...</div>

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
                <div class="comp-tab active" onclick="event.stopPropagation(); switchCompTab('type')" data-i18n="tab_type">类型</div>
                <div class="comp-tab" onclick="event.stopPropagation(); switchCompTab('path')" data-i18n="tab_path">路径</div>
                <div class="comp-tab" onclick="event.stopPropagation(); switchCompTab('name')" data-i18n="tab_name">文件名</div>
                <div class="comp-tab" onclick="event.stopPropagation(); switchCompTab('remark')" data-i18n="tab_remark">备注</div>
                <div class="comp-tab" onclick="event.stopPropagation(); switchCompTab('label')" data-i18n="tab_label">标注</div>
                <div class="comp-tab" onclick="event.stopPropagation(); switchCompTab('rating')" data-i18n="tab_rating">评分</div>
                <div class="comp-tab" onclick="event.stopPropagation(); switchCompTab('size')" data-i18n="tab_size">大小/日期</div>
                <div style="flex:1;"></div>
                <button class="tool-btn" data-i18n-title="clear_filter" onclick="event.stopPropagation(); clearCompFilters()" v-html="clear"></button>
                <button class="tool-btn" id="comp-collapse-btn" onclick="event.stopPropagation(); toggleCompModule()" v-html="arrowDown"></button>
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
            <span style="font-size: 14px; font-weight: bold; color: var(--primary);" data-i18n="tag_group">🏷️ 标签组</span>
            <div style="flex: 1;"></div>
            <button class="tool-btn" data-i18n-title="clear_tree" onclick="clearAll()" v-html="clear"></button>
            <button class="tool-btn" id="btn-toggle" data-i18n-title="toggle_all" onclick="toggleAll()" v-html="expand"></button>
            <button class="tool-btn" id="btn-active" data-i18n-title="expand_active" onclick="toggleTool('activeOnly')"><div class="icon-solid-circle"></div></button>
            <button class="tool-btn" id="btn-filter" data-i18n-title="show_active" onclick="toggleTool('filterOnly')"><div class="icon-outline-circle"></div></button>
            <button class="tool-btn" id="btn-edit" data-i18n-title="edit_mode" onclick="toggleTool('editMode')" v-html="edit"></button>
            <button class="tool-btn btn-plus-icon" data-i18n-title="add_root" onclick="addRootGroup(event)" oncontextmenu="triggerBatchAddMenu(event, 'root')" v-html="add"></button>
        </div>

        <div class="tree-container" id="tree"></div>
    </div>

    <div id="global-hist-dropdown" class="global-dropdown"></div>

    <div id="ctx-menu">
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
        <div class="menu-item" onclick="execActionBtnColor()"><span class="menu-icon" v-html="palette"></span><span class="menu-text" data-i18n="edit_bg">修改背景颜色</span></div>
        <div class="menu-item" onclick="execActionBtnColorReset()"><span class="menu-icon" v-html="refresh"></span><span class="menu-text" data-i18n="reset_color">恢复默认颜色</span></div>
    </div>

    <div id="batch-add-menu">
        <div class="menu-item" onclick="executeBatchAddMenu()"><span class="menu-icon" id="batch-title-icon" v-html="add"></span><span class="menu-text" id="batch-title-text" data-i18n="batch_add">批量新建</span></div>
    </div>
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

    <div id="confirm-modal" class="modal-overlay">
        <div class="modal-content" style="width: 320px;">
            <h4 style="margin:0 0 10px 0; color:var(--red); font-size:15px; display:flex; gap:8px; align-items:center;">
                <span v-html="delete"></span><span data-i18n="confirm_del_title">确认删除</span>
            </h4>
            <div id="confirm-msg" style="font-size:13px; color:var(--text-main); margin-bottom:15px; line-height: 1.5; word-break: break-all;"></div>
            <div style="display:flex; justify-content:flex-end; gap:8px;">
                <button class="settings-btn" style="width:auto; padding:6px 16px;" onclick="closeConfirmModal()" data-i18n="cancel">取消</button>
                <button class="action-btn" style="width:auto; padding:6px 16px; border:none; background:var(--red); color:white;" onclick="executeConfirm()" data-i18n="delete">删除</button>
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
                    <select id="cfg-theme" style="width:100%; box-sizing:border-box;" onchange="applyTheme(this.value, true)">
                        <option value="dark" data-i18n="dark_theme">暗黑 (Dark)</option>
                        <option value="light" data-i18n="light_theme">浅色 (Light)</option>
                    </select>
                </div>
                <div style="flex:1;">
                    <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;" data-i18n="ui_lang">界面语言:</div>
                    <select id="cfg-lang" style="width:100%; box-sizing:border-box;" onchange="applyLang(this.value)">
                        <option value="zh-CN">简体中文</option>
                        <option value="zh-TW">繁體中文</option>
                        <option value="en">English</option>
                    </select>
                </div>
            </div>

            <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;" data-i18n="xy_path_hint">XYplorer 路径 (支持填写exe或纯文件夹路径):</div>
            <input type="text" id="cfg-xy-path" placeholder="E:\\XYplorer" style="width:100%; margin-bottom:20px; box-sizing:border-box;">
            
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
            delete: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`,
            arrowRight: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>`,
            arrowDown: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>`,
            palette: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="13.5" cy="6.5" r=".5"></circle><circle cx="17.5" cy="10.5" r=".5"></circle><circle cx="8.5" cy="7.5" r=".5"></circle><circle cx="6.5" cy="12.5" r=".5"></circle><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10c1.38 0 2.5-1.12 2.5-2.5 0-.53-.21-1.04-.59-1.41-.37-.38-.59-.89-.59-1.43 0-1.12 1.12-2.04 2.5-2.04h1.61c2.8 0 5.07-2.27 5.07-5.07C22 7.03 17.52 2 12 2z"></path></svg>`,
            move: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>`,
            copy: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`,
            expand: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>`,
            minimize: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 14 10 14 10 20"></polyline><polyline points="20 10 14 10 14 4"></polyline><line x1="14" y1="10" x2="21" y2="3"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>`,
            check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
            refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"></polyline><polyline points="23 20 23 14 17 14"></polyline><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"></path></svg>`
        };
        
        const I18N = {
            'zh-CN': {
                '默认工作区': '默认工作区', '未分类': '未分类', '项目状态': '项目状态', 
                '重要': '重要', '紧急': '紧急', '待办': '待办', '搁置': '搁置', '完成': '完成',
                '?*': '含标签', '""': '无标签',
                
                'checking_update': '检查中...',
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
                'tag_group': '🏷️ 标签组',
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
                'tag_group': '🏷️ 標籤群組',
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
                'tag_group': '🏷️ Tags Group',
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

        let state = { editMode: false, allExpanded: true, activeOnly: false, filterOnly: false, tagStates: {}, expandedGroups: {}, isPinned: false };
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
                if (extM && extM.style.display === 'flex' && !extM.contains(e.target)) extM.style.display = 'none';
                
                document.querySelectorAll('.global-dropdown').forEach(el => { 
                    if (el.style.display === 'flex' && !el.contains(e.target) && !e.target.closest('#btn-ws-dropdown') && !e.target.classList.contains('hist-toggle') && !e.target.parentElement.classList.contains('hist-toggle')) 
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
            try { pywebview.api.change_titlebar_theme(hex, theme === 'dark'); } catch(e) {}
        }

        function applyLang(lang) {
            configData.lang = lang;
            updateI18n();
            renderWsBar();
            initCompModule();
            render();
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
                    saveDataAndRenderAll();
                    sysLog("成功导入工作区数据", "INFO");
                    showToast(t("toast_import_data_ok"), "success");
                } catch(err) { sysLog("导入工作区数据失败: 解析错误", "ERROR"); showToast(t("toast_import_error"), "error"); }
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
                    sysLog("成功导入软件设置并重启", "INFO");
                } catch(err) { sysLog("导入软件设置失败: 解析错误", "ERROR"); showToast(t("toast_import_error"), "error");}
            };
            reader.readAsText(file);
            e.target.value = '';
        }

        function renderActionBtnColors() {
            if(!configData.actionBtnColors) return;
            ['search','add','read','clear'].forEach(id => {
                let color = configData.actionBtnColors[id];
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
                sysLog("功能按钮颜色已更新", "INFO");
            });
        }
        
        function execActionBtnColorReset() {
            document.getElementById('action-btn-ctx-menu').style.display = 'none';
            if (!actionBtnTarget || !configData.actionBtnColors) return;
            let id = actionBtnTarget;
            delete configData.actionBtnColors[id];
            debouncedSaveConfig();
            renderActionBtnColors();
            sysLog("功能按钮颜色已恢复默认", "INFO");
        }

        function initResizeObserver() {
            const synWrap = document.getElementById('syntax-wrapper');
            const compMod = document.getElementById('comp-module');
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
                    }
                }
                if (changed) {
                    clearTimeout(resizeTimer);
                    resizeTimer = setTimeout(() => { debouncedSaveConfig() }, 500);
                }
            });
            ro.observe(synWrap);
            ro.observe(compMod);
        }

        function initExpandedState(node, path) { for (let k in node) { if (!k.startsWith('_')) { let cur = path ? path + '/' + k : k; if (state.expandedGroups[cur] === undefined) state.expandedGroups[cur] = true; initExpandedState(node[k], cur); } } }
        
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
        }
        function closeSettings() { document.getElementById('settings-modal').style.display = 'none'; }
        function saveSettings() { 
            configData.xyPath = document.getElementById('cfg-xy-path').value.trim(); 
            applyTheme(document.getElementById('cfg-theme').value, true);
            applyLang(document.getElementById('cfg-lang').value);
            debouncedSaveConfig(); 
            closeSettings(); 
            showToast(t("toast_save_ok"), "success");
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
        
        function onCompTypeClick(e, tName) { 
            if (isDragAction(e)) return; 
            let now = Date.now(); if (now - (lastClickTime[`type_${tName}`] || 0) < 150) return; lastClickTime[`type_${tName}`] = now;
            let cs = currentCompState(); let cur = cs.types[tName] || 0; 
            
            if (e.button === 0) {
                let nextState = cur === 1 ? 0 : 1;
                if (nextState === 1) {
                    for (let k in cs.types) {
                        if (cs.types[k] === 2) delete cs.types[k];
                    }
                }
                cs.types[tName] = nextState;
            } else if (e.button === 2) {
                let nextState = cur === 2 ? 0 : 2;
                if (nextState === 2) {
                    cs.types = {};
                }
                cs.types[tName] = nextState;
            }
            refreshCompUI(); renderCustomExts(); saveCompState(); 
        }
        
        function toggleExtEditMode() { extEditModeUI = !extEditModeUI; document.getElementById('comp-ext-container').classList.toggle('ext-edit-mode', extEditModeUI); renderCustomExts(); }

        function renderCustomExts() {
            let cs = currentCompState(); 
            if (!cs.customExts) cs.customExts = [];
            if (!cs.orderExt) cs.orderExt = [...cs.customExts];
            
            // 数据迁移：将旧的全局后缀无缝移至当前工作区
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
        
        function onCustomExtClick(e, ext) { 
            if (isDragAction(e)) return; 
            if (e.target.closest && e.target.closest('.custom-ext-del')) return;
            let now = Date.now(); if (now - (lastClickTime[`ext_${ext}`] || 0) < 150) return; lastClickTime[`ext_${ext}`] = now;
            
            let cs = currentCompState();
            if (!cs.customExts) cs.customExts = [];
            if (!cs.orderExt) cs.orderExt = [];
            
            if (extEditModeUI && e.button === 0) { 
                openQuickEdit(e.clientX, e.clientY, ext, (val) => { 
                    if (val && val !== ext) { 
                        let idx = cs.customExts.indexOf(ext); cs.customExts[idx] = val; 
                        let oIdx = cs.orderExt.indexOf(ext); cs.orderExt[oIdx] = val; 
                        if(cs.types[ext]) { cs.types[val] = cs.types[ext]; delete cs.types[ext]; } 
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
                    sysLog("XYplorer 批注同步成功", "INFO");
                    showToast(t("toast_sync_ok"), "success");
                } else {
                    sysLog("同步失败：" + res.msg, "ERROR");
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
                pushHistory(key, val); // 去除硬编码前缀，由 pushHistory 内部动态拼接当前工作区
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
                
                // 智能检测：如果包含字母（高级语法如 dw, m, d 等），强制剔除比较符号
                if (/[a-zA-Z]/.test(val)) {
                    op = ""; 
                    document.getElementById('date-op').value = ""; // 同时让界面上的下拉框变为空白
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
            
            // 自动清洗：遍历并修复以前可能残留了比较符号的高级语法旧规则
            cs.rules = cs.rules.map(r => {
                let match = r.match(/^(dateC|dateM|dateA|ageC|ageM|ageA):\\s*(>=|<=|==|>|<)?\\s*(.*)$/);
                // 如果是时间类型，且值里面包含字母，就强制丢弃 match[2] 的运算符号
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
                // 匹配日期与时间格式，兼容无符号的高级语法
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
                sysLog("历史记录已删除", "INFO");
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
                let bgColor = (configData.wsColors && configData.wsColors[ws]) ? configData.wsColors[ws] : '';
                let styleStr = isActive ? `background: var(--primary); color: #fff; border-color:var(--primary);` : (bgColor ? `background: ${bgColor};` : '');
                let sws = _e(ws);
                let hws = _h(t(ws));
                html += `<div class="ws-tab ${isActive ? 'active' : ''}" id="ws-tab-${_h(ws)}" style="${styleStr}" draggable="true" ondragstart="onDragStartWs(event, '${sws}')" ondragover="onDragOverWs(event)" ondragleave="onDragLeaveWs(event)" ondrop="onDropWs(event, '${sws}')" onclick="switchWs('${sws}')" oncontextmenu="onWsCtx(event, '${sws}')">${hws}</div>`; 
            });
            container.innerHTML = html; renderSVGs(container);
            setTimeout(updateWsVisibility, 50); 
        }
        
        function updateWsVisibility() {
            const container = document.getElementById('ws-tabs-scroll');
            const dynamicArea = document.getElementById('ws-dynamic-area');
            const activeTab = document.getElementById(`ws-tab-${_h(configData.currentWs)}`);
            
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
                html += `<div class="menu-item ws-list-item ${isActive ? 'active' : ''}" 
                              onclick="switchWs('${sws}'); document.getElementById('ws-list-menu').style.display='none';"
                              oncontextmenu="onWsCtx(event, '${sws}'); ">
                            <span class="menu-text">${_h(t(ws))}</span>
                         </div>`;
            });
            menu.innerHTML = html;
            menu.style.display = 'flex';
            setSafePosition(menu, e.clientX - 100, e.clientY + 15);
        }

        function switchWs(ws) { if (configData.currentWs === ws) return; configData.currentWs = ws; debouncedSaveConfig(); state.tagStates = {}; clickOrder = []; state.expandedGroups = {}; initExpandedState(currentTree(), ""); renderWsBar(); initCompModule(); render(); }
        
        function addWs(e) { 
            openQuickEdit(e.clientX, e.clientY, t("new_ws"), val => { 
                if (val && !allTreeData[val]) { 
                    allTreeData[val] = { "未分类": { "_bg_color": "", "_tags": ["?*", '""'] }, "_compState": { types: {}, path: "", name: "", remarkMode: "", remark: "", label: "", ratings: {}, rules: [] } }; 
                    let wsList = getWsList();
                    if (!wsList.includes(val)) { wsList.push(val); configData.orderWs = wsList; debouncedSaveConfig(); }
                    saveDataAndRenderAll(); 
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
                    sysLog("工作区颜色已更新", "INFO");
                });
            } else if (action === 'color-reset') {
                if(configData.wsColors) delete configData.wsColors[ws];
                debouncedSaveConfig();
                renderWsBar();
                sysLog("工作区颜色已恢复默认", "INFO");
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

                        // 同步迁移该工作区的历史记录
                        ['path', 'name', 'remark'].forEach(k => {
                            if (configData[`hist_${k}_${ws}`]) {
                                configData[`hist_${k}_${val}`] = configData[`hist_${k}_${ws}`];
                                delete configData[`hist_${k}_${ws}`];
                            }
                        });
                        
                        if (configData.currentWs === ws) { configData.currentWs = val; } 
                        debouncedSaveConfig();
                        saveDataAndRenderAll(); 
                    } 
                }); 
            } else if (action === 'duplicate') { 
                let newWs = ws + " Copy"; let count = 1; 
                while(allTreeData[newWs]) { count++; newWs = `${ws} Copy ${count}`; } 
                allTreeData[newWs] = JSON.parse(JSON.stringify(allTreeData[ws])); 
                
                let keys = getWsList();
                let idx = keys.indexOf(ws);
                if (idx !== -1) keys.splice(idx + 1, 0, newWs);
                else keys.push(newWs);
                configData.orderWs = keys;

                // 完美复刻原工作区的历史记录
                ['path', 'name', 'remark'].forEach(k => {
                    if (configData[`hist_${k}_${ws}`]) {
                        configData[`hist_${k}_${newWs}`] = [...configData[`hist_${k}_${ws}`]];
                    }
                });

                debouncedSaveConfig();
                
                let newAll = {}; for (let k of keys) newAll[k] = allTreeData[k]; allTreeData = newAll;
                saveDataAndRenderAll(); 
            } else if (action === 'delete') { 
                if (Object.keys(allTreeData).length <= 1) { 
                    showToast(t("toast_ws_keep_one"), "error"); 
                    sysLog("至少需保留一个工作区！", "ERROR"); 
                    return; 
                } 
                showConfirmModal(t('confirm_del_ws').replace('{ws}', ws), () => {
                    delete allTreeData[ws]; 

                    // 彻底销毁该工作区关联的所有历史垃圾记录
                    ['path', 'name', 'remark'].forEach(k => {
                        delete configData[`hist_${k}_${ws}`];
                    });

                    if (configData.currentWs === ws) { configData.currentWs = Object.keys(allTreeData)[0]; } 
                    let keys = getWsList();
                    configData.orderWs = keys.filter(k => k !== ws);
                    debouncedSaveConfig();
                    if (configData.currentWs === ws) { state.tagStates = {}; clickOrder = []; initExpandedState(currentTree(), ""); } 
                    saveDataAndRenderAll(); 
                    sysLog("工作区已删除", "INFO");
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
            saveDataAndRenderAll(); 
        }

        function saveDataAndRenderAll() { 
            try {
                pywebview.api.save_data(allTreeData).then(() => { 
                    renderWsBar(); 
                    render(); 
                    let wl = document.getElementById('ws-list-menu');
                    if (wl && wl.style.display === 'flex') {
                        wl.style.display = 'none';
                        let html = '';
                        getWsList().forEach(ws => { 
                            const isActive = ws === configData.currentWs;
                            let sws = _e(ws);
                            html += `<div class="menu-item ws-list-item ${isActive ? 'active' : ''}" 
                                          onclick="switchWs('${sws}'); document.getElementById('ws-list-menu').style.display='none';"
                                          oncontextmenu="onWsCtx(event, '${sws}'); ">
                                        <span class="menu-text">${_h(t(ws))}</span>
                                     </div>`;
                        });
                        wl.innerHTML = html;
                        wl.style.display = 'flex';
                    }
                });
            } catch(e) { 
                renderWsBar(); 
                render(); 
            } 
        }

        function toggleTool(toolName) {
            if (toolName === 'editMode') {
                state.editMode = !state.editMode;
                document.getElementById('btn-edit').classList.toggle('active-orange', state.editMode);
                render();
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
        function toggleAll() { 
            state.allExpanded = !state.allExpanded; 
            state.activeOnly = false; 
            state.filterOnly = false; 
            document.getElementById('btn-active').classList.remove('active-green'); 
            document.getElementById('btn-filter').classList.remove('active-green'); 
            document.getElementById('btn-toggle').innerHTML = state.allExpanded ? SVGS.expand : SVGS.minimize; 
            for (let k in state.expandedGroups) state.expandedGroups[k] = state.allExpanded; 
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
            let dn = _h(t(name));

            let isExpanded = state.expandedGroups[path]; let hasActive = checkActiveBubble(node, path);
            if (state.filterOnly && !hasActive) return "";

            let hasTags = node._tags && node._tags.length > 0;
            let hasSubgroups = false;
            for (let k in node) { if (!k.startsWith('_')) { hasSubgroups = true; break; } }
            let isExpandable = hasTags || hasSubgroups;

            let canAddTags = (level > 0) || (name === "未分类"); // 根级分组隐藏悬浮+号，改由右键菜单添加
            let isRoot = level === 0;
            let selfColor = node._bg_color; 
            let finalColor = isRoot ? (selfColor || 'transparent') : (selfColor || (node._parentBg && node._parentBg !== 'transparent' ? getLighterColor(node._parentBg) : 'transparent'));
            
            // 算法注入：动态判断文字与箭头的强对比颜色
            let dynTextColor = (finalColor && finalColor !== 'transparent') ? getContrastColor(finalColor) : '';
            let bgStyle = isRoot ? (selfColor ? `background: ${finalColor}; border-color: transparent; --group-text: ${dynTextColor}; --group-arrow: ${dynTextColor};` : ``) : ``;
            let html = `<div class="group ${isRoot ? 'group-root' : 'group-sub'} ${isExpanded ? '' : 'collapsed'}" data-path="${sp}" data-type="group" style="${bgStyle}">`;
            
            let arrowIcon = isExpanded ? 'arrowDown' : 'arrowRight';
            // 组名右侧悬浮的“+”按钮 (仅在无标签时在此处显示)
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

            if (isRoot) {
                html += `<div class="group-header" draggable="true" ondragstart="onDragStartTree(event, 'group', '${sp}', '${sn}')" ondragover="onDragOverTree(event)" ondragleave="onDragLeaveTree(event)" ondrop="onDropTree(event, '${sp}', '${sn}')" onmouseup="onGroupClick(event, '${sp}', '${sn}')" oncontextmenu="onGroupCtx(event, '${sp}', ${isRoot}, '${sn}')">`;
                html += isExpandable ? `<span class="group-arrow" v-html="${arrowIcon}"></span>` : `<span class="group-arrow" style="visibility:hidden;" v-html="arrowRight"></span>`;
                html += `<span class="group-title" data-name="${_h(name)}">${dn}</span><span class="group-dot ${hasActive ? 'show' : ''}">●</span>${headerAddBtn}</div>`;
            } else {
                html += `<div class="group-header" draggable="true" ondragstart="onDragStartTree(event, 'group', '${sp}', '${sn}')" ondragover="onDragOverTree(event)" ondragleave="onDragLeaveTree(event)" ondrop="onDropTree(event, '${sp}', '${sn}')" onmouseup="onGroupClick(event, '${sp}', '${sn}')" oncontextmenu="onGroupCtx(event, '${sp}', ${isRoot}, '${sn}')">`;
                html += `<span class="group-title" data-name="${_h(name)}">${dn}</span><span class="group-dot ${hasActive ? 'show' : ''}">●</span>${headerAddBtn}</div>`;
            }

            html += `<div class="group-content"><div class="tags-area" ondragover="onDragOverTreeArea(event)" ondragleave="onDragLeaveTreeArea(event)" ondrop="onDropTreeArea(event, '${sp}')">`;
            if (hasTags) {
                node._tags.forEach(tagStr => {
                    let st = _e(tagStr);
                    let ht = _h(t(tagStr));
                    let key = `${path}|${tagStr}`; 
                    let tState = state.tagStates[key] || 0; 
                    let cls = tState === 1 ? 's1' : (tState === 2 ? 's2' : (tState === 3 ? 's3' : ''));
                    
                    // 核心逻辑：如果是未激活状态，且父级色条有颜色，则将其作为局部 CSS 变量注入给该按钮
                    let styleStr = '';
                    if (tState === 0 && finalColor && finalColor !== 'transparent') {
                        let textColor = getContrastColor(finalColor);
                        styleStr = `style="--bg-btn: ${finalColor}; --border-color: ${finalColor}; --btn-text: ${textColor};"`;
                    }

                    html += `
                    <div class="tag-btn ${cls}" ${styleStr} draggable="true" ondragstart="onDragStartTree(event, 'tag', '${sp}', '${st}')" ondragover="onDragOverTreeTag(event)" ondragleave="onDragLeaveTree(event)" ondrop="onDropTreeTag(event, '${sp}', '${st}')" onmouseup="onTagClick(event, '${sp}', '${st}')" oncontextmenu="event.preventDefault()">
                        ${ht}<div class="tag-del" onmousedown="event.stopPropagation();" onmouseup="delTagBtn(event, '${sp}', '${st}')" v-html="delete"></div>
                    </div>`;
                });
                // 如果有标签，+号按钮出现在标签末尾
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
            let sIdx = srcNode._tags.indexOf(dragItem.name);
            if (sIdx > -1) srcNode._tags.splice(sIdx, 1);
            
            let tgtNode = getNodeByPath(targetPath);
            if (!tgtNode._tags) tgtNode._tags = [];
            if (!tgtNode._tags.includes(dragItem.name)) tgtNode._tags.push(dragItem.name);
            
            saveDataAndRenderAll();
        }

        function onTagClick(e, path, tag) {
            if (isDragAction(e)) return;
            if (e.target.closest && e.target.closest('.tag-del')) return;
            
            // Alt + 中键 (e.button === 1)：重命名标签
            if (e.altKey && e.button === 1) {
                e.preventDefault(); e.stopPropagation();
                openQuickEdit(e.clientX, e.clientY, tag, (val) => { 
                    if (val && val !== tag) { 
                        let node = getNodeByPath(path); 
                        let idx = node._tags.indexOf(tag); 
                        if (idx > -1) { 
                            node._tags[idx] = val; 
                            saveDataAndRenderAll(); 
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
                            let idx = node._tags.indexOf(tag); 
                            if (idx > -1) { 
                                node._tags[idx] = val; 
                                saveDataAndRenderAll(); 
                            } 
                        } 
                    }); 
                } 
                return; 
            }
            
            let key = `${path}|${tag}`; 
            let now = Date.now(); if (now - (lastClickTime[key] || 0) < 150) return; lastClickTime[key] = now;
            let cur = state.tagStates[key] || 0; let nextState = 0;
            if (e.button === 0) nextState = cur === 1 ? 0 : 1; else if (e.button === 2) nextState = cur === 2 ? 0 : 2; else if (e.button === 1) nextState = cur === 3 ? 0 : 3; 
            if (cur === nextState) return; 
            
            state.tagStates[key] = nextState; 

            // 核心互斥与清理逻辑
            if (nextState !== 0) {
                if (tag === '""') {
                    // 规则1：选择"无标签"时，清除所有其他激活的标签
                    Object.keys(state.tagStates).forEach(k => {
                        if (k !== key && state.tagStates[k] !== 0) {
                            state.tagStates[k] = 0;
                            clickOrder = clickOrder.filter(x => x !== k);
                        }
                    });
                } else if (tag === '?*') {
                    // 规则2：选择"有标签"时，清除"无标签"，以及所有处于 包含(1) 或 或者(3) 状态的普通标签
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
                    // 规则3：当激活普通标签时，进行反向校验
                    Object.keys(state.tagStates).forEach(k => {
                        let otherTag = k.split('|')[1];
                        // 任何标签被激活，都会挤掉"无标签"
                        if (otherTag === '""' && state.tagStates[k] !== 0) {
                            state.tagStates[k] = 0;
                            clickOrder = clickOrder.filter(x => x !== k);
                        }
                        // 如果以 包含(1) 或 或者(3) 激活，则挤掉"有标签"
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
                
                if (stateVal === 2) {
                    // 核心修改1：如果是排除(红色)，则丢入单独的排除数组
                    excludeTags.push(tag);
                } else {
                    // 如果是包含/或者(绿色/蓝色)，正常拼接到包含链中
                    let formattedTag = tag;
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
                    if (state.tagStates[key] === 1) {
                        activeTags.push(tag); 
                    } else if (state.tagStates[key] === 2) {
                        removeTags.push(tag); 
                    }
                }
            }); 
            
            if (activeTags.length === 0 && removeTags.length === 0) {
                return showToast(t("toast_no_tags_act"), "error"); 
            }
            
            let cmd = ""; 
            if (removeTags.length > 0) {
                cmd += `tag '${removeTags.join(',')}', , 1, 2; `;
            }
            if (activeTags.length > 0) {
                cmd += `tag '${activeTags.join(',')}', , 1; `;
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
        
        function activateTagsFromText(tags) { 
            let tree = currentTree(); let changed = false; 
            tags.forEach(t => { 
                if (!t || t.includes("Ctrl+V") || t.includes("剪贴板")) return; 
                let foundPath = findTagPath(tree, "", t); 
                if (foundPath) { 
                    state.tagStates[`${foundPath}|${t}`] = 1; 
                    if (!clickOrder.includes(`${foundPath}|${t}`)) clickOrder.push(`${foundPath}|${t}`); 
                    let parts = foundPath.split('/'); let curP = ""; 
                    parts.forEach(p => { curP += (curP?"/":"")+p; state.expandedGroups[curP] = true; }); 
                    changed = true; 
                } else { 
                    if (!tree["未分类"]) tree["未分类"] = { "_bg_color": "", "_tags": ["?*", '""'] }; 
                    if (!tree["未分类"]._tags.includes(t)) tree["未分类"]._tags.push(t); 
                    state.tagStates[`未分类|${t}`] = 1; 
                    if (!clickOrder.includes(`未分类|${t}`)) clickOrder.push(`未分类|${t}`); 
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
                saveDataAndRenderAll(); 
            } 
        }

        function findTagPath(node, path, tag) { if (node._tags && node._tags.includes(tag)) return path; for (let k in node) { if (!k.startsWith('_')) { let res = findTagPath(node[k], path ? path+'/'+k : k, tag); if (res) return res; } } return null; }
        function clearAllFiltersAndTags() { clearCompFilters(); clearAll(); showToast(t("clear_title"), "success"); }
        function checkActiveBubble(node, path) { if (node._tags && node._tags.some(t => state.tagStates[`${path}|${t}`])) return true; for (let k in node) { if (!k.startsWith('_') && checkActiveBubble(node[k], path + '/' + k)) return true; } return false; }

        function onGroupClick(e, path, name) { 
            if (isDragAction(e)) return; 
            
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
                        saveDataAndRenderAll(); 
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
                        saveDataAndRenderAll(); 
                    } 
                }); 
            } else { 
                let node = getNodeByPath(path);
                let hasTags = node._tags && node._tags.length > 0;
                let hasSubgroups = false;
                for (let k in node) { if (!k.startsWith('_')) { hasSubgroups = true; break; } }
                if (!hasTags && !hasSubgroups) return; // 核心：空组彻底禁止折叠/展开操作

                state.expandedGroups[path] = !state.expandedGroups[path]; 
                render(); 
            } 
        }
        function addRootGroup(e) { openQuickEdit(e.clientX, e.clientY, "", (val) => { if (val && !currentTree()[val]) { currentTree()[val] = {"_tags": [], "_bg_color": ""}; saveDataAndRenderAll(); } }); }
        
        // 加入了 e.stopPropagation() 以防止在组名栏点击+号时触发展开操作
        function addTag(e, path) { 
            e.stopPropagation(); 
            openQuickEdit(e.clientX, e.clientY, "", (val) => { 
                if (val) { 
                    let node = getNodeByPath(path); 
                    if (!node._tags) node._tags = []; 
                    if (!node._tags.includes(val)) { node._tags.push(val); saveDataAndRenderAll(); } 
                } 
            }); 
        }
        
        function delTagBtn(e, path, tag) { 
            e.stopPropagation(); e.preventDefault(); 
            let node = getNodeByPath(path); 
            node._tags = node._tags.filter(t => t !== tag); 
            delete state.tagStates[`${path}|${tag}`]; 
            clickOrder = clickOrder.filter(k => k !== `${path}|${tag}`); 
            saveDataAndRenderAll(); 
            sysLog(`标签 "${tag}" 已删除`, "INFO"); 
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
                    let sw = _e(w); let hw = _h(t(w)); 
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
            if (action === 'color') { let node = getNodeByPath(p); openColorModal(node._bg_color || "", (newHex) => { if (newHex) { node._bg_color = newHex; saveDataAndRenderAll(); sysLog("分组颜色已更新", "INFO"); } }); } 
            else if (action === 'color-reset') { let node = getNodeByPath(p); delete node._bg_color; saveDataAndRenderAll(); sysLog("分组颜色已恢复默认", "INFO"); }
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
                saveDataAndRenderAll();
                sysLog("未分类组已恢复默认标签", "INFO");
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
                        saveDataAndRenderAll(); 
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
                render(); // UI状态改变，只重绘不写盘
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
                render();
            }
            else if (action === 'add') { openQuickEdit(gStartX, gStartY, "", val => { if (val) { getNodeByPath(p)[val] = {"_tags": []}; state.expandedGroups[p] = true; saveDataAndRenderAll(); } }); }
            else if (action === 'batch-add') { batchTarget = { type: 'subgroup', path: p }; executeBatchAddMenu(); }
            else if (action === 'add-tag') {
                openQuickEdit(gStartX, gStartY, "", val => {
                    if (val) {
                        let node = getNodeByPath(p);
                        if (!node._tags) node._tags = [];
                        if (!node._tags.includes(val)) { node._tags.push(val); saveDataAndRenderAll(); }
                    }
                });
            }
            else if (action === 'batch-add-tag') { batchTarget = { type: 'tag', path: p }; executeBatchAddMenu(); }
            else if (action === 'delete') { if (n === "未分类") return; let parent = getParentNode(p); delete parent[n]; saveDataAndRenderAll(); } 
        }
        function execWsTransfer(action, targetWs) { ctxMenu.style.display = 'none'; if (ctxTarget.name === "未分类") return showToast(t("toast_no_uncat_op"), "error"); let parent = getParentNode(ctxTarget.path); let dataCopy = JSON.parse(JSON.stringify(parent[ctxTarget.name])); allTreeData[targetWs][ctxTarget.name] = dataCopy; if (action === 'move') delete parent[ctxTarget.name]; saveDataAndRenderAll(); }

        function getNodeByPath(pathStr) { let parts = pathStr.split('/'); let curr = currentTree(); for (let p of parts) curr = curr[p]; return curr; }
        function getParentNode(pathStr) { let parts = pathStr.split('/'); let curr = currentTree(); for (let i = 0; i < parts.length - 1; i++) curr = curr[parts[i]]; return curr; }

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
                if (!tgtNode._tags.includes(dragItem.name)) tgtNode._tags.push(dragItem.name); 
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
            saveDataAndRenderAll(); 
        }
        
        function onDragOverTreeTag(e) { e.preventDefault(); e.stopPropagation(); if (dragItem.type !== 'tag') return; let el = e.currentTarget; el.classList.remove('drag-left', 'drag-right'); let r = el.getBoundingClientRect(); if (e.clientX - r.left < r.width / 2) el.classList.add('drag-left'); else el.classList.add('drag-right'); }
        
        function onDropTreeTag(e, targetPath, targetTag) { 
            e.preventDefault(); e.stopPropagation(); 
            e.currentTarget.classList.remove('drag-left', 'drag-right'); 
            if (!dragItem || dragItem.type !== 'tag') return; 
            if (dragItem.path === targetPath && dragItem.name === targetTag) return; 
            
            let srcNode = getNodeByPath(dragItem.path); 
            let sIdx = srcNode._tags.indexOf(dragItem.name);
            if (sIdx > -1) srcNode._tags.splice(sIdx, 1); 
            
            let tgtNode = getNodeByPath(targetPath); 
            if (!tgtNode._tags) tgtNode._tags = []; 
            let tIdx = tgtNode._tags.indexOf(targetTag);  
            if (tIdx < 0) tIdx = tgtNode._tags.length;
            
            let r = e.currentTarget.getBoundingClientRect(); 
            if (e.clientX - r.left >= r.width / 2) tIdx++; 
            tgtNode._tags.splice(tIdx, 0, dragItem.name); 
            saveDataAndRenderAll(); 
        }

        function triggerBatchAddMenu(e, type, path, forcedX, forcedY) {
            if(e) { e.preventDefault(); e.stopPropagation(); }
            batchTarget = { type, path };
            const menu = document.getElementById('batch-add-menu');
            menu.style.display = 'flex';
            setSafePosition(menu, e ? e.clientX : forcedX, e ? e.clientY : forcedY);
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

        function showConfirmModal(msg, callback) {
            document.getElementById('confirm-msg').innerText = msg;
            currentConfirmCallback = callback;
            
            const modal = document.getElementById('confirm-modal');
            const content = modal.querySelector('.modal-content');
            
            modal.style.display = 'flex';
            
            content.style.position = 'absolute';
            content.style.margin = '0';
            
            let w = content.offsetWidth;
            let h = content.offsetHeight;
            
            let x = (window.innerWidth - w) / 2;
            let y = gStartY - h / 2;
            
            x = Math.max(10, x);
            y = Math.max(10, Math.min(y, window.innerHeight - h - 10));
            
            content.style.left = x + 'px';
            content.style.top = y + 'px';
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
                saveDataAndRenderAll();
            } else if (batchTarget.type === 'tag') {
                let node = getNodeByPath(batchTarget.path);
                if (!node._tags) node._tags = [];
                lines.forEach(val => {
                    if (!node._tags.includes(val)) node._tags.push(val);
                });
                saveDataAndRenderAll();
            } else if (batchTarget.type === 'subgroup') {
                let node = getNodeByPath(batchTarget.path);
                lines.forEach(val => {
                    if(!node[val]) node[val] = {"_tags": []};
                });
                state.expandedGroups[batchTarget.path] = true;
                saveDataAndRenderAll();
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

        function onCompTypeClick(e, tName) { 
            if (isDragAction(e)) return; 
            let now = Date.now(); if (now - (lastClickTime[`type_${tName}`] || 0) < 150) return; lastClickTime[`type_${tName}`] = now;
            let cs = currentCompState(); let cur = cs.types[tName] || 0; 
            
            if (e.button === 0) {
                let nextState = cur === 1 ? 0 : 1;
                if (nextState === 1) {
                    for (let k in cs.types) {
                        if (cs.types[k] === 2) delete cs.types[k];
                    }
                }
                cs.types[tName] = nextState;
            } else if (e.button === 2) {
                let nextState = cur === 2 ? 0 : 2;
                if (nextState === 2) {
                    cs.types = {};
                }
                cs.types[tName] = nextState;
            }
            refreshCompUI(); renderCustomExts(); saveCompState(); 
        }

        function onCustomExtClick(e, ext) { 
            if (isDragAction(e)) return; 
            if (e.target.closest && e.target.closest('.custom-ext-del')) return;
            let now = Date.now(); if (now - (lastClickTime[`ext_${ext}`] || 0) < 150) return; lastClickTime[`ext_${ext}`] = now;
            
            if (extEditModeUI && e.button === 0) { 
                openQuickEdit(e.clientX, e.clientY, ext, (val) => { 
                    if (val && val !== ext) { 
                        let idx = configData.customExts.indexOf(ext); configData.customExts[idx] = val; 
                        let oIdx = configData.orderExt.indexOf(ext); configData.orderExt[oIdx] = val; 
                        let cs = currentCompState(); 
                        if(cs.types[ext]) { cs.types[val] = cs.types[ext]; delete cs.types[ext]; } 
                        debouncedSaveConfig(); renderCustomExts(); saveCompState(); 
                    } 
                }); 
                return; 
            } 
            
            let cs = currentCompState(); let cur = cs.types[ext] || 0; 
            
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
        
        function openQuickEdit(x, y, defVal, cb) { 
            qCallback = cb; 
            const qe = document.getElementById('quick-edit');
            const qInput = document.getElementById('edit-input');
            qInput.value = defVal; 
            qe.style.display = 'block'; 
            setSafePosition(qe, x, y);
            setTimeout(() => { qInput.focus(); qInput.select(); }, 50); 
        }
        function getLighterColor(hex) { if (!hex || hex === 'transparent') return '#00bcd4'; let r = parseInt(hex.slice(1,3), 16), g = parseInt(hex.slice(3,5), 16), b = parseInt(hex.slice(5,7), 16); r = Math.min(255, r + 40); g = Math.min(255, g + 40); b = Math.min(255, b + 40); return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1); }
        function getContrastColor(hex) { if (!hex || hex === 'transparent') return ''; let c = hex.startsWith('#') ? hex.slice(1) : hex; if (c.length === 3) c = c.split('').map(x => x + x).join(''); let r = parseInt(c.slice(0, 2), 16), g = parseInt(c.slice(2, 4), 16), b = parseInt(c.slice(4, 6), 16); let yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000; return yiq >= 128 ? '#111111' : '#FFFFFF'; }

        // ======= 版本更新与链接逻辑 =======
        const CURRENT_VERSION = '1.2.2'; // 每次更新软件时，除了改 Python 里的 WINDOW_TITLE，也要顺手改这里
        
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
                        showConfirmModal(`${t('update_found')} (v${latest})\n\n${t('go_to_download')}`, () => {
                            pywebview.api.open_url('https://github.com/C21H21NO2S/XYplorerTagHelper/releases/latest');
                        });
                    } else {
                        showToast(t('is_latest'), 'success');
                    }
                }
            } catch (err) {
                showToast(t('update_fail'), 'error');
                sysLog(`检查更新异常: ${err.message}`, "ERROR");
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
    
    window = webview.create_window(
        WINDOW_TITLE, 
        html=html_template.replace("/*__INIT_DATA__*/{}", initial_data).replace("/*__INIT_CONFIG__*/{}", initial_config), 
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
                    res = ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
                    if res == 0:
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
            write_log(f"保存窗口状态失败: {e}", "ERROR")
        
    window.events.closing += on_closing

    webview.start()
