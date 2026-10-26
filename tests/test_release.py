import copy
import json
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile
import zlib

from core import ai_state, parser, storage
from core import ai
from core.models import BalancerConfig
from core.models import ItemSpec
from core.pricing import field_price, rub_from_xml
from core.service import BalancerService, _raw_of, drain_events


VEHICLE = b"""<vehicle><storeData><name>Test Tractor</name><brand>Fendt</brand>
<category>tractors</category><price>10000</price><dailyUpkeep>10</dailyUpkeep>
<specs><power>120</power><maxSpeed>40</maxSpeed></specs></storeData>
<motorized><motorConfigurations>
<motorConfiguration name="Base" hp="120" price="0"><motor maxForwardSpeed="40"/></motorConfiguration>
<motorConfiguration name="Plus" hp="160" price="1000"><motor maxForwardSpeed="40"/></motorConfiguration>
</motorConfigurations></motorized></vehicle>"""
PLANT = b"""<placeable><storeData><name>Test Plant</name><brand>GENERIC</brand>
<category>productions</category><price>100000</price><dailyUpkeep>100</dailyUpkeep></storeData>
<productionPoint><productions>
<production name="flour" cyclesPerHour="2" costsPerActiveMonth="240">
<inputs><input fillType="WHEAT" amount="1000"/></inputs>
<outputs><output fillType="FLOUR" amount="800"/></outputs></production></productions>
<storage><capacity fillType="WHEAT" capacity="10000"/><capacity fillType="FLOUR" capacity="10000"/></storage>
</productionPoint></placeable>"""
SELLING = b"""<placeable><storeData><name>Market</name><category>sellingPoints</category>
<price>10000</price></storeData><sellingStation><unloadTrigger fillTypes="WHEAT BARLEY FLOUR"/></sellingStation></placeable>"""


class ReleaseChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous_state = copy.deepcopy(ai_state._state)
        self.storage_patch = patch.object(storage, "data_dir", return_value=str(self.root))
        self.storage_patch.start()
        ai_state.init_state()
        self.cfg = BalancerConfig(use_local_ai=False, selected_countries=["Германия"])
        self.backup = self.root / "_backup_original_mods"
        drain_events()

    def tearDown(self):
        self.storage_patch.stop()
        ai_state._state.clear()
        ai_state._state.update(self.previous_state)
        self.temp.cleanup()

    def make_mod(self, name="Test.zip", folder=False):
        files = {"modDesc.xml": b'<modDesc><storeItems><storeItem xmlFilename="tractor.xml"/><storeItem xmlFilename="plant.xml"/><storeItem xmlFilename="market.xml"/></storeItems></modDesc>',
                 "tractor.xml": VEHICLE, "plant.xml": PLANT, "market.xml": SELLING,
                 "assets.bin": b"asset" * 10000}
        target = self.root / (name.removesuffix(".zip") if folder else name)
        if folder:
            target.mkdir()
            for filename, data in files.items():
                (target / filename).write_bytes(data)
        else:
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
                for filename, data in files.items():
                    archive.writestr(filename, data)
        return target

    def service(self, target):
        service = BalancerService()
        service.cfg = copy.deepcopy(self.cfg)
        service.cfg.mods_dir = str(target.parent)
        service.specs = parser.process_mod(str(target), service.cfg)
        service.raw_cache = {item.unique_key: _raw_of(item) for item in service.specs}
        return service

    def test_zip_metadata_and_zero_write(self):
        target = self.root / "unicode.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.comment = b"archive comment"
            archive.writestr("техника.xml", b"original")
            archive.writestr("asset.bin", b"untouched" * 1000)
        before = target.stat().st_mtime_ns
        parser.reset_disk_meter()
        self.assertEqual(parser.rebuild_mod_zip(str(target), {"техника.xml": b"original"}), "skip")
        self.assertEqual(parser.disk_payload()["written"], 0)
        self.assertEqual(target.stat().st_mtime_ns, before)
        self.assertEqual(parser.rebuild_mod_zip(str(target), {"техника.xml": b"changed"}), "inplace")
        with zipfile.ZipFile(target) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.comment, b"archive comment")
            self.assertEqual(archive.read("техника.xml"), b"changed")
            self.assertEqual(len(archive.namelist()), 2)

    def test_interrupted_write_restores_original(self):
        target = self.make_mod()
        original = target.read_bytes()
        with patch.object(parser, "_verify_inplace", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                parser.rebuild_mod_zip(str(target), {"tractor.xml": b"changed"})
        parser.recover_mod_zip(str(target))
        self.assertEqual(target.read_bytes(), original)

    def test_crash_journal_recovery(self):
        target = self.make_mod()
        original = target.read_bytes()
        with zipfile.ZipFile(target) as archive:
            offset = archive.start_dir
        tail = original[offset:]
        Path(str(target) + ".fs25txn").write_bytes(parser._JOURNAL_HEADER.pack(
            parser._JOURNAL_MAGIC, offset, len(original), zlib.crc32(tail)) + tail)
        with target.open("r+b") as stream:
            stream.seek(offset)
            stream.write(b"corrupted")
            stream.truncate()
        self.assertTrue(parser.recover_mod_zip(str(target)))
        self.assertEqual(target.read_bytes(), original)

    def test_scan_is_read_only_and_categories_work(self):
        target = self.make_mod()
        before = target.read_bytes()
        items = parser.process_mod(str(target), self.cfg)
        self.assertEqual(len(items), 3)
        self.assertEqual(target.read_bytes(), before)
        self.cfg.scan_targets = ["placeable"]
        self.assertEqual(len(parser.process_mod(str(target), self.cfg)), 2)
        self.assertEqual({item.subgroup for item in items if item.item_type == "placeable"}, {"production", "selling"})

    def test_apply_backup_and_repeat(self):
        for folder in (False, True):
            with self.subTest(folder=folder):
                target = self.make_mod("Folder.zip" if folder else "Archive.zip", folder)
                items = parser.process_mod(str(target), self.cfg, True, str(self.backup))
                self.assertEqual(len(items), 3)
                backup = self.backup / target.name
                self.assertEqual((backup / "tractor.xml").read_bytes(), VEHICLE)
                self.assertFalse((backup / "assets.bin").exists())
                parser.reset_disk_meter()
                parser.process_mod(str(target), self.cfg, True, str(self.backup))
                self.assertEqual(parser.disk_payload()["written"], 0)
                self.assertGreater(parser.restore_mod_backup(str(target), str(self.backup)), 0)
                if folder:
                    self.assertEqual((target / "tractor.xml").read_bytes(), VEHICLE)
                else:
                    with zipfile.ZipFile(target) as archive:
                        self.assertEqual(archive.read("tractor.xml"), VEHICLE)

    def test_production_edit_preview_and_persistence(self):
        target = self.make_mod()
        service = self.service(target)
        plant = next(item for item in service.specs if item.title == "Test Plant")
        self.assertIn("prod_cycles", plant.spec_fields)
        self.assertEqual(plant.storage_capacity, 20000)
        preview = service.preview_specs(plant.unique_key, {"prod_cycles": 8, "prod_output": 1600, "storage_capacity": 40000})
        self.assertTrue(preview["ok"])
        self.assertGreater(preview["auto_price"], plant.new_price)
        result = service.update_specs(plant.unique_key, {"prod_cycles": 8, "prod_output": 1600, "storage_capacity": 40000})
        self.assertTrue(result["ok"])
        self.assertEqual(result["item"]["new_price"], preview["auto_price"])
        parser.process_mod(str(target), service.cfg, True, str(self.backup), service.overrides)
        with zipfile.ZipFile(target) as archive:
            root = ET.fromstring(archive.read("plant.xml"))
            self.assertEqual(float(root.find(".//production").get("cyclesPerHour")), 8)
            self.assertEqual(float(root.find(".//output").get("amount")), 1600)
        parser.reset_disk_meter()
        parser.process_mod(str(target), service.cfg, True, str(self.backup), service.overrides)
        self.assertEqual(parser.disk_payload()["written"], 0)

    def test_motor_changes_and_share_bundle(self):
        target = self.make_mod()
        service = self.service(target)
        tractor = next(item for item in service.specs if item.item_type == "vehicle")
        self.assertTrue(service.set_motor(tractor.unique_key, 1, 200, 12345)["ok"])
        self.assertTrue(service.update_specs(tractor.unique_key, {"max_speed": 55})["ok"])
        self.assertTrue(service.set_price(tractor.unique_key, 987654)["ok"])
        exported = service.export_prices(str(self.root))
        self.assertTrue(exported["ok"])
        self.assertLess(exported["size"], 15000)
        second = self.service(target)
        result = second.import_prices(exported["path"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["matched"], 3)
        self.assertEqual(result["missing"], 0)
        second._apply_worker()
        with zipfile.ZipFile(target) as archive:
            root = ET.fromstring(archive.read("tractor.xml"))
            motors = root.findall(".//motorConfiguration")
            self.assertEqual(float(motors[1].get("hp")), 200)
            self.assertEqual(int(motors[1].get("price")), 12345)
            self.assertEqual(int(root.findtext("./storeData/price")), 987654)
            self.assertEqual(float(root.find(".//motor").get("maxForwardSpeed")), 55)
            self.assertIsNone(archive.testzip())

    def test_settings_skip_unchanged(self):
        self.assertTrue(storage.save_json("example.json", {"value": 42}))
        target = self.root / "example.json"
        timestamp = target.stat().st_mtime_ns
        with patch("builtins.open", wraps=open) as opened:
            self.assertTrue(storage.save_json("example.json", {"value": 42}))
            self.assertFalse(any("w" in str(call.args[1]) for call in opened.call_args_list))
        self.assertEqual(target.stat().st_mtime_ns, timestamp)
        self.assertFalse(storage.save_json("invalid.json", {"value": float("nan")}))

    def test_hardware_specific_recommendations(self):
        low = ai.recommend_model({"ram_gb": 8, "gpu_gb": 0, "gpu_name": ""})[0]
        high = ai.recommend_model({"ram_gb": 32, "gpu_gb": 12, "gpu_name": "GPU"})[0]
        self.assertNotEqual(low, high)
        self.assertIn("mistral:latest", {model["name"] for model in ai.MODEL_CATALOG})
        self.assertGreaterEqual(len(ai.MODEL_CATALOG), 10)

    def test_production_cost_and_material_yield(self):
        target = self.make_mod()
        service = self.service(target)
        plant = next(item for item in service.specs if item.title == "Test Plant")
        current = service.preview_specs(plant.unique_key)["auto_price"]
        expensive = service.preview_specs(plant.unique_key, {"prod_cost_month": 24000})
        self.assertGreater(expensive["auto_price"], current)
        edited = service.update_specs(plant.unique_key, {"prod_cost_month": 24000})
        self.assertEqual(edited["item"]["new_price"], expensive["auto_price"])
        efficient = service.preview_specs(plant.unique_key, {"prod_input": 100})
        inefficient = service.preview_specs(plant.unique_key, {"prod_input": 10000})
        self.assertGreater(efficient["auto_price"], inefficient["auto_price"])

    def test_motor_repeat_apply_without_writes(self):
        target = self.make_mod()
        service = self.service(target)
        tractor = next(item for item in service.specs if item.item_type == "vehicle")
        service.set_motor(tractor.unique_key, 1, 200, 12345)
        service.reprice_item(tractor)
        self.assertEqual(tractor.motors[1].price_delta, 12345)
        service._apply_worker()
        parser.reset_disk_meter()
        service._apply_worker()
        self.assertEqual(parser.disk_payload()["written"], 0)

    def test_cheat_mode_and_pool(self):
        target = self.make_mod()
        service = self.service(target)
        tractor = next(item for item in service.specs if item.item_type == "vehicle")
        service.cfg.cheat_detect = True
        service.cfg.cheat_max_hp = 100
        service.reprice_item(tractor)
        self.assertTrue(tractor.is_cheat)
        service.cfg.cheat_detect = False
        service.reprice_item(tractor)
        self.assertFalse(tractor.is_cheat)
        self.assertFalse(service.set_country(tractor.unique_key, "Япония")["ok"])

    def test_import_rejects_invalid_bundle(self):
        target = self.make_mod()
        service = self.service(target)
        bundle = self.root / "invalid.json"
        bundle.write_text(json.dumps({"format": "fs25balancer-bundle", "items": [
            {"key": "test", "price": float("nan")}]}))
        self.assertFalse(service.import_prices(str(bundle))["ok"])

    def test_ai_checks_actual_specs(self):
        self.cfg.cheat_detect = True
        self.cfg.cheat_use_ai = True
        self.cfg.use_local_ai = True
        self.cfg.ai_model_name = "fixture"
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"response":"CHEAT|implausible power"}'
        with patch.object(ai, "check_ollama", return_value=(True, ["fixture:latest"])), \
             patch.object(ai.urllib.request, "urlopen", return_value=response) as request:
            result = ai.assess_specs("Test", "Unique fixture", "test.xml", "test", {"hp": 9000}, self.cfg)
        self.assertTrue(result[0])
        self.assertIn(b"9000", request.call_args.args[0].data)

    def test_prepared_apply_preserves_manual_country_and_retro(self):
        target = self.make_mod()
        service = self.service(target)
        service.cfg.selected_countries = ["Германия", "США"]
        tractor = next(item for item in service.specs if item.item_type == "vehicle")
        self.assertTrue(service.set_country(tractor.unique_key, "США")["ok"])
        service.set_retro(tractor.unique_key, True)
        expected = tractor.new_price
        service._apply_worker()
        with zipfile.ZipFile(target) as archive:
            root = ET.fromstring(archive.read("tractor.xml"))
            self.assertEqual(int(root.findtext("./storeData/price")), expected)
            self.assertEqual(int(root.findtext("./storeData/dailyUpkeep")),
                             max(5, int(round(expected * 0.0025 * 1.15))))
        parser.reset_disk_meter()
        service._apply_worker()
        self.assertEqual(parser.disk_payload()["written"], 0)

    def test_restore_removes_pending_spec_patches(self):
        target = self.make_mod()
        service = self.service(target)
        tractor = next(item for item in service.specs if item.item_type == "vehicle")
        service.update_specs(tractor.unique_key, {"max_speed": 55})
        service._apply_worker()
        service._restore_worker(str(self.root), str(self.backup))
        self.assertNotIn(tractor.unique_key, ai_state.get_spec_patches())
        self.assertFalse(service.specs)
        with zipfile.ZipFile(target) as archive:
            self.assertEqual(archive.read("tractor.xml"), VEHICLE)

    def test_currency_modes_and_field_area(self):
        self.cfg.exchange_rate = 100
        self.cfg.ac_mod_installed = False
        self.assertEqual(self.cfg.xml_factor, 100)
        self.assertEqual(rub_from_xml(500000, self.cfg), 500000)
        self.cfg.ac_mod_installed = True
        self.cfg.ac_converter = True
        self.assertEqual(self.cfg.xml_factor, 1)
        self.assertEqual(rub_from_xml(5000, self.cfg), 500000)
        self.cfg.adjust_field_prices = True
        self.assertGreater(field_price(20, 0, self.cfg), field_price(10, 0, self.cfg))
        self.assertGreater(field_price(10, 0, self.cfg), field_price(10, 5, self.cfg))
        service = BalancerService()
        service.cfg = self.cfg
        service.specs = [ItemSpec("map.zip", "field.xml", item_type="field")]
        key = service.specs[0].unique_key
        self.assertFalse(service.patch_field(key, float("nan"), 2)["ok"])
        self.assertFalse(service.patch_field(key, 10, float("inf"))["ok"])

    def test_changed_mod_requires_rescan(self):
        target = self.make_mod()
        service = self.service(target)
        service._mod_signatures[target.name] = (target.stat().st_size, target.stat().st_mtime_ns)
        with zipfile.ZipFile(target, "a") as archive:
            archive.writestr("external.xml", b"external change")
        service._apply_worker()
        self.assertIn("изменился после сканирования", service.last_error)
        self.assertTrue(any(event["type"] == "error" for event in drain_events()))


    def test_legacy_backup_migration_and_source_kind(self):
        target = self.make_mod()
        self.backup.mkdir()
        (self.backup / "Test.zip").write_bytes(b"old full mod backup")
        service = self.service(target)
        tractor = next(item for item in service.specs if item.item_type == "vehicle")
        self.assertEqual(tractor.source_kind, "dict")
        service._apply_worker()
        self.assertFalse(service.last_error)
        self.assertTrue((self.backup / "Test.zip").is_dir())
        self.assertTrue((self.backup / "Test.zip.legacy").is_file())
        service._restore_worker(str(self.root), str(self.backup))
        self.assertEqual((self.root / "Test.zip").read_bytes(), b"old full mod backup")


    def test_import_dialog_file_filters_parse(self):
        from webview.util import parse_file_type
        import app
        for ft in app.IMPORT_FILE_TYPES:
            parse_file_type(ft)


if __name__ == "__main__":
    unittest.main()
