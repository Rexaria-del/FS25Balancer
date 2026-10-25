# -*- coding: utf-8 -*-
"""ИИ-слой: Ollama, классификация страны и ретро-статуса."""

import json, os, re, shutil, subprocess, tempfile, time, urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.countries import ALL_COUNTRIES, country_info
from core.models import BalancerConfig

OLLAMA_HOST = "http://localhost:11434"

AI_BRAND_CACHE: Dict[str, str] = {}

DEFAULT_AI_PROMPT = (
    "Ты — эксперт по классификации модов Farming Simulator 25.\n"
    "Определи СТРАНУ-ПРОИЗВОДИТЕЛЬ и СТАТУС РЕТРО для данной техники.\n\n"
    "Данные мода:\n"
    "  Мод: {mod_name}\n"
    "  Файл: {filename}\n"
    "  Бренд: {brand}\n"
    "  Название: {title}\n\n"
    "РАЗРЕШЁННЫЕ СТРАНЫ (выбери ровно одну, строго из этого списка, "
    "название повторяя символ в символ):\n{countries}\n\n"
    "ПРАВИЛА:\n"
    "1. Учитывай только список выше. Если производитель из списка отсутствует, "
    "укажи наиболее близкую по рынку страну из списка.\n"
    "2. РЕТРО = техника до 1991 года выпуска, советские/постсоветские модели "
    "(Т-40, ДТ-75, К-700, ЗИЛ, ГАЗ-53, МТЗ-50/80, УАЗ-469, КРАЗ, Дон-1500), "
    "а также vintage/classic-реплики. Иначе — MODERN.\n"
    "3. СССР выбирай только для техники советского периода.\n\n"
    "ФОРМАТ ОТВЕТА — ровно одна строка, без пояснений:\n"
    "СТРАНА|RETRO  или  СТРАНА|MODERN\n"
    "Примеры: Россия|RETRO   Германия|MODERN   СССР|RETRO\n"
    "Ответ:"
)


def get_ollama_exe() -> Optional[str]:
    p = shutil.which("ollama")
    if not p:
        win = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
        if os.path.isfile(win):
            p = win
    return p


