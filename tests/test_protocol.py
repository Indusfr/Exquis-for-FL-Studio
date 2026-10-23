# Tests hors FL de device_Exquis.py (couche protocole, rendu, dispatch)
# Lancer depuis la racine du dépôt : python -m unittest discover tests
import os
import sys
import types
import unittest

# Modules FL remplacés : device enregistre les SysEx envoyés
_sent = []
_device = types.ModuleType('device')
_device.midiOutSysex = _sent.append
sys.modules['device'] = _device
sys.modules['ui'] = types.ModuleType('ui')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import device_Exquis as dx  # noqa: E402

HEADER = [0xF0, 0x00, 0x21, 0x7E, 0x7F]


class Event(object):
    def __init__(self, status, data1, data2):
        self.status, self.data1, self.data2, self.port = status, data1, data2, 0
        self.handled = False


class ProtocolTest(unittest.TestCase):
    def test_dev_mode(self):
        self.assertEqual(list(dx.build_dev_mode(dx.DEV_MASK_CONTROLS)), HEADER + [0x00, 0x3E, 0xF7])
        self.assertEqual(list(dx.build_dev_mode(dx.DEV_MASK_OFF)), HEADER + [0x00, 0x00, 0xF7])

    def test_tempo(self):
        self.assertEqual(list(dx.build_tempo(120)), HEADER + [0x05, 0x00, 120, 0xF7])
        self.assertEqual(list(dx.build_tempo(200)), HEADER + [0x05, 0x01, 200 - 128, 0xF7])
        self.assertEqual(dx.build_tempo(999), dx.build_tempo(240))
        self.assertEqual(dx.build_tempo(5), dx.build_tempo(20))

    def test_root_and_scale(self):
        self.assertEqual(list(dx.build_root(13)), HEADER + [0x06, 1, 0xF7])
        major = [1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1]
        self.assertEqual(list(dx.build_custom_scale(major)), HEADER + [0x08] + major + [0xF7])
        with self.assertRaises(ValueError):
            dx.build_custom_scale([1, 0, 1])

    def test_leds(self):
        msg = dx.build_leds(100, [(127, 0, 0, 0x3F), (0, 127, 0, 0)])
        self.assertEqual(list(msg), HEADER + [0x04, 100, 127, 0, 0, 0x3F, 0, 127, 0, 0, 0xF7])

    def test_led_runs_split_on_gaps_and_size(self):
        s = (1, 2, 3, 0)
        msgs = dx.build_led_runs({100: s, 101: s, 103: s, 110: s}, run_max=2)
        starts = [m[6] for m in msgs]
        self.assertEqual(starts, [100, 103, 110])
        msgs = dx.build_led_runs({i: s for i in range(100, 105)}, run_max=2)
        self.assertEqual([m[6] for m in msgs], [100, 102, 104])

    def test_seven_bit(self):
        msg = dx.build_sysex([0x80, 0xFF])
        self.assertTrue(all(b < 0x80 for b in msg[1:-1]))


class ControllerTest(unittest.TestCase):
    def setUp(self):
        del _sent[:]
        self.x = dx.Exquis()

    def test_init_sends_dev_mode_then_all_leds(self):
        self.x.on_init()
        self.assertEqual(_sent[0], dx.build_dev_mode(dx.DEV_MASK_CONTROLS))
        self.assertEqual(len(self.x.sent), len(dx.CONTROL_LEDS))
        del _sent[:]
        self.x.dirty = True
        self.x.on_idle()
        self.assertEqual(_sent, [])  # rien ne change : rien n'est envoyé

    def test_shift_redraws_only_settings(self):
        self.x.on_init()
        del _sent[:]
        ev = Event(0xBF, dx.BTN_SETTINGS, 0x7F)
        self.x.on_midi(ev)
        self.assertTrue(ev.handled)
        self.x.on_idle()
        self.assertEqual(_sent, [dx.build_leds(dx.BTN_SETTINGS, [dx.SHIFT_ON])])

    def test_mpe_notes_pass_through(self):
        ev = Event(0x91, 60, 100)
        self.x.on_midi(ev)
        self.assertFalse(ev.handled)

    def test_unknown_dev_message_not_handled(self):
        ev = Event(0xBF, 70, 1)
        self.x.on_midi(ev)
        self.assertFalse(ev.handled)

    def test_deinit_turns_off_and_exits(self):
        self.x.on_init()
        del _sent[:]
        self.x.on_deinit()
        self.assertEqual(_sent[-1], dx.build_dev_mode(dx.DEV_MASK_OFF))
        self.assertFalse(self.x.initialised)


if __name__ == '__main__':
    unittest.main()
