"""Non-GUI smoke tests for local records and crop suggestions."""
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "puyo_tools"))
import record_store
import crop_suggest
import tenpai_probe

EMPTY = ["......"] * 13

class RecordsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        record_store.ROOT=Path(self.temp.name)
        record_store.INDEX=record_store.ROOT / "index.json"
    def tearDown(self):
        self.temp.cleanup()
    def test_save_restore_move_edit(self):
        record_store.add_folder("対戦A")
        item=record_store.save("未分類","3:15","盤面のみ","memo",EMPTY,["RB","GY","RP"],{"type":"盤面のみ"})
        loaded=record_store.load(item["id"])
        self.assertEqual(loaded["board"], EMPTY)
        self.assertEqual(loaded["number"],1)
        record_store.update(item["id"],"第1試合","更新")
        record_store.move(item["id"],"対戦A")
        self.assertEqual(record_store.load(item["id"])["folder"],"対戦A")
        self.assertEqual(record_store.load(item["id"])["name"],"第1試合")
    def test_folder_traversal_rejected(self):
        with self.assertRaises(ValueError):
            record_store.add_folder("../bad")
    def test_tenpai_ignition(self):
        board=list(EMPTY)
        board[-1]="RRR..."
        results=tenpai_probe.probe(tuple(board),include_nuisance=False)
        self.assertTrue(any(r["column"]==4 and r["pieces"]=="R" and r["chains"]>=1 for r in results))
        self.assertFalse(any(r["pieces"].startswith("O") for r in results))
        self.assertEqual(tenpai_probe.probe(tuple(EMPTY)),[])

    def test_crop_suggestion(self):
        self.assertIn("1P",crop_suggest.suggest(1920,1080))
        self.assertIn("2P",crop_suggest.suggest(1920,1080))
        self.assertIn("1P",crop_suggest.suggest(300,600))
        self.assertEqual(crop_suggest.suggest(800,800),{})

if __name__=="__main__":
    unittest.main()
