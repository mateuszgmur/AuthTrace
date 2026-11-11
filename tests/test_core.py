"""
Testy rdzenia (bez klawiatury i bez GUI):  python -m unittest discover tests
"""

import json
import tempfile
import unittest
from pathlib import Path

from authtrace.features import extract_features, remove_outliers_iqr
from authtrace.profiles import ProfileStore
from authtrace.session import CollectorSession, SessionTooShort


class FakeBackend:
    """Udaje pynput/evdev: testy same 'wciskają' klawisze przez press()/release()."""
    name = "fake"

    def __init__(self, on_press, on_release):
        self.press, self.release = on_press, on_release
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


def type_text(backend, text, t0=0.0, iki=0.12, dwell=0.08):
    t = t0
    for ch in text:
        key = "Key.space" if ch == " " else repr(ch)
        backend.press(key, t)
        backend.release(key, t + dwell)
        t += iki
    return t


class TestFeatures(unittest.TestCase):
    def test_iqr_needs_8_samples(self):
        self.assertEqual(remove_outliers_iqr([1, 2, 100]), [1, 2, 100])
        self.assertNotIn(100, remove_outliers_iqr([1, 1, 1, 1, 1, 1, 1, 1, 100]))

    def test_basic_timings(self):
        events = []
        t = 0.0
        for ch in "ala ma kota " * 5:
            events += [{"event": "press", "key": repr(ch), "t": t},
                       {"event": "release", "key": repr(ch), "t": t + 0.1}]
            t += 0.2
        f = extract_features(events)
        self.assertAlmostEqual(f["dwell_time"]["mean"], 0.1, places=6)
        self.assertAlmostEqual(f["iki"]["mean"], 0.2, places=6)
        self.assertAlmostEqual(f["flight_time"]["mean"], 0.1, places=6)
        self.assertEqual(f["meta"]["total_chars"], 60)

    def test_altgr_counted_as_alt_right(self):
        events = [{"event": "press", "key": "Key.alt_gr", "t": 0.0},
                  {"event": "release", "key": "Key.alt_gr", "t": 0.09}]
        f = extract_features(events)
        self.assertEqual(f["special_keys"]["alt_right"]["count"], 1)


class TestProfiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProfileStore(Path(self.tmp.name) / "data", Path(self.tmp.name) / "models")

    def tearDown(self):
        self.tmp.cleanup()

    def test_names_and_numbering(self):
        self.store.create("ania")
        d = self.store.path("ania")
        for i in (1, 2, 10):
            (d / f"features_session_{i}.json").write_text("{}")
        self.assertEqual(self.store.names(), ["ania"])
        self.assertEqual(self.store.session_ids("ania"), [1, 2, 10])
        self.assertEqual(self.store.next_session_id("ania"), 11)

    def test_rejects_unsafe_names(self):
        for bad in ("../x", "a b", "", "a/b"):
            self.assertFalse(ProfileStore.is_valid_name(bad), bad)
        self.assertTrue(ProfileStore.is_valid_name("Małgorzata_2"))


class TestSession(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProfileStore(Path(self.tmp.name) / "data", Path(self.tmp.name) / "models")
        self.backends = []

        def factory(p, r):
            b = FakeBackend(p, r)
            self.backends.append(b)
            return b
        self.session = CollectorSession("ania", backend=factory, store=self.store)
        self.session.start()
        self.kb = self.backends[0]

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_numbers_and_files(self):
        type_text(self.kb, "to jest test sesji")
        r1 = self.session.save()
        type_text(self.kb, "druga sesja tekstu", t0=10)
        r2 = self.session.save()
        self.assertEqual((r1.session_id, r2.session_id), (1, 2))
        raw = json.loads(r2.raw_path.read_text(encoding="utf-8"))
        self.assertEqual(raw[0]["key"], "'d'")             # bufor wyczyszczony po 1. zapisie
        self.assertTrue(self.kb.running)                    # save() nie zatrzymuje nasłuchu

    def test_pause_and_orphans(self):
        self.session.pause()
        self.kb.press("Key.enter", 0.0)                     # wciśnięty w trakcie pauzy
        self.session.resume()
        self.kb.release("Key.enter", 0.05)                  # osierocony release -> odrzucony
        self.assertEqual(self.session.event_count, 0)

    def test_too_short(self):
        type_text(self.kb, "abc")
        with self.assertRaises(SessionTooShort):
            self.session.finish()
        self.assertFalse(self.kb.running)

    def test_no_overwrite(self):
        type_text(self.kb, "to jest test sesji")
        self.session.save(session_id=5)
        type_text(self.kb, "to jest test sesji", t0=10)
        with self.assertRaises(FileExistsError):
            self.session.save(session_id=5)


if __name__ == "__main__":
    unittest.main()
