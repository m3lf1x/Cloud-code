"""
Cloud Code by m3lf1x — бесплатный аналог Claude Code на базе opencode.
Интерфейс: HTML в окне pywebview.

    pip install pywebview
    npm i -g opencode-ai
    python cloud_code.py

Ключи и оплата не нужны: автоматически выбирается бесплатная модель opencode.
"""
import codecs
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

# убираем собственную консоль программы (даже если exe собран без --windowed).
# Для отладки с консолью: set CC_DEBUG=1
if sys.platform == "win32" and not os.environ.get("CC_DEBUG"):
    try:
        import ctypes
        _h = ctypes.windll.kernel32.GetConsoleWindow()
        if _h:
            ctypes.windll.user32.ShowWindow(_h, 0)
        ctypes.windll.kernel32.FreeConsole()
    except Exception:
        pass
    for _n in ("stdout", "stderr"):
        setattr(sys, _n, open(os.devnull, "w"))
for _n in ("stdout", "stderr"):
    if getattr(sys, _n) is None:
        setattr(sys, _n, open(os.devnull, "w"))

import traceback

try:
    import webview
except Exception:  # например, не установлен pythonnet: покажем понятную ошибку при старте
    webview = None
    _IMPORT_ERR = traceback.format_exc()

APP = Path.home() / ".cloud_code"
APP.mkdir(exist_ok=True)
CHATS, CFG = APP / "chats.json", APP / "config.json"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")
IGNORE = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".idea", ".vscode", ".DS_Store"}
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
WIN = sys.platform == "win32"
VERSION = "1.1.1"
REPO = "m3lf1x/Cloud-code"


def _dlg(kind):  # совместимо с разными версиями pywebview
    FD = getattr(webview, "FileDialog", None)
    return getattr(FD, kind) if FD else getattr(webview, kind + "_DIALOG")


def _si():  # полностью скрывает консольное окно дочерних процессов (Windows)
    if not WIN:
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return si


