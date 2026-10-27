import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
import zipfile


def run() -> None:
    import webview
    import app
    from core import ai_state, parser, storage
    from core.service import _raw_of

    output = Path(sys.argv[sys.argv.index("--smoke-test") + 1]).resolve()
    workspace = tempfile.TemporaryDirectory(prefix="fs25-smoke-")
    storage.data_dir = lambda: workspace.name
    ai_state.init_state()

    class SmokeApi(app.Api):
        def _refresh_ai(self):
            pass

        def _ai_status(self):
            return {"running": False, "models": [], "current": ""}

        def ai_catalog(self):
            from core.ai import MODEL_CATALOG, MODEL_RANKS
            catalog = [dict(model, desc=model.get("desc_en") if self._svc.cfg.ui_lang == "en" else model["desc"],
                            size=str(model["gb"]) + " GB", rank=MODEL_RANKS.get(model["name"], 0))
                       for model in MODEL_CATALOG]
            return {"running": False, "installed": ["qwen2.5:3b"], "catalog": catalog,
                    "loaded": [{"name": "qwen2.5:3b", "size": 3000000000, "vram": 3000000000}],
                    "ollama_installed": True, "hw": {}, "rec": "qwen2.5:3b", "rec_reason": "16 GB"}

    api = SmokeApi()
    api._svc.cfg.stop_ai_on_close = False
    api._svc.cfg.use_local_ai = False
    api._svc.cfg.selected_countries = ["Германия"]
    api._svc.cfg.mods_dir = workspace.name
    target = Path(workspace.name) / "Smoke.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("modDesc.xml", '<modDesc><storeItems><storeItem xmlFilename="plant.xml"/></storeItems></modDesc>')
        archive.writestr("plant.xml", '<placeable><storeData><name>Smoke Plant</name><category>productions</category><price>10000</price></storeData><productionPoint><productions><production name="Test" cyclesPerHour="2" costsPerActiveMonth="24"><inputs><input fillType="WHEAT" amount="1000"/></inputs><outputs><output fillType="FLOUR" amount="800"/></outputs></production></productions><storage><capacity fillType="WHEAT" capacity="10000"/></storage></productionPoint></placeable>')
    api._svc.specs = parser.process_mod(str(target), api._svc.cfg)
    api._svc.raw_cache = {item.unique_key: _raw_of(item) for item in api._svc.specs}
    window = webview.create_window("FS25 smoke", os.path.join(app._web_root(), "index.html"),
                                   js_api=api, width=1024, height=680, hidden=True)

    def verify():
        result = {"ok": False, "checks": []}
        try:
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                ready = window.evaluate_js("typeof S !== 'undefined' && !!S.boot && !document.querySelector('#shell').hidden")
                if ready:
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("UI boot timed out")
            script = """
            (() => {
              const checks = [];
              const check = (condition, label) => { if (!condition) throw new Error(label); checks.push(label); };
              check(!window.__jsErrors.length, 'No JS errors');
              check(S.order.length === 1, 'Table renders fixture');
              check(document.querySelectorAll('#scanTarget input').length === 3, 'Scan multiselect');
              check(document.querySelector('#languageSwitch'), 'Language switch');
              endTour(); finishIntro();
              const item = S.items.get(S.order[0]);
              openTtx(item.unique_key);
              check(document.querySelector('[data-spec="prod_cycles"]'), 'Production editor');
              check(document.querySelector('#mPrice'), 'Custom price editor');
              closeTtx();
              document.querySelector('[data-f="placeable"]').click();
              check(document.querySelector('[data-subgroup="production"]'), 'Building subgroup picker');
              closeMenu();
              S.selected.add(item.unique_key); renderTable();
              check(document.querySelector('#selectionBar').classList.contains('is-on'), 'Bulk selection');
              applyLanguage('en');
              check(document.documentElement.lang === 'en', 'English language');
              check(document.querySelector('#btnApply').textContent.includes('Apply'), 'English Apply button');
              window.__untranslated = [];
              for (const key of ['scan', 'prices', 'countries', 'fields', 'pro']) {
                showView(key); translateTree(document.body);
                const walker = document.createTreeWalker(document.querySelector('#view-' + key), NodeFilter.SHOW_TEXT);
                let node;
                while ((node = walker.nextNode())) {
                  if (/[А-Яа-яЁё]/.test(node.nodeValue) && node.parentElement.getClientRects().length &&
                    !node.parentElement.closest('textarea, .c-name, .c-brand, .c-mod, .data-path')) {
                    window.__untranslated.push(node.nodeValue.trim());
                  }
                }
              }
              showView('pro');
              check(document.querySelector('#cheatSettings'), 'Balance settings');
              const view = document.querySelector('#view-pro');
              check(view.scrollHeight > view.clientHeight, 'Settings overflow scroll');
              view.scrollTop = view.scrollHeight;
              check(view.scrollTop > 0, 'Settings scroll to bottom');
              showView('scan'); applyLanguage('ru');
              check(document.querySelector('#btnApply').textContent.includes('Применить'), 'Russian switch back');
              startTour();
              check(!document.querySelector('#tour').hidden, 'Tutorial starts');
              check(document.querySelector('#tourNext').getBoundingClientRect().bottom <= innerHeight, 'Tutorial button in viewport');
              endTour();
              showView('pro');
              const scroll = document.querySelector('#view-pro');
              scroll.scrollTop = 0;
              scroll.dispatchEvent(new WheelEvent('wheel', { deltaY: 400, bubbles: true, cancelable: true }));
              check(scroll.scrollTop > 0, 'Mouse wheel scroll works');
              showView('scan'); startTour();
              for (let index = 0; index < TOUR.length; index++) {
                S.tourStep = index; placeTour();
                const button = document.querySelector('#tourNext').getBoundingClientRect();
                check(button.top >= 0 && button.bottom <= innerHeight && button.right <= innerWidth, 'Tutorial step ' + index + ' fits');
              }
              endTour();
              return checks;
            })()
            """
            result["checks"] = window.evaluate_js(script)
            result["untranslated"] = window.evaluate_js("window.__untranslated")
            window.evaluate_js("showView('scan'); openPrice(document.querySelector('[data-price]'), S.items.get(S.order[0])); true")
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if window.evaluate_js("!!document.querySelector('#customSave')?.onclick"):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Price editor failed to load")
            window.evaluate_js("document.querySelector('#customRubles').value='123456'; document.querySelector('#customRubles').dispatchEvent(new Event('input')); document.querySelector('#customSave').click(); true")
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if window.evaluate_js("S.items.get(S.order[0]).manual_price === 123456"):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Manual price failed to save")
            result["checks"].append("Manual ruble price saved through Python bridge")
            window.evaluate_js("document.querySelector('#languageSwitch').click(); true")
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if window.evaluate_js("S.boot.config.ui_lang === 'en' && document.documentElement.lang === 'en'"):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Language switch failed through Python bridge")
            result["checks"].append("Language switch persisted through Python bridge")
            time.sleep(0.5)
            errors = window.evaluate_js("window.__jsErrors")
            if errors:
                raise RuntimeError(str(errors))
            if result.get("untranslated"):
                raise RuntimeError("Untranslated UI: " + str(result["untranslated"]))
            result["ok"] = True
        except Exception:
            result["error"] = traceback.format_exc()
        finally:
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            window.destroy()

    webview.start(verify, private_mode=True)
    workspace.cleanup()
