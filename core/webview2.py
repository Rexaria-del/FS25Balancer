# -*- coding: utf-8 -*-
"""WebView2 Runtime: проверка наличия и нативное окно согласия.

pywebview рисует интерфейс на Chromium из WebView2. На чистых Windows 10/11 его
может не быть — без него окно не открывается вообще. Программа объясняет, что это
за компонент, и доскачивает его сама, но только с согласия пользователя.
"""

import os
import sys

RUNTIME_GUID = "{F3017245-79FE-4CCE-8337-30BD39417FFF}"
_CL = r"SOFTWARE\Microsoft\EdgeUpdate\Clients"
_CL64 = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"
_RT = r"SOFTWARE\Microsoft\EdgeWebView\Runtime"
_DL = "https://developer.microsoft.com/microsoft-edge/webview2/"

TXT_TITLE = "FS25 Balancer — WebView2"
TXT_BODY = ("Для работы интерфейса нужен Microsoft Edge WebView2 — компонент, которым Windows "
            "отображает веб-страницы внутри программ.\n\n"
            "Он есть в современных Windows 10/11 (вместе с Edge), но на этом ПК его не нашли.\n"
            "Программа установит его тихо из репозитория Microsoft, затем запустится заново.\n\n"
            "Установить WebView2 сейчас?\n\n"
            "English: Microsoft Edge WebView2 is required to display this app's interface. "
            "It was not found on this PC. Download and install it from Microsoft now? "
            "The app will restart afterwards.")
TXT_DONE = "WebView2 установлен. Программа перезапустится сама."
TXT_FAIL = ("Не удалось установить WebView2 автоматически.\n"
            "Открой страницу официального установщика: " + _DL)


def _reg_version() -> str:
    try:
        import winreg
    except ImportError:
        return ""
    roots = (
        (winreg.HKEY_LOCAL_MACHINE, os.path.join(_CL64, RUNTIME_GUID)),
        (winreg.HKEY_LOCAL_MACHINE, os.path.join(_CL, RUNTIME_GUID)),
        (winreg.HKEY_CURRENT_USER, os.path.join(_CL, RUNTIME_GUID)),
        (winreg.HKEY_CURRENT_USER, _RT),
    )
    for hive, path in roots:
        for access in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ):
            try:
                with winreg.OpenKey(hive, path, 0, access) as k:
                    for name in ("pv", "Version"):
                        try:
                            v = str(winreg.QueryValueEx(k, name)[0]).strip()
                        except OSError:
                            continue
                        if v and v not in ("0", "0.0.0.0"):
                            return v
            except OSError:
                continue
    return ""


def _folder_version() -> str:
    for env in ("%ProgramFiles(x86)%", "%ProgramW6432%", "%ProgramFiles%"):
        root = os.path.join(os.path.expandvars(env), "Microsoft", "EdgeWebView", "Application")
        try:
            if os.path.isdir(root):
                for name in sorted(os.listdir(root)):
                    if os.path.isdir(os.path.join(root, name)):
                        return name
        except OSError:
            continue
    return ""


def is_installed() -> bool:
    """True, если WebView2 Runtime есть в системе (реестр или папка установки)."""
    return bool(_reg_version() or _folder_version())

def _message(text: str, title: str, yes_no: bool = True) -> bool:
    """Нативное окно согласия: до pywebview никакого интерфейса ещё нет."""
    try:
        import ctypes
        u32 = ctypes.windll.user32
        u32.GetForegroundWindow.restype = ctypes.c_void_p
        u32.MessageBoxW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                    ctypes.c_wchar_p, ctypes.c_uint]
        MB_YESNO, MB_OK = 0x04, 0x00
        MB_ICONINFORMATION, MB_ICONWARNING = 0x40, 0x30
        MB_SETFOREGROUND, MB_DEFBUTTON2 = 0x10000, 0x200
        flags = (MB_ICONINFORMATION if yes_no else MB_ICONWARNING) | MB_SETFOREGROUND
        flags |= (MB_YESNO | MB_DEFBUTTON2) if yes_no else MB_OK
        try:
            hwnd = u32.GetForegroundWindow()
        except Exception:
            hwnd = 0
        result = u32.MessageBoxW(hwnd, text, title, flags)
        return result == 6 if yes_no else True
    except Exception:
        try:
            return input("Установить WebView2? [y/N] ").strip().lower() == "y"
        except Exception:
            return False


def _winget() -> str:
    for env in ("%LOCALAPPDATA%", "%ProgramFiles%"):
        p = os.path.join(os.path.expandvars(env), "Microsoft", "WinGet", "Links", "winget.exe")
        if os.path.isfile(p):
            return p
    from shutil import which
    return which("winget") or ""


def install_silent(log=None) -> bool:
    """WinGet либо официальный Microsoft bootstrapper после согласия пользователя."""
    say = log or (lambda m: None)
    import subprocess
    import webbrowser
    exe = _winget()
    if exe:
        say("Устанавливаю WebView2 через WinGet…")
        try:
            p = subprocess.run(
                [exe, "install", "-e", "--id", "Microsoft.EdgeWebView2Runtime",
                 "--accept-source-agreements", "--accept-package-agreements", "--silent"],
                timeout=900, capture_output=True, text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if is_installed():
                return True
            say("WinGet: код %s, %s" % (p.returncode, (p.stdout or p.stderr or "")[:160]))
        except Exception as e:
            say("WinGet не смог установить WebView2: %s" % e)
    else:
        say("WinGet не найден — открою страницу официального установщика")
    try:
        import tempfile
        import urllib.request
        with tempfile.TemporaryDirectory(prefix="fs25-webview2-") as temporary:
            bootstrapper = os.path.join(temporary, "MicrosoftEdgeWebview2Setup.exe")
            say("Скачиваю официальный установщик Microsoft WebView2…")
            request = urllib.request.Request(
                "https://go.microsoft.com/fwlink/p/?LinkId=2124703",
                headers={"User-Agent": "FS25Balancer/16.0"})
            with urllib.request.urlopen(request, timeout=60) as response, open(bootstrapper, "wb") as target:
                import shutil
                shutil.copyfileobj(response, target, length=262144)
            say("Устанавливаю WebView2…")
            subprocess.run([bootstrapper, "/silent", "/install"], timeout=900,
                           capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if is_installed():
                return True
    except Exception as error:
        say("Установка WebView2: %s" % error)
    _message(TXT_FAIL, TXT_TITLE, yes_no=False)
    try:
        webbrowser.open(_DL)
    except Exception:
        pass
    return is_installed()


def ensure(log=None) -> str:
    """'present' | 'installed' | 'declined' | 'failed'. Всегда спрашивает разрешение."""
    say = log or (lambda m: None)
    if is_installed():
        return "present"
    say("WebView2 не найден — запрашиваю согласие на установку")
    if not _message(TXT_BODY, TXT_TITLE, yes_no=True):
        say("Пользователь отказался устанавливать WebView2")
        return "declined"
    if not install_silent(say):
        say("Установка WebView2 не завершилась")
        return "failed"
    say("WebView2 установлен")
    _message(TXT_DONE, TXT_TITLE, yes_no=False)
    return "installed"


def relaunch() -> None:
    """Перезапуск сразу после установки: тот же exe, настройки сохраняются."""
    try:
        import subprocess
        if getattr(sys, "frozen", False):
            exe = sys.executable
            subprocess.Popen([exe] + sys.argv[1:], cwd=os.path.dirname(exe) or None)
        else:
            os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception:
        pass
    os._exit(0)