def check_ollama() -> Tuple[bool, List[str]]:
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=1.0) as r:
            if r.status == 200:
                data = json.loads(r.read().decode("utf-8"))
                return True, [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        pass
    return False, []


def installed_models_disk() -> List[str]:
    """Модели по манифестам на диске: %OLLAMA_MODELS% или ~/.ollama/models.

    Нужен именно обход файлов, потому что /api/tags отвечает пустым, когда служба
    Ollama остановлена, — и дропдаун «готовые к работе» ложно пустел.
    """
    roots = []
    env = os.environ.get("OLLAMA_MODELS")
    if env:
        roots.append(env)
    roots.append(os.path.join(os.path.expanduser("~"), ".ollama", "models"))
    out: List[str] = []
    for root in roots:
        mf = os.path.join(root, "manifests")
        if not os.path.isdir(mf):
            continue
        for dirpath, _dirs, files in os.walk(mf):
            rel = os.path.relpath(dirpath, mf).replace("\\", "/")
            parts = [p for p in rel.split("/") if p]
            if len(parts) < 2:
                continue
            name = "/".join(parts[1:])
            for tag in files:
                out.append(f"{name}:{tag}")
    return sorted(set(out))


def _no_window() -> Dict[str, Any]:
    kw: Dict[str, Any] = {}
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def start_ollama(cb: Callable[[str], None]) -> bool:
    ok, _ = check_ollama()
    if ok:
        return True
    exe = get_ollama_exe()
    if not exe:
        cb("Ollama не найдена.")
        return False
    try:
        env = os.environ.copy()
        env["OLLAMA_NUM_PARALLEL"] = "2"
        subprocess.Popen([exe, "serve"], env=env, **_no_window())
        for _ in range(15):
            ok, _ = check_ollama()
            if ok:
                return True
            time.sleep(1.0)
    except Exception:
        pass
    return False


def stop_ollama(cb: Callable[[str], None]) -> None:
    try:
        if os.name == "nt":
            for p in ("ollama.exe", "ollama_llama_server.exe"):
                subprocess.run(["taskkill", "/f", "/im", p], capture_output=True, **_no_window())
        else:
            subprocess.run(["pkill", "ollama"], capture_output=True)
        cb("Служба ИИ остановлена.")
    except Exception:
        pass


def download_model(name: str, prog_cb: Callable[[Any], None],
                   done_cb: Callable[[str], None]) -> None:
    """Pull через /api/pull (stream): проценты, скорость, прогресс по слоям."""
    if not start_ollama(lambda m: prog_cb({"msg": str(m)})):
        done_cb("Не удалось запустить Ollama.")
        return
    try:
        payload = json.dumps({"name": name, "stream": True}).encode("utf-8")
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/pull", data=payload,
                                     headers={"Content-Type": "application/json"})
        last_bytes, last_t = 0.0, time.time()
        with urllib.request.urlopen(req, timeout=None) as resp:
            for raw in resp:
                try:
                    j = json.loads(raw.decode("utf-8", "ignore"))
                except ValueError:
                    continue
                status = str(j.get("status", ""))
                comp, tot = j.get("completed"), j.get("total")
                info: Dict[str, Any] = {"msg": f"[{name}] {status}"}
                if comp is not None and tot:
                    if comp < last_bytes:
                        last_bytes, last_t = 0.0, time.time()   # новый слой
                    now = time.time()
                    dt = max(now - last_t, 0.05)
                    mbps = max(0.0, comp - last_bytes) / dt / 2 ** 20
                    last_bytes, last_t = comp, now
                    info.update(pct=round(min(100.0, comp / tot * 100), 1),
                                done=comp, total=tot,
                                speed=(f"{mbps:.1f} МБ/с" if mbps < 1000
                                       else f"{mbps / 1024:.2f} ГБ/с"))
                prog_cb(info)
        done_cb(f"✅ Модель '{name}' загружена!")
    except Exception as e:
        done_cb(f"Ошибка: {e}")


def delete_model(name: str, cb: Callable[[str], None],
                 done_cb: Callable[[str], None]) -> None:
    exe = get_ollama_exe()
    if not exe:
        done_cb("Ollama не найдена.")
        return
    try:
        kw = dict(check=True); kw.update(_no_window())
        subprocess.run([exe, "rm", name], **kw)
        done_cb(f"Модель '{name}' удалена.")
    except Exception as e:
        done_cb(f"Ошибка: {e}")


def install_ollama_app(status_cb: Callable[[str], None],
                       done_cb: Callable[[str], None]) -> None:
    url = "https://ollama.com/download/OllamaSetup.exe"
    status_cb("Скачивание Ollama...")
    try:
        tmp = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
        urllib.request.urlretrieve(url, tmp)
        subprocess.Popen([tmp], shell=True)
        done_cb("Инсталлятор Ollama запущен.")
    except Exception as e:
        done_cb(f"Ошибка скачивания: {e}")


def build_prompt(pro_data: Dict[str, Any], countries: List[str], brand: str,
                 title: str, filename: str, mod_name: str) -> str:
    tpl = (pro_data or {}).get("custom_prompt") or DEFAULT_AI_PROMPT
    need = {"countries", "brand", "title", "filename", "mod_name"}
    available = {f for f in re.findall(r"\{(\w+)\}", tpl)}
    if not available or not need.issubset(available):
        tpl = DEFAULT_AI_PROMPT
    return tpl.format(countries=", ".join(countries) if countries else "Любая страна",
                      brand=brand, title=title, filename=filename, mod_name=mod_name)