def jload(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def fix_path():
    """macOS/Linux: приложение, запущенное из Finder, не видит PATH терминала.
    Добавляем типичные папки и, если opencode не найден, берём PATH из login-shell."""
    if WIN:
        return
    h = Path.home()
    extra = ["/opt/homebrew/bin", "/usr/local/bin", str(h / ".opencode" / "bin"), str(h / ".bun" / "bin"),
             str(h / ".npm-global" / "bin"), str(h / ".local" / "bin")]
    os.environ["PATH"] = ":".join(dict.fromkeys([p for p in os.environ.get("PATH", "").split(":") + extra if p]))
    if not shutil.which("opencode"):
        try:
            sh = os.environ.get("SHELL") or "/bin/zsh"
            out = subprocess.run([sh, "-ilc", 'printf "%s" "$PATH"'], capture_output=True, text=True,
                                 timeout=8, stdin=subprocess.DEVNULL).stdout.strip().splitlines()
            if out:
                os.environ["PATH"] = ":".join(dict.fromkeys([p for p in out[-1].split(":") + os.environ["PATH"].split(":") if p]))
        except Exception:
            pass


def find_oc():
    p = shutil.which("opencode")
    if p:
        return p
    h = Path.home()
    c = []
    if WIN:
        for base in (os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")):
            if base:
                c += [Path(base) / "npm" / "opencode.cmd", Path(base) / "npm" / "opencode.exe"]
        c += [h / ".opencode" / "bin" / "opencode.exe", h / "scoop" / "shims" / "opencode.exe"]
    else:
        c += [h / ".opencode" / "bin" / "opencode", h / ".local" / "bin" / "opencode",
              Path("/usr/local/bin/opencode"), Path("/opt/homebrew/bin/opencode")]
    for x in c:
        if x.exists():
            return str(x)
    return None


class Api:
    def __init__(self):
        self.window = None
        self.cfg = jload(CFG, {})
        cwd = self.cfg.get("cwd")
        self.cwd = cwd if cwd and os.path.isdir(cwd) else os.getcwd()
        self.proc = None
        self.oc = find_oc()
        self.git_bin = shutil.which("git")

    # ---------- утилиты ----------
    def _js(self, fn, *args):
        if self.window:
            try:
                self.window.evaluate_js(f"{fn}({','.join(json.dumps(a) for a in args)})")
            except Exception:
                pass

    def _run(self, cmd, timeout=20):
        try:
            r = subprocess.run(cmd, cwd=self.cwd, capture_output=True, timeout=timeout,
                               stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace",
                               creationflags=NOWIN, startupinfo=_si())
            return ANSI.sub("", r.stdout or "")
        except Exception as e:
            return f"ERROR: {e}"

    def _safe(self, rel):
        root = Path(self.cwd).resolve()
        p = (root / rel).resolve()
        if root != p and root not in p.parents:
            raise ValueError("outside project")
        return p

    # ---------- состояние ----------
    def start(self):  # мгновенно, без запуска процессов
        if not self.oc:
            return {"ok": False, "message": "opencode не найден. Установи: npm i -g opencode-ai и перезапусти программу."}
        return {"ok": True}

    def version(self):
        out = self._run([self.oc, "--version"], 12).strip().splitlines() if self.oc else []
        v = out[-1] if out else ""
        return "" if v.startswith("ERROR") else v

    def state(self):
        return {"chats": jload(CHATS, []), "cfg": {**self.cfg, "cwd": self.cwd}, "version": VERSION}

    def save_chats(self, data):
        try:
            CHATS.write_text(data, encoding="utf-8")
        except Exception:
            pass

    def set_cfg(self, key, value):
        self.cfg[key] = value
        try:
            CFG.write_text(json.dumps(self.cfg, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def choose_folder(self):
        res = self.window.create_file_dialog(_dlg("FOLDER"), directory=self.cwd)
        if res:
            self.cwd = res[0]
            self.set_cfg("cwd", self.cwd)
        return self.cwd

    def models(self):
        out = self._run([self.oc, "models"], 25) if self.oc else ""
        ms = [l.strip() for l in out.splitlines() if "/" in l and " " not in l.strip() and not l.startswith("ERROR")]
        return sorted(ms, key=lambda m: (not (m.startswith("opencode/") and "free" in m), not m.startswith("opencode/")))

    # ---------- файлы и git ----------
    def files(self, rel=""):
        try:
            d = self._safe(rel)
            items = []
            for p in d.iterdir():
                if p.name in IGNORE:
                    continue
                items.append({"name": p.name, "dir": p.is_dir(), "rel": str(p.relative_to(Path(self.cwd).resolve())).replace("\\", "/")})
            items.sort(key=lambda i: (not i["dir"], i["name"].lower()))
            return {"ok": True, "items": items}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def read_file(self, rel):
        try:
            p = self._safe(rel)
            size = p.stat().st_size
            if size > 400_000:
                return {"ok": True, "text": "", "size": size, "note": "Файл слишком большой для просмотра"}
            raw = p.read_bytes()
            if b"\0" in raw[:4096]:
                return {"ok": True, "text": "", "size": size, "note": "Бинарный файл"}
            return {"ok": True, "text": raw.decode("utf-8", "replace"), "size": size}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def git(self):
        if not self.git_bin:
            return {"ok": False, "message": "git не установлен"}
        out = self._run([self.git_bin, "status", "--porcelain"])
        if out.startswith("ERROR") or "not a git repository" in out:
            return {"ok": False, "message": "Папка не является git-репозиторием"}
        items = []
        for l in out.splitlines():
            if len(l) > 3:
                path = l[3:].split(" -> ")[-1].strip('"')
                items.append({"status": l[:2].strip() or "?", "path": path})
        return {"ok": True, "items": items}

    def git_diff(self, path, status):
        if status in ("?", "??"):
            r = self.read_file(path)
            return "\n".join("+" + x for x in (r.get("text") or "").splitlines()) or r.get("note", "")
        out = self._run([self.git_bin, "diff", "HEAD", "--", path])
        return out or self._run([self.git_bin, "diff", "--", path]) or "Нет изменений"

    # ---------- обновления, папка, экспорт ----------
    def check_update(self):
        try:
            import urllib.request
            req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                         headers={"User-Agent": "CloudCode"})
            d = json.loads(urllib.request.urlopen(req, timeout=6).read().decode("utf-8"))
            tag = str(d.get("tag_name", ""))
            num = lambda v: tuple(int(x) for x in re.findall(r"\d+", v)[:3])
            if tag and num(tag) > num(VERSION):
                return {"new": True, "version": tag.lstrip("vV"), "url": d.get("html_url") or f"https://github.com/{REPO}/releases/latest"}
        except Exception:
            pass
        return {"new": False}

    def open_url(self, url):
        if str(url).startswith("https://github.com/"):
            import webbrowser
            webbrowser.open(url)

    def open_folder(self):
        try:
            if WIN:
                os.startfile(self.cwd)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", self.cwd])
        except Exception:
            pass

    def export_chat(self, title, text):
        try:
            name = re.sub(r'[\\/:*?"<>|]+', "", title).strip()[:40] or "chat"
            res = self.window.create_file_dialog(_dlg("SAVE"), directory=self.cwd, save_filename=name + ".md")
            if not res:
                return ""
            path = Path(res if isinstance(res, str) else res[0])
            path.write_text(text, encoding="utf-8")
            return path.name
        except Exception:
            return ""

    # ---------- буфер обмена (надёжно, без браузерных ограничений) ----------
    def copy(self, text):
        if WIN:
            import ctypes
            k, u = ctypes.windll.kernel32, ctypes.windll.user32
            k.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
            k.GlobalAlloc.restype = ctypes.c_void_p
            k.GlobalLock.argtypes = [ctypes.c_void_p]
            k.GlobalLock.restype = ctypes.c_void_p
            k.GlobalUnlock.argtypes = [ctypes.c_void_p]
            u.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
            data = (text + "\0").encode("utf-16le")
            h = k.GlobalAlloc(0x0042, len(data))
            p = k.GlobalLock(h)
            ctypes.memmove(p, data, len(data))
            k.GlobalUnlock(h)
            for _ in range(10):
                if u.OpenClipboard(None):
                    u.EmptyClipboard()
                    u.SetClipboardData(13, h)
                    u.CloseClipboard()
                    return True
                threading.Event().wait(0.05)
            return False
        for c in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
            if shutil.which(c[0]):
                subprocess.run(c, input=text.encode("utf-8"))
                return True
        return False

    # ---------- запуск opencode ----------
    def send(self, prompt, model="", cont=False, context="", agent=""):
        if not self.oc:
            self._js("onError", "opencode не найден. Установи: npm i -g opencode-ai")
            self._js("onDone", 1)
            return
        threading.Thread(target=self._worker, args=(prompt, model, cont, context, agent), daemon=True).start()

    def _worker(self, prompt, model, cont, context, agent=""):
        if context:
            prompt = f"{context}\n\nНовое сообщение пользователя:\n{prompt}"
        # переносы строк в аргументах ломаются (cmd.exe режет по первому Enter),
        # поэтому весь текст запроса и контекст идут через stdin, а в аргументе — короткая строка
        cmd = [self.oc, "run"]
        if model.strip():
            cmd += ["--model", model.strip()]
        if agent == "plan":  # режим «план»: агент только анализирует, файлы не меняет
            cmd += ["--agent", "plan"]
        cmd.append("Выполни запрос пользователя. Полный текст запроса (с переносами строк) передан ниже.")
        rc = 1
        try:
            self.proc = subprocess.Popen(
                cmd, cwd=self.cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE, env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"},
                creationflags=NOWIN, startupinfo=_si())
            try:
                self.proc.stdin.write(prompt.encode("utf-8"))
                self.proc.stdin.close()
            except Exception:
                pass
            dec = codecs.getincrementaldecoder("utf-8")("replace")
            while True:
                chunk = self.proc.stdout.read1(4096)
                if not chunk:
                    break
                text = ANSI.sub("", dec.decode(chunk))
                if text:
                    self._js("onChunk", text)
            rc = self.proc.wait()
        except Exception as e:
            self._js("onError", str(e))
        finally:
            self._js("onDone", rc)

    def stop(self):
        p = self.proc
        if p and p.poll() is None:
            if WIN:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True,
                               stdin=subprocess.DEVNULL, creationflags=NOWIN, startupinfo=_si())
            else:
                p.terminate()


HTML = r"""<!doctype html>
<html lang="ru" data-theme="dark"><head><meta charset="utf-8"><title>Cloud Code by m3lf1x</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#000;--bg2:#070707;--panel:#0d0d0e;--panel2:#161617;--line:#252527;--txt:#ededed;--dim:#8c8c92;--dim2:#5a5a60;--acc:#f2f2f2;--accsoft:#ffffff12;--code:#060606;--ok:#54d69b;--bad:#ef6b7b;--warn:#e2a84c;--shadow:0 14px 50px #000c;color-scheme:dark}
[data-theme=light]{--bg:#f5f5f6;--bg2:#ebebed;--panel:#fff;--panel2:#f0f0f2;--line:#d9d9de;--txt:#111;--dim:#5e5e66;--dim2:#8f8f98;--acc:#111;--accsoft:#0000000d;--code:#f1f1f3;--shadow:0 14px 40px #0002;color-scheme:light}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--txt);font:14px/1.6 Inter,"Segoe UI",system-ui,sans-serif;overflow:hidden;-webkit-user-select:text;user-select:text}
button{-webkit-user-select:none;user-select:none}
button,input,textarea{font:inherit;color:inherit}
button{cursor:pointer;border:1px solid var(--line);background:var(--panel2);border-radius:9px;padding:6px 11px;transition:.15s;display:inline-flex;align-items:center;gap:7px;justify-content:center}
button:hover{border-color:var(--dim)}
svg{flex:none;display:block}
::-webkit-scrollbar{width:9px;height:9px}::-webkit-scrollbar-thumb{background:var(--line);border-radius:9px}::-webkit-scrollbar-thumb:hover{background:var(--dim2)}
kbd{font:10px Consolas,monospace;background:var(--bg2);border:1px solid var(--line);border-radius:5px;padding:1px 5px;color:var(--dim)}
.hidden{display:none!important}
.app{display:grid;grid-template-columns:276px 1fr;height:100vh}
.app.collapsed{grid-template-columns:1fr}.app.collapsed .sb{display:none}

.sb{background:var(--bg2);border-right:1px solid var(--line);display:flex;flex-direction:column;padding:16px 12px 12px;gap:10px;min-height:0}
.brand{display:flex;align-items:center;gap:12px;padding:2px 6px 12px}
.logo{width:40px;height:40px;border-radius:12px;background:radial-gradient(circle at 50% 0,#222,#000 70%);border:1px solid #4a4a4e;display:grid;place-items:center;color:#fff;box-shadow:0 0 18px #ffffff40,0 0 46px #ffffff1f,inset 0 0 12px #ffffff18;animation:glow 3.5s ease-in-out infinite}
[data-theme=light] .logo{box-shadow:0 0 18px #00000040,0 0 40px #00000022}
@keyframes glow{50%{box-shadow:0 0 26px #ffffff66,0 0 64px #ffffff30,inset 0 0 14px #ffffff22}}
.bn{font-size:17px;font-weight:760;letter-spacing:-.5px;line-height:1.1}
.by{display:inline-block;margin-top:4px;font-size:10px;letter-spacing:.4px;color:var(--dim);padding:2px 8px;border-radius:20px;border:1px solid var(--line);background:var(--panel)}
.by b{color:var(--txt);font-weight:800;text-shadow:0 0 10px #ffffff66}
[data-theme=light] .by b{text-shadow:none}
.newchat{display:flex;justify-content:space-between;width:100%;font-weight:650;padding:10px 12px;border-color:#3a3a3d}
.newchat span{display:flex;align-items:center;gap:8px}
.search{width:100%;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:7px 10px;outline:none;font-size:12.5px}
.search:focus{border-color:var(--dim)}
.lbl{font-size:10px;color:var(--dim2);font-weight:750;letter-spacing:1.4px;padding:4px 8px 0}
.chats{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:2px;min-height:0}
.chat{display:flex;align-items:center;gap:9px;padding:8px 10px;border-radius:9px;color:var(--dim);cursor:pointer;font-size:13px;border:1px solid transparent}
.chat:hover{background:var(--panel)}.chat.on{background:var(--panel2);color:var(--txt);border-color:var(--line)}
.chat .t{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chat .x{opacity:0;border:0;background:none;padding:2px;color:var(--dim2)}.chat:hover .x{opacity:1}.chat .x:hover{color:var(--bad)}
.none{color:var(--dim2);font-size:12px;padding:8px 10px}
.proj{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:11px}
.proj .h{font-size:10px;letter-spacing:1.2px;color:var(--dim2);font-weight:750;margin-bottom:6px}
.proj .p{font:11.5px/1.45 Consolas,Menlo,monospace;overflow-wrap:anywhere;margin-bottom:9px}
.conn{display:flex;align-items:center;gap:8px;color:var(--dim);font-size:11px;padding:2px 6px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--warn);box-shadow:0 0 10px var(--warn)}.dot.on{background:var(--ok);box-shadow:0 0 10px var(--ok)}.dot.off{background:var(--bad);box-shadow:0 0 10px var(--bad)}
.sig{font-size:10px;color:var(--dim2);text-align:center;padding-top:2px}.sig b{color:var(--txt)}

main{display:flex;flex-direction:column;min-width:0;min-height:0;background:radial-gradient(ellipse at 50% -30%,#ffffff0d,transparent 55%),var(--bg)}
[data-theme=light] main{background:var(--bg)}
.top{height:58px;flex:none;display:flex;align-items:center;gap:12px;padding:0 18px;border-bottom:1px solid var(--line)}
.ib{padding:6px 8px}
.crumb{color:var(--dim);font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:28vw}.crumb b{color:var(--txt);font-weight:600}
.tabs{display:flex;gap:3px;background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:3px;margin-left:8px}
.tab{border:0;background:none;padding:5px 13px;border-radius:8px;color:var(--dim);font-size:12.5px}
.tab.on{background:var(--panel2);color:var(--txt);box-shadow:0 0 0 1px var(--line)}
.sp{flex:1}
.model{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:6px 13px;font-size:11.5px;width:230px;outline:none;font-family:Consolas,monospace}
.model:focus{border-color:var(--dim)}
.view{flex:1;min-height:0;display:flex;flex-direction:column}

.scroll{flex:1;overflow-y:auto;padding:30px 24px 10px;scroll-behavior:smooth}
.wrap{width:min(840px,100%);margin:0 auto}
.welcome{margin-top:6vh}
.welcome .spark{margin-bottom:14px;color:var(--txt);filter:drop-shadow(0 0 10px #ffffff88)}
.welcome h1{font-size:38px;letter-spacing:-1.6px;margin:0 0 10px;font-weight:740;line-height:1.1}
.welcome h1 span{background:linear-gradient(90deg,#fff,#7d7d83);-webkit-background-clip:text;background-clip:text;color:transparent}
[data-theme=light] .welcome h1 span{background:linear-gradient(90deg,#000,#777);-webkit-background-clip:text;background-clip:text}
.welcome p{margin:0;color:var(--dim);max-width:600px}
.sug{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:26px}
.sg{text-align:left;background:var(--panel);border-radius:13px;padding:14px;border:1px solid var(--line);display:block}
.sg:hover{background:var(--panel2);transform:translateY(-1px)}
.sg b{display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:4px}.sg span{font-size:11.5px;color:var(--dim)}
.msg{display:flex;gap:13px;margin-bottom:24px;animation:in .25s ease}
@keyframes in{from{opacity:0;transform:translateY(6px)}}
.av{flex:none;width:30px;height:30px;border-radius:10px;display:grid;place-items:center;font-size:12px;font-weight:700;background:var(--panel2);border:1px solid var(--line)}
.msg.user .av{color:var(--dim)}
.mb{flex:1;min-width:0}
.who{font-size:11px;color:var(--dim);margin:3px 0 6px;display:flex;gap:10px;align-items:center}
.who .cb{opacity:.75;border:0;background:none;padding:0;color:var(--dim2);font-size:11px}.msg:hover .cb{opacity:1}.cb:hover{color:var(--txt)}
.msg.user .tx{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--panel);border:1px solid var(--line);border-radius:4px 14px 14px 14px;padding:10px 14px;display:inline-block;max-width:100%}
.tx{overflow-wrap:anywhere}
.tx p{margin:0 0 10px}.tx h2,.tx h3,.tx h4,.tx h5{margin:16px 0 8px;letter-spacing:-.3px}.tx h2{font-size:20px}.tx h3{font-size:17px}.tx h4,.tx h5{font-size:15px}
.tx ul,.tx ol{margin:0 0 10px;padding-left:22px}.tx li{margin:2px 0}
.tx blockquote{margin:0 0 10px;padding:4px 14px;border-left:3px solid var(--dim);color:var(--dim)}
.tx hr{border:0;border-top:1px solid var(--line);margin:14px 0}
.tx a{color:var(--txt);text-decoration:underline}
.tx code{background:var(--code);border:1px solid var(--line);padding:1px 6px;border-radius:6px;font:12.5px Consolas,Menlo,monospace}
.tool{font:11.5px/1.5 Consolas,Menlo,monospace;color:var(--dim);background:var(--accsoft);border-left:2px solid var(--dim);padding:3px 10px;margin:3px 0;border-radius:0 7px 7px 0;white-space:pre-wrap}
.cbk{margin:10px 0;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--code)}
.cbk .hd{display:flex;justify-content:space-between;align-items:center;padding:5px 10px 5px 14px;background:var(--panel);border-bottom:1px solid var(--line);font:11px Consolas,monospace;color:var(--dim)}
.cbk .hd button{padding:2px 9px;font-size:11px;border-radius:7px}
.cbk pre{margin:0;padding:12px 14px;overflow-x:auto;font:12.5px/1.55 Consolas,Menlo,monospace;tab-size:4}
.cbk pre code{background:none;border:0;padding:0;font:inherit}
.k{color:#fff;font-weight:700}.s{color:#8fd19e}.c{color:#6b6b73;font-style:italic}.n{color:#e0b878}
[data-theme=light] .k{color:#000}[data-theme=light] .s{color:#198038}[data-theme=light] .n{color:#b85c00}
.caret{display:inline-block;width:8px;height:15px;background:var(--txt);margin-left:3px;vertical-align:-2px;border-radius:2px;animation:bl 1s steps(2) infinite}
@keyframes bl{50%{opacity:0}}
.think{color:var(--dim);font-size:12.5px;display:flex;align-items:center;gap:8px}
.spin{width:13px;height:13px;border:2px solid var(--line);border-top-color:var(--txt);border-radius:50%;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}

.comp{flex:none;padding:6px 24px 14px}
.box{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:11px 12px 9px;box-shadow:var(--shadow);transition:.15s}
.box:focus-within{border-color:#6a6a70;box-shadow:0 0 0 3px var(--accsoft),var(--shadow)}
textarea{width:100%;resize:none;background:none;border:0;outline:0;min-height:50px;max-height:200px;padding:3px;color:var(--txt)}
textarea::placeholder{color:var(--dim2)}
.cb2{display:flex;justify-content:space-between;align-items:center;margin-top:6px;gap:10px}
.hint{font-size:10.5px;color:var(--dim2)}
.send{border:0;border-radius:10px;background:#f2f2f2;color:#000;font-weight:750;padding:8px 16px;box-shadow:0 0 18px #ffffff30}
[data-theme=light] .send{background:#111;color:#fff;box-shadow:none}
.send.stop{background:#d64560;color:#fff;box-shadow:0 0 18px #d6456055}
.foot{text-align:center;color:var(--dim2);font-size:10.5px;margin-top:9px}.foot b{color:var(--txt)}

.split{flex:1;display:grid;grid-template-columns:290px 1fr;min-height:0}
.side{border-right:1px solid var(--line);overflow:auto;padding:10px;font-size:13px}
.view-r{display:flex;flex-direction:column;min-width:0;min-height:0}
.fh{display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid var(--line);font:12px Consolas,monospace;color:var(--dim)}
.fb{flex:1;overflow:auto;display:grid;grid-template-columns:auto 1fr;align-content:start;font:12.5px/1.6 Consolas,Menlo,monospace;background:var(--code)}
.gut{padding:12px 10px 12px 16px;text-align:right;color:var(--dim2);user-select:none;border-right:1px solid var(--line);white-space:pre}
.cod{padding:12px 16px;white-space:pre;tab-size:4}
.empty{display:grid;place-items:center;height:100%;color:var(--dim2);font-size:13px;text-align:center;padding:20px}
.row{display:flex;align-items:center;gap:8px;padding:4px 8px;border-radius:7px;cursor:pointer;color:var(--dim);white-space:nowrap}
.row:hover{background:var(--panel)}.row.on{background:var(--panel2);color:var(--txt)}
ul.tree{list-style:none;margin:0;padding-left:14px}ul.tree.root{padding-left:0}
.st{font:700 10px Consolas,monospace;width:20px;text-align:center;border-radius:5px;padding:1px 0}
.st.M{color:var(--warn);background:#e2a84c22}.st.A,.st.\?{color:var(--ok);background:#54d69b22}.st.D{color:var(--bad);background:#ef6b7b22}.st.R{color:var(--txt);background:var(--accsoft)}
.dl{display:block;padding:0 16px}.dl.a{background:#54d69b18;color:var(--ok)}.dl.d{background:#ef6b7b18;color:var(--bad)}.dl.h{background:var(--accsoft);color:var(--dim)}
.banner{background:#ef6b7b1c;border:1px solid #ef6b7b55;color:var(--bad);border-radius:10px;padding:9px 13px;margin-bottom:16px;font-size:12.5px}
.box{position:relative}
.mode{font-size:11px;padding:3px 10px;border-radius:20px;color:var(--dim);white-space:nowrap}
.mode.plan{color:var(--warn);border-color:#e2a84c66}
.slash{position:absolute;left:0;right:0;bottom:calc(100% + 8px);background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:5px;box-shadow:var(--shadow);z-index:10;max-height:270px;overflow:auto}
.slash .it{display:flex;gap:12px;align-items:baseline;padding:7px 10px;border-radius:8px;cursor:pointer;font-size:13px}
.slash .it b{font:600 12.5px Consolas,Menlo,monospace;min-width:96px}
.slash .it span{color:var(--dim);font-size:12px}
.slash .it.on,.slash .it:hover{background:var(--panel2)}
.banner.info{background:var(--accsoft);border-color:var(--line);color:var(--txt);display:flex;align-items:center;justify-content:space-between;gap:12px}
@media(max-width:820px){.app{grid-template-columns:1fr}.sb{display:none}.sug{grid-template-columns:1fr}.model{width:150px}.welcome h1{font-size:30px}}
</style></head><body>
<div class="app" id="app">
<aside class="sb">
  <div class="brand"><div class="logo"><i data-i="cloud" data-s="22"></i></div><div><div class="bn">cloud code</div><div class="by">by <b>m3lf1x</b></div></div></div>
  <button class="newchat" onclick="newChat()"><span><i data-i="plus" data-s="15"></i>Новый чат</span><kbd id="k1">Ctrl K</kbd></button>
  <input class="search" id="q" placeholder="Поиск по чатам…" oninput="renderChats()">
  <div class="lbl">ЧАТЫ</div>
  <div class="chats" id="chats"></div>
  <div class="proj"><div class="h">ПРОЕКТ</div><div class="p" id="cwd">…</div><div style="display:flex;gap:6px"><button onclick="chooseFolder()" style="flex:1;font-size:12px">Выбрать папку<i data-i="ext" data-s="13"></i></button><button onclick="api().open_folder()" title="Открыть папку проекта" style="padding:6px 9px"><i data-i="folder" data-s="14"></i></button></div></div>
  <div class="conn"><span class="dot" id="dot"></span><span id="st">Проверка opencode…</span></div>
  <div class="sig" id="sig">Cloud Code <b>by m3lf1x</b></div>
</aside>
<main>
  <header class="top">
    <button class="ib" onclick="toggleSb()" title="Панель (Ctrl+B)"><i data-i="menu" data-s="17"></i></button>
    <div class="crumb"><span id="pn">project</span> <span style="color:var(--dim2)">/</span> <b id="ct">Новый диалог</b></div>
    <div class="tabs">
      <button class="tab on" data-t="chat" onclick="tab('chat')">Чат</button>
      <button class="tab" data-t="files" onclick="tab('files')">Файлы</button>
      <button class="tab" data-t="diff" onclick="tab('diff')">Изменения</button>
    </div>
    <div class="sp"></div>
    <input class="model" id="model" list="ml" placeholder="модель: авто (бесплатная)" onchange="S.cfgSet('model',this.value)">
    <datalist id="ml"></datalist>
    <button class="ib" onclick="loadModels()" title="Обновить список моделей"><i data-i="refresh" data-s="16"></i></button>
    <button class="ib" onclick="exportChat()" title="Экспорт чата в .md"><i data-i="download" data-s="16"></i></button>
    <button class="ib" onclick="theme()" title="Тема" id="th"></button>
  </header>

  <section class="view" id="v-chat">
    <div class="scroll" id="sc"><div class="wrap">
      <div id="banner"></div>
      <div class="welcome" id="welcome">
        <div class="spark"><i data-i="spark" data-s="32"></i></div>
        <h1>Что создадим <span>сегодня?</span></h1>
        <p>Бесплатный AI-разработчик. Опиши задачу обычным языком — Cloud Code изучит проект, напишет код и внесёт изменения прямо в файлы через opencode.</p>
        <div class="sug">
          <button class="sg" onclick="use('Изучи структуру этого проекта и коротко объясни, как он работает.')"><b><i data-i="search" data-s="15"></i>Изучи проект</b><span>Структура, стек и точки входа</span></button>
          <button class="sg" onclick="use('Найди ошибки и потенциальные баги в проекте и исправь их.')"><b><i data-i="bolt" data-s="15"></i>Найди и исправь ошибки</b><span>Ревью кода с правками</span></button>
          <button class="sg" onclick="use('Создай современный адаптивный интерфейс для этого проекта.')"><b><i data-i="shape" data-s="15"></i>Создай интерфейс</b><span>Красивый адаптивный UI</span></button>
          <button class="sg" onclick="use('Напиши README с описанием, установкой и примерами запуска для этого проекта.')"><b><i data-i="pen" data-s="15"></i>Напиши README</b><span>Документация проекта</span></button>
        </div>
      </div>
      <div id="msgs"></div>
    </div></div>
    <div class="comp"><div class="wrap">
      <div class="box">
        <div id="slash" class="slash hidden"></div>
        <textarea id="inp" rows="2" placeholder="Что сделать в проекте?  Можно упомянуть файл через вкладку «Файлы»…"></textarea>
        <div class="cb2"><span style="display:flex;align-items:center;gap:12px;min-width:0"><button class="mode" id="mode" onclick="toggleMode()"></button><span class="hint" id="hint"></span></span>
        <button class="send" id="btn" onclick="act()"></button></div>
      </div>
      <div class="foot">Cloud Code <b>by m3lf1x</b> · работает на opencode · бесплатные модели без ключа</div>
    </div></div>
  </section>

  <section class="view hidden" id="v-files"><div class="split">
    <div class="side"><ul class="tree root" id="tree"></ul></div>
    <div class="view-r" id="fv"><div class="empty">Выбери файл слева</div></div>
  </div></section>

  <section class="view hidden" id="v-diff"><div class="split">
    <div class="side" id="gl"></div>
    <div class="view-r" id="dv"><div class="empty">Выбери файл слева, чтобы увидеть изменения</div></div>
  </div></section>
</main>
</div>
<script>
const $=id=>document.getElementById(id);
const esc=s=>s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
const api=()=>window.pywebview.api;
const S={chats:[],cur:null,cfg:{},busy:false,last:null,stream:null,t0:0,timer:null,raf:0,
  cfgSet(k,v){S.cfg[k]=v;try{api().set_cfg(k,v)}catch(e){}}};

/* ---------- иконки ---------- */
const P={
cloud:'<path d="M7 19a4.5 4.5 0 0 1-.6-8.96A6 6 0 0 1 17.6 9 4.8 4.8 0 0 1 18 19z"/>',
menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
plus:'<path d="M12 5v14M5 12h14"/>',
refresh:'<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
moon:'<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
chat:'<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
folder:'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
file:'<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
x:'<path d="M6 6l12 12M18 6L6 18"/>',
check:'<path d="M5 12l5 5L20 7"/>',
up:'<path d="M12 19V5M5 12l7-7 7 7"/>',
stop:'<rect x="7" y="7" width="10" height="10" rx="1.5"/>',
search:'<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
bolt:'<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
shape:'<path d="M12 3l9 9-9 9-9-9z"/>',
pen:'<path d="M4 20l4-1 11-11-3-3L5 16z"/>',
spark:'<path d="M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6L5.6 18.4"/>',
warn:'<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.01"/>',
at:'<circle cx="12" cy="12" r="3.5"/><path d="M15.5 12v1.5a2.5 2.5 0 0 0 5 0V12a8.5 8.5 0 1 0-3.4 6.8"/>',
ext:'<path d="M7 17L17 7M8 7h9v9"/>',
download:'<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>'};
const ic=(n,s=16)=>'<svg width="'+s+'" height="'+s+'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+(P[n]||"")+'</svg>';
document.querySelectorAll("[data-i]").forEach(e=>{e.outerHTML=ic(e.dataset.i,+e.dataset.s||16)});
if(/Mac/i.test(navigator.platform))$("k1").textContent="Cmd K";
const HINT='<kbd>Enter</kbd> отправить · <kbd>Shift+Enter</kbd> перенос · <kbd>Esc</kbd> стоп · <kbd>/</kbd> команды';
$("hint").innerHTML=HINT;$("btn").innerHTML="Отправить"+ic("up",15);

/* ---------- копирование ---------- */
async function copyText(t){
  try{if(await api().copy(t))return}catch(e){}
  try{await navigator.clipboard.writeText(t);return}catch(e){}
  const a=document.createElement("textarea");a.value=t;a.style.cssText="position:fixed;opacity:0";document.body.append(a);a.select();document.execCommand("copy");a.remove();
}
function copyCode(b){copyText(b.closest(".cbk").querySelector("code").innerText);const o=b.textContent;b.textContent="скопировано";setTimeout(()=>b.textContent=o,1100)}
function copyMsg(b,i){const c=cur();copyText(c.msgs[i].text);b.textContent="готово";setTimeout(()=>b.textContent="копировать",1000)}

/* ---------- подсветка и markdown ---------- */
const KW="function|const|let|var|return|if|else|elif|for|while|class|def|import|from|export|default|async|await|try|except|catch|finally|new|this|self|true|false|null|None|True|False|in|of|not|and|or|is|lambda|with|as|yield|raise|throw|switch|case|break|continue|public|private|static|void|int|string|bool|fn|mut|use|pub|struct|impl|interface|type|enum|package|func|go|defer";
function hl(code,lang){
  const hash=/^(py|python|sh|bash|shell|yaml|yml|toml|rb|ruby|ps1|powershell|dockerfile|conf|ini)$/i.test(lang||"");
  const re=new RegExp("("+(hash?"#[^\\n]*":"\\/\\/[^\\n]*|\\/\\*[\\s\\S]*?\\*\\/")+")|(\"(?:\\\\.|[^\"\\\\\\n])*\"|'(?:\\\\.|[^'\\\\\\n])*'|`(?:\\\\.|[^`\\\\])*`)|\\b("+KW+")\\b|\\b(\\d+(?:\\.\\d+)?)\\b","g");
  return esc(code).replace(re,(m,c,s,k,n)=>c?'<span class="c">'+c+'</span>':s?'<span class="s">'+s+'</span>':k?'<span class="k">'+k+'</span>':'<span class="n">'+n+'</span>');
}
function inl(s){
  s=esc(s);const cs=[];
  s=s.replace(/`([^`\n]+)`/g,(m,c)=>{cs.push(c);return "\u0000"+(cs.length-1)+"\u0000"});
  s=s.replace(/\*\*([^*\n]+)\*\*/g,"<b>$1</b>").replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g,"$1<i>$2</i>")
   .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,'<a href="$2" target="_blank">$1</a>');
  return s.replace(/\u0000(\d+)\u0000/g,(m,i)=>"<code>"+cs[i]+"</code>");
}
function blk(t){
  let o="",list=null,para=[],m;
  const fp=()=>{if(para.length){o+="<p>"+para.join("<br>")+"</p>";para=[]}},fl=()=>{if(list){o+="</"+list+">";list=null}};
  for(const l of t.split("\n")){
    if(!l.trim()){fp();fl();continue}
    if(/^(\|\s|→\s|←\s|✱\s)/.test(l)){fp();fl();o+='<div class="tool">'+esc(l)+'</div>';continue}
    if(m=l.match(/^(#{1,4})\s+(.*)/)){fp();fl();const n=m[1].length+1;o+="<h"+n+">"+inl(m[2])+"</h"+n+">";continue}
    if(m=l.match(/^\s*[-*•]\s+(.*)/)){fp();if(list!=="ul"){fl();o+="<ul>";list="ul"}o+="<li>"+inl(m[1])+"</li>";continue}
    if(m=l.match(/^\s*\d+[.)]\s+(.*)/)){fp();if(list!=="ol"){fl();o+="<ol>";list="ol"}o+="<li>"+inl(m[1])+"</li>";continue}
    if(m=l.match(/^>\s?(.*)/)){fp();fl();o+="<blockquote>"+inl(m[1])+"</blockquote>";continue}
    if(/^(---+|\*\*\*+)$/.test(l.trim())){fp();fl();o+="<hr>";continue}
    fl();para.push(inl(l));
  }
  fp();fl();return o;
}
function md(src){
  return src.split("```").map((p,i)=>{
    if(i%2){
      const nl=p.indexOf("\n"),lang=nl>=0?p.slice(0,nl).trim():"",code=(nl>=0?p.slice(nl+1):p).replace(/\n$/,"");
      return '<div class="cbk"><div class="hd"><span>'+esc(lang||"код")+'</span><button onclick="copyCode(this)">копировать</button></div><pre><code>'+hl(code,lang)+'</code></pre></div>';
    }
    return blk(p);
  }).join("");
}

/* ---------- чаты ---------- */
const cur=()=>S.chats.find(c=>c.id===S.cur);
let svT;function save(){clearTimeout(svT);svT=setTimeout(()=>{try{api().save_chats(JSON.stringify(S.chats))}catch(e){}},350)}
function newChat(){
  tab("chat");
  const c=cur();if(c&&!c.msgs.length){$("inp").focus();return}
  const n={id:Date.now().toString(36),title:"Новый чат",msgs:[],ts:Date.now()};
  S.chats.unshift(n);S.cur=n.id;save();renderChats();renderMsgs();$("inp").focus();
}
function openChat(id){S.cur=id;tab("chat");renderChats();renderMsgs()}
function delChat(id,e){
  e.stopPropagation();if(S.busy&&S.stream&&S.stream.c.id===id)return;
  S.chats=S.chats.filter(c=>c.id!==id);if(S.cur===id)S.cur=S.chats[0]?S.chats[0].id:null;
  if(S.last===id)S.last=null;save();renderChats();renderMsgs();
}
function renderChats(){
  const q=$("q").value.toLowerCase(),L=S.chats.filter(c=>c.msgs.length&&c.title.toLowerCase().includes(q));
  $("chats").innerHTML=L.length?L.map(c=>'<div class="chat'+(c.id===S.cur?" on":"")+'" onclick="openChat(\''+c.id+'\')">'+ic("chat",14)+'<span class="t">'+esc(c.title)+'</span><button class="x" onclick="delChat(\''+c.id+'\',event)">'+ic("x",13)+'</button></div>').join(""):'<div class="none">'+(q?"Ничего не найдено":"Пока нет чатов")+'</div>';
  const c=cur();$("ct").textContent=c&&c.msgs.length?c.title:"Новый диалог";
}
function msgEl(m,i){
  const d=document.createElement("div");d.className="msg "+m.role;
  const u=m.role==="user";
  const cm=cur(),lastA=!u&&!S.busy&&cm&&i===cm.msgs.length-1&&i>0;
  d.innerHTML='<div class="av">'+(u?"Я":ic("spark",15))+'</div><div class="mb"><div class="who">'+(u?"Вы":"Cloud Code")+(m.sec?'<span>· '+m.sec+' с</span>':'')+(u?"":'<button class="cb" onclick="copyMsg(this,'+i+')">копировать</button>')+(lastA?'<button class="cb" onclick="regen()">повторить</button>':'')+'</div><div class="tx"></div></div>';
  const tx=d.querySelector(".tx");
  if(u)tx.textContent=m.text;else tx.innerHTML=md(m.text);
  return d;
}
function renderMsgs(){
  const c=cur(),box=$("msgs");box.innerHTML="";
  $("welcome").classList.toggle("hidden",!!(c&&c.msgs.length));
  if(!c)return;
  c.msgs.forEach((m,i)=>box.append(msgEl(m,i)));
  if(S.busy&&S.stream&&S.stream.c===c){S.stream.body=box.lastElementChild.querySelector(".tx");paint()}
  bottom(true);
}
function bottom(force){const s=$("sc");if(force||s.scrollHeight-s.scrollTop-s.clientHeight<140)s.scrollTop=s.scrollHeight}
function use(t){$("inp").value=t;grow();$("inp").focus()}
function toast(t){$("hint").textContent=t;setTimeout(()=>{if(!S.busy)$("hint").innerHTML=HINT},2800)}
function regen(){
  const c=cur();if(S.busy||!c||c.msgs.length<2)return;
  const u=c.msgs[c.msgs.length-2];if(u.role!=="user")return;
  c.msgs.splice(-2);$("inp").value=u.text;renderMsgs();send();
}
async function exportChat(){
  const c=cur();if(!c||!c.msgs.length){toast("Нечего экспортировать");return}
  const t="# "+c.title+"\n\n"+c.msgs.map(m=>(m.role==="user"?"**Вы:**\n\n":"**Cloud Code:**\n\n")+m.text).join("\n\n---\n\n")+"\n";
  const r=await api().export_chat(c.title,t);if(r)toast("Сохранено: "+r);
}
function setMode(){
  const b=$("mode"),p=S.mode==="plan";
  b.textContent=p?"Режим: план (только чтение)":"Режим: сборка";b.classList.toggle("plan",p);
  b.title="Переключить режим. План: агент только анализирует и ничего не меняет в файлах";
}
function toggleMode(){S.mode=S.mode==="plan"?"build":"plan";setMode();S.cfgSet("mode",S.mode)}
const CMDS=[
["/объясни","Объяснить проект","Объясни, как устроен этот проект: структура, стек, ключевые файлы и как всё запускается."],
["/ошибки","Найти и исправить ошибки","Найди ошибки и потенциальные баги в проекте и исправь их."],
["/ревью","Ревью кода без изменений","Проведи ревью кода: проблемы, безопасность, читаемость. Ничего не меняй, дай только список замечаний с приоритетами."],
["/тесты","Написать тесты","Напиши тесты для основного кода проекта и, если возможно, запусти их."],
["/рефактор","Упростить код","Упрости и отрефактори код, не меняя поведение. Объясни, что изменил."],
["/readme","Написать README","Напиши README с описанием, установкой и примерами запуска для этого проекта."],
["/коммит","Сообщение коммита","Посмотри текущие изменения (git diff) и предложи понятное сообщение коммита."],
["/план","Составить план","Составь пошаговый план реализации задачи, ничего не изменяя в файлах. Задача: "]];
let SL=[],SI=0;
function slashDraw(){
  const p=$("slash");
  p.innerHTML=SL.map((c,i)=>'<div class="it'+(i===SI?" on":"")+'" onmousedown="pick('+i+')"><b>'+c[0]+'</b><span>'+esc(c[1])+'</span></div>').join("");
}
function slash(){
  const v=$("inp").value,p=$("slash");
  if(!v.startsWith("/")||/\s/.test(v)){p.classList.add("hidden");SL=[];return}
  SL=CMDS.filter(c=>c[0].startsWith(v.toLowerCase()));SI=0;
  if(!SL.length){p.classList.add("hidden");return}
  p.classList.remove("hidden");slashDraw();
}
function pick(i){const c=SL[i];if(!c)return;$("inp").value=c[2];$("slash").classList.add("hidden");SL=[];grow();$("inp").focus()}

/* ---------- отправка и поток ---------- */
function ctxOf(c){
  if(!c.msgs.length)return "";
  let t="";for(const m of c.msgs.slice(-12))t+=(m.role==="user"?"Пользователь: ":"Ассистент: ")+m.text.slice(0,3500)+"\n\n";
  return "Это продолжение диалога. История предыдущих сообщений (учитывай её как контекст, не повторяй):\n"+t.slice(-16000);
}
function setBusy(b){
  S.busy=b;const bt=$("btn");bt.innerHTML=b?ic("stop",14)+"Стоп":"Отправить"+ic("up",15);bt.classList.toggle("stop",b);
  clearInterval(S.timer);
  if(b){S.t0=Date.now();const f=()=>{$("hint").innerHTML='<span class="think"><span class="spin"></span>Работаю · '+Math.floor((Date.now()-S.t0)/1000)+' с</span>'};f();S.timer=setInterval(f,500)}
  else $("hint").innerHTML=HINT;
}
function act(){S.busy?stop():send()}
function stop(){if(S.busy){S.stopped=true;api().stop()}}
function send(){
  const t=$("inp").value.trim();if(!t||S.busy)return;
  if(!cur()){S.chats.unshift({id:Date.now().toString(36),title:"Новый чат",msgs:[],ts:Date.now()});S.cur=S.chats[0].id}
  const c=cur(),cont=false,ctx=ctxOf(c);
  c.msgs.push({role:"user",text:t});if(c.msgs.length===1)c.title=t.replace(/\s+/g," ").slice(0,48);
  const am={role:"assistant",text:""};c.msgs.push(am);c.ts=Date.now();
  $("inp").value="";grow();S.stopped=false;
  S.stream={c,am,body:null};setBusy(true);renderChats();renderMsgs();save();
  api().send(t,$("model").value,cont,ctx,S.mode==="plan"?"plan":"");
}
function paint(){
  const s=S.stream;if(!s||!s.body)return;
  s.body.innerHTML=(s.am.text?md(s.am.text):"")+'<span class="caret"></span>';
}
function onChunk(t){
  const s=S.stream;if(!s)return;s.am.text+=t;
  if(!S.raf)S.raf=requestAnimationFrame(()=>{S.raf=0;paint();bottom()});
}
function onError(e){const s=S.stream;if(s)s.am.text+=(s.am.text?"\n\n":"")+"Ошибка: "+e}
function onDone(rc){
  const s=S.stream;if(!s)return;
  if(S.stopped)s.am.text+=(s.am.text?"\n\n":"")+"_Остановлено_";
  else if(!s.am.text.trim())s.am.text="Пустой ответ. Проверь, что выбрана рабочая модель (кнопка обновления рядом с полем модели) и интернет доступен.";
  if(rc===0&&!S.stopped)S.last=s.c.id;else if(S.stopped)S.last=null;
  if(!S.stopped)s.am.sec=Math.round((Date.now()-S.t0)/1000);
  if(s.body)s.body.innerHTML=md(s.am.text);
  S.stream=null;setBusy(false);renderMsgs();save();$("inp").focus();
}

/* ---------- ввод ---------- */
function grow(){const t=$("inp");t.style.height="auto";t.style.height=Math.min(t.scrollHeight,200)+"px"}
$("inp").addEventListener("input",()=>{grow();slash()});
$("inp").addEventListener("keydown",e=>{
  if(SL.length){
    if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();SI=(SI+(e.key==="ArrowDown"?1:-1)+SL.length)%SL.length;slashDraw();return}
    if(e.key==="Tab"||(e.key==="Enter"&&!e.shiftKey)){e.preventDefault();pick(SI);return}
    if(e.key==="Escape"){$("slash").classList.add("hidden");SL=[];return}
  }
  if(e.key==="Enter"&&!e.shiftKey&&!e.isComposing){e.preventDefault();send()}
});
document.addEventListener("keydown",e=>{
  if(e.key==="Escape")stop();
  if(e.ctrlKey||e.metaKey){
    if(e.key==="k"){e.preventDefault();newChat()}
    if(e.key==="b"){e.preventDefault();toggleSb()}
    if(e.key==="1")tab("chat");if(e.key==="2")tab("files");if(e.key==="3")tab("diff");
  }
});

/* ---------- интерфейс ---------- */
function toggleSb(){$("app").classList.toggle("collapsed")}
function theme(){const l=document.documentElement.dataset.theme!=="light";setTheme(l?"light":"dark");S.cfgSet("theme",l?"light":"dark")}
function setTheme(t){document.documentElement.dataset.theme=t;$("th").innerHTML=ic(t==="light"?"sun":"moon",16)}
setTheme("dark");setMode();
function tab(n){
  document.querySelectorAll(".tab").forEach(b=>b.classList.toggle("on",b.dataset.t===n));
  ["chat","files","diff"].forEach(v=>$("v-"+v).classList.toggle("hidden",v!==n));
  if(n==="files"&&!$("tree").children.length)loadTree("",$("tree"));
  if(n==="diff")loadGit();
}
function setCwd(p){$("cwd").textContent=p;$("pn").textContent=p.split(/[\\/]/).filter(Boolean).pop()||p}
async function chooseFolder(){
  const p=await api().choose_folder();setCwd(p);S.last=null;
  $("tree").innerHTML="";$("fv").innerHTML='<div class="empty">Выбери файл слева</div>';
  if(!$("v-files").classList.contains("hidden"))loadTree("",$("tree"));
  if(!$("v-diff").classList.contains("hidden"))loadGit();
}
async function loadModels(){
  try{
    const m=await api().models();
    $("ml").innerHTML=m.map(x=>'<option value="'+x+'">').join("");
    if(!$("model").value){const f=m.find(x=>x.startsWith("opencode/")&&x.includes("free"));if(f){$("model").value=f;S.cfgSet("model",f)}}
  }catch(e){}
}

/* ---------- файлы ---------- */
async function loadTree(rel,ul){
  const r=await api().files(rel);
  if(!r.ok){ul.innerHTML='<li class="none">'+esc(r.message)+'</li>';return}
  ul.innerHTML="";
  if(!r.items.length)ul.innerHTML='<li class="none">пусто</li>';
  r.items.forEach(it=>{
    const li=document.createElement("li"),row=document.createElement("div");row.className="row";
    row.innerHTML=ic(it.dir?"folder":"file",14)+'<span>'+esc(it.name)+'</span>';
    li.append(row);
    if(it.dir){
      let sub=null;
      row.onclick=async()=>{
        if(sub){sub.remove();sub=null;return}
        sub=document.createElement("ul");sub.className="tree";li.append(sub);await loadTree(it.rel,sub);
      };
    }else row.onclick=()=>{document.querySelectorAll("#tree .row.on").forEach(x=>x.classList.remove("on"));row.classList.add("on");openFile(it.rel)};
    ul.append(li);
  });
}
async function openFile(rel){
  const r=await api().read_file(rel),v=$("fv");
  if(!r.ok){v.innerHTML='<div class="empty">'+esc(r.message)+'</div>';return}
  const lang=(rel.split(".").pop()||"");
  v.innerHTML='<div class="fh"><span style="flex:1">'+esc(rel)+' · '+(r.size/1024).toFixed(1)+' КБ</span><button onclick="mention(\''+rel.replace(/\\/g,"\\\\").replace(/'/g,"\\'")+'\')">'+ic("at",14)+'Упомянуть в чате</button></div>';
  if(r.note){v.insertAdjacentHTML("beforeend",'<div class="empty">'+esc(r.note)+'</div>');return}
  const n=r.text.split("\n").length;
  const d=document.createElement("div");d.className="fb";
  d.innerHTML='<div class="gut">'+Array.from({length:n},(_,i)=>i+1).join("\n")+'</div><div class="cod">'+hl(r.text,lang)+'</div>';
  v.append(d);
}
function mention(rel){tab("chat");const i=$("inp");i.value+=(i.value&&!i.value.endsWith(" ")?" ":"")+"@"+rel+" ";grow();i.focus()}

/* ---------- git ---------- */
async function loadGit(){
  const r=await api().git(),g=$("gl");
  if(!r.ok){g.innerHTML='<div class="empty">'+esc(r.message)+'</div>';return}
  if(!r.items.length){g.innerHTML='<div class="empty">Изменений нет</div>';return}
  g.innerHTML="";
  r.items.forEach(it=>{
    const row=document.createElement("div");row.className="row";
    row.innerHTML='<span class="st '+esc(it.status[0])+'">'+esc(it.status[0])+'</span><span style="overflow:hidden;text-overflow:ellipsis">'+esc(it.path)+'</span>';
    row.onclick=async()=>{
      g.querySelectorAll(".row.on").forEach(x=>x.classList.remove("on"));row.classList.add("on");
      const t=await api().git_diff(it.path,it.status);
      $("dv").innerHTML='<div class="fh">'+esc(it.path)+'</div><div class="fb" style="display:block;padding:10px 0;white-space:pre">'+
        t.split("\n").map(l=>'<span class="dl '+(l.startsWith("@@")?"h":l.startsWith("+")&&!l.startsWith("+++")?"a":l.startsWith("-")&&!l.startsWith("---")?"d":"")+'">'+(esc(l)||" ")+'</span>').join("")+'</div>';
    };
    g.append(row);
  });
}

/* ---------- старт ---------- */
function setStatus(cls,text){$("dot").className="dot "+cls;$("st").textContent=text}
window.addEventListener("pywebviewready",async()=>{
  try{
    const st=await api().state();S.chats=st.chats.filter(c=>c.msgs&&c.msgs.length);S.cfg=st.cfg;
    setCwd(st.cfg.cwd);setTheme(st.cfg.theme||"dark");if(st.cfg.model)$("model").value=st.cfg.model;
    S.mode=st.cfg.mode==="plan"?"plan":"build";setMode();
    if(st.version)$("sig").innerHTML='Cloud Code <b>by m3lf1x</b> · v'+st.version;
    S.cur=S.chats[0]?S.chats[0].id:null;renderChats();renderMsgs();
  }catch(e){}
  try{
    const r=await api().start();
    if(r.ok){
      setStatus("on","opencode подключён");
      api().version().then(v=>{if(v)$("st").textContent="opencode подключён · v"+v}).catch(()=>{});
      loadModels();
      api().check_update().then(r=>{if(r&&r.new)$("banner").insertAdjacentHTML("beforeend",'<div class="banner info"><span>Доступна новая версия <b>v'+esc(r.version)+'</b></span><button data-u="'+esc(r.url)+'" onclick="api().open_url(this.dataset.u)">Скачать'+ic("ext",13)+'</button></div>')}).catch(()=>{});
    }else{
      setStatus("off","opencode не найден");
      $("banner").innerHTML='<div class="banner">'+esc(r.message)+'</div>';
    }
  }catch(e){setStatus("off","ошибка связи")}
  $("inp").focus();
});
setTimeout(()=>{if($("st").textContent.startsWith("Проверка"))setStatus("off","нет ответа от приложения")},8000);
</script></body></html>"""


def _crash():
    """Окно ошибки через user32 (работает всегда) + лог в ~/.cloud_code/error.log"""
    tb = traceback.format_exc()
    log = APP / "error.log"
    try:
        log.write_text(tb, encoding="utf-8")
    except Exception:
        pass
    if WIN:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, "Cloud Code не удалось запустить.\n\n" + tb[-1000:] + "\n\nЛог: " + str(log),
                                             "Cloud Code", 0x10)
        except Exception:
            pass
    else:
        print(tb)


if __name__ == "__main__":
    try:
        if webview is None:
            raise RuntimeError("Не удалось загрузить pywebview:\n" + _IMPORT_ERR)
        fix_path()
        api = Api()
        api.window = webview.create_window("Cloud Code by m3lf1x", html=HTML, js_api=api,
                                           width=1280, height=820, min_size=(760, 520),
                                           background_color="#000000")
        webview.start()
    except Exception:
        _crash()
