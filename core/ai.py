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


def download_model(name: str, prog_cb: Callable[[str], None],
                   done_cb: Callable[[str], None]) -> None:
    exe = get_ollama_exe()
    if not exe:
        done_cb("Сначала установите Ollama!")
        return
    if not start_ollama(prog_cb):
        done_cb("Не удалось запустить Ollama.")
        return
    try:
        kw = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                  encoding="utf-8", errors="ignore")
        kw.update(_no_window())
        proc = subprocess.Popen([exe, "pull", name], **kw)
        for line in proc.stdout or []:
            s = line.strip()
            if s:
                prog_cb(f"⬇ [{name}]: {s}")
        rc = proc.wait()
        done_cb(f"✅ Модель '{name}' загружена!" if rc == 0 else f"Ошибка: код {rc}")
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

    if cfg.use_local_ai:
        country, is_retro, reason = ask_ai_classification(
            brand, title, filename, mod_name, cfg, allowed)
        if country and country in allowed:
            info = country_info(country)
            return country, info["flag"], cfg.multiplier_for(country), is_retro, False, reason
        return "⚠️ Проверить", "❓", cfg.multiplier_for(allowed[0]), False, True, f"ИИ: {reason}"

    info = country_info(allowed[0])
    return allowed[0], info["flag"], cfg.multiplier_for(allowed[0]), False, True, "По умолчанию"


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