def _normalize_country(ans: str, allowed: List[str]) -> Optional[str]:
    a = (ans or "").strip().lower()
    if not a:
        return None
    for c in allowed:
        if c.lower() == a:
            return c
    for c in allowed:
        if c.lower() in a or a in c.lower():
            return c
    for c, info in ALL_COUNTRIES.items():
        if info.get("iso2", "").lower() == a and c in allowed:
            return c
    return None


def ask_ai_classification(brand: str, title: str, filename: str, mod_name: str,
                          cfg: BalancerConfig, allowed: List[str]
                          ) -> Tuple[Optional[str], bool, str]:
    """Возвращает (страна, is_retro, причина)."""
    key = f"{cfg.ai_model_name}_{brand}_{title}_{filename}_{mod_name}".lower()
    if key in AI_BRAND_CACHE:
        parts = AI_BRAND_CACHE[key].split("|")
        country = parts[0] if parts else None
        is_retro = len(parts) > 1 and "RETRO" in parts[1].upper()
        return country, is_retro, "Кэш ИИ"

    ok, models = check_ollama()
    if not ok:
        return None, False, "Служба не запущена"
    if not any(cfg.ai_model_name in m for m in models):
        return None, False, f"Модель {cfg.ai_model_name} не найдена"

    from core.ai_state import get_pro_data
    prompt = build_prompt(get_pro_data(), allowed, brand, title, filename, mod_name)

    payload = json.dumps({
        "model": cfg.ai_model_name, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.0, "num_predict": 40},
    }).encode("utf-8")

    req = urllib.request.Request(f"{OLLAMA_HOST}/api/generate", data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20.0) as resp:
            ans = json.loads(resp.read().decode("utf-8")).get("response", "").strip()
        parts = ans.split("|")
        is_retro = len(parts) > 1 and "RETRO" in parts[1].upper()
        country = _normalize_country(parts[0], allowed)
        if country:
            AI_BRAND_CACHE[key] = f"{country}|{'RETRO' if is_retro else 'MODERN'}"
            return country, is_retro, "ИИ-классификация"
        return None, False, f"Вне пула: {ans[:40]}"
    except Exception as e:
        return None, False, str(e)[:60]


def detect_country_and_retro(brand: str, title: str, filename: str, mod_name: str,
                             cfg: BalancerConfig, learned: Dict[str, str]
                             ) -> Tuple[str, str, float, bool, bool, str]:
    """(страна, флаг, коэф, ретро, need_review, причина). Только выбранный пул стран."""
    cb = (brand or "").strip().lower()
    allowed = [c for c in (cfg.selected_countries or []) if c in ALL_COUNTRIES]
    if not allowed:
        return "Неизвестно", "❓", 1.0, False, True, "Нет выбранных стран"

    combined = f"{brand} {title} {filename} {mod_name}".lower()
    tokens = set(re.findall(r"[a-z0-9]+", combined))

    if cb and cb not in ("lizard", "none", "generic", "") and cb in learned:
        country = learned[cb].split("|")[0]
        if country in ALL_COUNTRIES:
            info = country_info(country)
            # Ретро берём из самой позиции, а не из памяти бренда:
            # у одной марки выпускаются и ретро, и современные модели.
            is_retro = check_retro_keywords(combined)
            return country, info["flag"], cfg.multiplier_for(country), is_retro, False, "Память"

    from core.ai_state import get_pro_data
    pro = get_pro_data()
    country_brands = pro.get("country_brands", {}) or {}
    for country in allowed:
        brands_list = [str(b).lower() for b in country_brands.get(country, [])]
        if not brands_list:
            continue
        if tokens & set(brands_list) or any(b in combined for b in brands_list):
            info = country_info(country)
            is_retro = check_retro_keywords(combined)
            return country, info["flag"], cfg.multiplier_for(country), is_retro, False, f"Бренд ({country})"

    kw_retro = check_retro_keywords(combined)
    if cfg.use_local_ai:
        country, is_retro, reason = ask_ai_classification(
            brand, title, filename, mod_name, cfg, allowed)
        if country and country in allowed:
            info = country_info(country)
            return (country, info["flag"], cfg.multiplier_for(country),
                    bool(is_retro or kw_retro), False, reason)
        return ("⚠️ Проверить", "❓", cfg.multiplier_for(allowed[0]),
                kw_retro, True, f"ИИ: {reason}")

    info = country_info(allowed[0])
    return (allowed[0], info["flag"], cfg.multiplier_for(allowed[0]),
            kw_retro, True, "По умолчанию")


RETRO_KEYWORDS = [
    "zil-130", "zil130", "zil-131", "zil-157", "gaz-52", "gaz-53", "gaz-66", "gaz66",
    "gaz-69", "gaz-51", "uaz-469", "uaz469", "uaz-452", "mtz-50", "mtz50",
    "mtz-80", "mtz80", "mtz-82", "dt-75", "dt75", "t-40", "t40", "t-25", "t25",
    "t-16", "t16", "t-150", "k-700", "k700", "k-701", "sk-5", "sk5",
    "don-1500", "don1500", "kraz-255", "kraz255", "maz-500", "kamaz-5320",
    "2pts-4", "pts-4", "soviet", "ussr", "cccp", "советск", "старый",
    "retro", "vintage", "classic", "196", "197", "198",
]


def check_retro_keywords(text: str) -> bool:
    t = (text or "").lower()
    return any(kw in t for kw in RETRO_KEYWORDS)


MODEL_CATALOG = [
    {"name": "qwen2.5:3b", "gb": 1.9, "desc": "лучшее понимание русского, оптимальный старт"},
    {"name": "llama3.2:3b", "gb": 2.0, "desc": "быстрая и лёгкая, для слабых ПК"},
    {"name": "gemma2:2b", "gb": 1.6, "desc": "компактная, для быстрого старта"},
    {"name": "phi3:latest", "gb": 3.8, "desc": "надёжная классификация, средний вес"},
    {"name": "mistral:latest", "gb": 6.1, "desc": "эталонная стабильность, требует ресурсов"},
    {"name": "gemma3:4b", "gb": 3.8, "desc": "новое поколение Google, хорошая русская речь"},
    {"name": "qwen2.5:7b", "gb": 4.7, "desc": "максимальная точность на русском"},
    {"name": "llama3.1:8b", "gb": 4.9, "desc": "флагман Meta для сложных спорных случаев"},
    {"name": "deepseek-r1:1.5b", "gb": 1.1, "desc": "с reasoning, но русским слабее"},
    {"name": "llama3.2:1b", "gb": 0.9, "desc": "самая быстрая из «умных», черновой вариант"},
    {"name": "tinyllama:1.1b", "gb": 0.6, "desc": "сверхлёгкий минимум точности"},
    {"name": "phi3.5:latest", "gb": 3.8, "desc": "улучшенная phi3, многоязычная"},
]


# ранг по качеству именно для нашей задачи (короткая RU-классификация),
# а не по размеру файла
MODEL_RANKS = {"qwen2.5:7b": 96, "llama3.1:8b": 94, "mistral:latest": 90,
               "phi3.5:latest": 80, "gemma3:4b": 78, "phi3:latest": 75,
               "qwen2.5:3b": 70, "llama3.2:3b": 68, "gemma2:2b": 60,
               "deepseek-r1:1.5b": 55, "llama3.2:1b": 45, "tinyllama:1.1b": 35}

_HW_CACHE: Dict[str, Any] = {"ts": 0.0, "hw": None}


def hardware_info(force: bool = False) -> Dict[str, Any]:
    """ОЗУ через GlobalMemoryStatusEx; VRAM: nvidia-smi (CUDA), иначе CIM для AMD."""
    now = time.time()
    if not force and _HW_CACHE["hw"] is not None and now - _HW_CACHE["ts"] < 300:
        return dict(_HW_CACHE["hw"])
    ram_gb = 0.0
    try:
        import ctypes

        class _MSX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        msc = _MSX()
        msc.dwLength = ctypes.sizeof(_MSX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(msc)):
            ram_gb = msc.ullTotalPhys / 1024 ** 3
    except Exception:
        pass
    gpu_gb, gpu_name = 0.0, ""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total,name",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=3, **_no_window())
        if out.returncode == 0 and out.stdout.strip():
            first = out.stdout.strip().splitlines()[0]
            parts = [x.strip() for x in first.split(",")]
            gpu_gb = float(parts[0]) / 1024.0
            gpu_name = parts[1] if len(parts) > 1 else ""
    except Exception:
        pass
    if gpu_gb < 0.5:
        # AMD/Intel: AdapterRAM из CIM (перепадает >4ГБ, поэтому нижняя оценка);
        # официальная GPU-acceleration Ollama на Windows = CUDA, значит для AMD
        # реально важен объём ОЗУ — GPU только подсвечиваем в причине.
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_VideoController | "
                 "Select-Object -First 1 Name,AdapterRAM | ConvertTo-Csv -NoTypeInformation"],
                capture_output=True, text=True, timeout=5, **_no_window())
            rows = [r.strip('"') for r in out.stdout.replace('"', '').splitlines()[1:2]]
            if rows:
                cols = rows[0].split(",")
                if len(cols) >= 2 and cols[1].isdigit():
                    arb = int(cols[1]) / 1024 ** 3
                    nm = cols[0]
                    if arb >= 3.0 and "nvidia" not in nm.lower():
                        gpu_gb, gpu_name = arb, nm
        except Exception:
            pass
    hw = {"ram_gb": round(ram_gb, 1), "gpu_gb": round(gpu_gb, 1), "gpu_name": gpu_name}
    _HW_CACHE.update(ts=now, hw=dict(hw))
    return hw


def recommend_model(hw: Optional[Dict[str, Any]] = None) -> Tuple[str, str, Dict[str, Any]]:
    """(имя, причина, hw) — крупнейшая модель, влезающая в память с запасом."""
    hw = hw or hardware_info()
    budget = max(1.0, hw["ram_gb"] - 3.0)
    if hw["gpu_gb"] >= 3:
        budget = max(budget, min(hw["ram_gb"] - 2.0, hw["gpu_gb"] - 1.0))
    feas = [m for m in MODEL_CATALOG if m["gb"] * 1.2 + 1.0 <= budget]
    best = (max(feas, key=lambda m: (MODEL_RANKS.get(m["name"], 0), m["gb"]))
            if feas else min(MODEL_CATALOG, key=lambda m: m["gb"]))
    reason = (f"ОЗУ {hw['ram_gb']:.0f} ГБ" +
              (f", {hw['gpu_name']} ({hw['gpu_gb']:.0f} ГБ VRAM)" if hw["gpu_gb"] >= 3 else ", дискретной GPU нет — расчёт на ОЗУ"))
    return best["name"], reason, hw


def ollama_ps() -> List[Dict[str, Any]]:
    """Модели, фактически загруженные в память: size vs size_vram => GPU/CPU."""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/ps")
        with urllib.request.urlopen(req, timeout=1.5) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [{"name": m.get("name", ""), "size": float(m.get("size", 0) or 0),
                 "vram": float(m.get("size_vram", 0) or 0),
                 "expires": str(m.get("expires_at", "") or "")}
                for m in data.get("models", [])]
    except Exception:
        return []


def model_catalog() -> Dict[str, Any]:
    ok, models = check_ollama()
    if not models:
        models = installed_models_disk()
    rec, reason, hw = recommend_model()
    cat = [dict(m, size=f"{m['gb']:.1f} ГБ", rank=MODEL_RANKS.get(m["name"], 0))
           for m in MODEL_CATALOG]
    return {"running": ok, "installed": models, "catalog": cat,
            "ollama_installed": bool(get_ollama_exe()),
            "rec": rec, "rec_reason": reason, "hw": hw, "loaded": ollama_ps()}


def _find_ollama_uninstall() -> Optional[Tuple[str, List[str]]]:
    """Ищет запись деинсталлятора Ollama в реестре (HKCU/HKLM)."""
    try:
        import winreg
    except ImportError:
        return None
    BS = chr(92)
    roots = [(winreg.HKEY_CURRENT_USER, ""),
             (winreg.HKEY_LOCAL_MACHINE, ""),
             (winreg.HKEY_LOCAL_MACHINE, "WOW6432Node" + BS)]
    for hive, sub in roots:
        try:
            upath = BS.join(["SOFTWARE", "Microsoft", "Windows", "CurrentVersion", "Uninstall"])
            key = winreg.OpenKey(hive, upath + (BS + sub if sub else ""))
        except OSError:
            continue
        with key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    name = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, name) as sk:
                        disp = str(winreg.QueryValueEx(sk, "DisplayName")[0]).lower()
                        if "ollama" not in disp:
                            continue
                        for val in ("QuietUninstallString", "UninstallString"):
                            try:
                                cmd = winreg.QueryValueEx(sk, val)[0]
                            except OSError:
                                continue
                            cmd = cmd.strip()
                            if cmd.startswith('"'):
                                exe, _, rest = cmd[1:].partition('"')
                                args = rest.split()
                            else:
                                parts = cmd.split()
                                exe, args = parts[0], parts[1:]
                            if os.path.isfile(exe):
                                return exe, args
                except OSError:
                    continue
    return None


def uninstall_ollama(cb: Callable[[str], None]) -> bool:
    cb("Останавливаю службу Ollama…")
    stop_ollama(lambda m: None)
    found = _find_ollama_uninstall()
    if not found:
        cb("Не найден деинсталлятор Ollama в реестре.")
        return False
    exe, args = found
    silent = [a for a in args if a.startswith("/")] or ["/SILENT", "/NORESTART"]
    try:
        subprocess.Popen([exe] + silent, **_no_window())
        cb("Деинсталлятор Ollama запущен — следуй подсказкам (он работает тихо).")
        return True
    except Exception as e:
        cb(f"Не удалось запустить деинсталлятор: {e}")
        return False


def install_ollama_silent(status_cb: Callable[[str], None],
                          done_cb: Callable[[str], None]) -> bool:
    """Тихая установка Ollama (Inno Setup /VERYSILENT) после согласия пользователя."""
    url = "https://ollama.com/download/OllamaSetup.exe"
    status_cb("Скачиваю установщик Ollama (~1 ГБ)…")
    try:
        tmp = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
        if not os.path.isfile(tmp) or os.path.getsize(tmp) < 1000000:
            req = urllib.request.Request(url, headers={"User-Agent": "FS25Balancer"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                got, last_b, last_t = 0, 0, time.time()
                with open(tmp + ".part", "wb") as out:
                    while True:
                        chunk = resp.read(262144)
                        if not chunk:
                            break
                        out.write(chunk)
                        got += len(chunk)
                        now = time.time()
                        if now - last_t >= 0.4:
                            sp = (got - last_b) / (now - last_t) / 2 ** 20
                            status_cb({"msg": f"Загружаю Ollama: {got // 2 ** 20} МБ",
                                       "pct": round(got / total * 100, 1) if total else None,
                                       "done": got, "total": total, "speed": f"{sp:.1f} МБ/с"})
                            last_b, last_t = got, now
            os.replace(tmp + ".part", tmp)
        subprocess.Popen([tmp, "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"], **_no_window())
        for _ in range(240):
            if get_ollama_exe():
                done_cb("Ollama установлена.")
                return True
            time.sleep(1.0)
        done_cb("Установщик Ollama ещё работает — подождите завершения.")
        return False
    except Exception as e:
        done_cb(f"Ошибка скачивания Ollama: {e}")
        return False
