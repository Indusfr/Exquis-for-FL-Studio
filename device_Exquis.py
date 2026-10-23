# name=Intuitive Instruments Exquis (Ableton style)
# url=https://github.com/Indusfr/Exquis-for-FL-Studio
# supportedDevices=Exquis
"""
=======================================================================================
 Intuitive Instruments Exquis  ->  FL Studio 2026  (intégration « style Ableton Live »)
=======================================================================================
 Version 0.2.0 (2026-10-23) — squelette
 Author : Pascal "Indus" Nowak, written with the help of Claude (Anthropic)
 License: MIT (texte complet à la fin de cet en-tête)

Le script passe l'Exquis en mode développeur (SysEx 00) pour les encodeurs, le
slider et tous les boutons. Les pads restent en mode MPE natif : leurs notes
(pitch bend, pression, slide par note) passent directement à FL Studio.

Source protocole : « Exquis Developer Mode MIDI specification »
  https://dualo.com/download/16645/ (lien depuis https://dualo.com/en/exquis-resources/)

INSTALLATION
  1. Copier device_Exquis.py dans :
       Documents/Image-Line/FL Studio/Settings/Hardware/Exquis/
  2. FL Studio > Options > MIDI settings :
       - Entrée « Exquis » : Enable, Controller type = « Intuitive Instruments
         Exquis (Ableton style) », Port = 11 (par exemple).
       - Sortie « Exquis » : même numéro de Port (11).
     Un seul port USB : il transporte les notes MPE (canaux 1-15), les messages
     du mode développeur (canal 16) et les SysEx (LED, tempo, gamme).

ÉTAT DU SQUELETTE
  - Entrée/sortie du mode développeur, extinction des LED à la sortie.
  - Toutes les LED des boutons/encodeurs/slider pilotées par le rendu différentiel.
  - Les messages du canal 16 sont routés par une table de dispatch ; les
    fonctions sont des emplacements vides (journal DEBUG seulement), sauf
    Settings qui sert de Shift.

CHANGELOG
  0.2.0 (2026-10-23)  Nouveau squelette (architecture cible). L'ancienne v0.1
                      (dépôt FL-Exquis) sert de référence.

MIT LICENSE
  Copyright (c) 2026 Pascal "Indus" Nowak

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
  SOFTWARE.
===============================================================================
"""

__version__ = "0.2.0"
VERSION_DATE = "2026-10-23"
__author__ = 'Pascal "Indus" Nowak (with the help of Claude)'
__license__ = "MIT"

import device
import ui

# =============================================================================
# CONFIGURATION
# =============================================================================
# Journal : messages entrants (status, data1, data2, port) et SysEx sortants (hex)
DEBUG = False

# Nombre max de LED par SysEx 04 regroupé.
# [À VÉRIFIER : la doc ne donne pas de taille max de SysEx ; valeur prudente,
#  à augmenter après test avec DEBUG]
LED_RUN_MAX = 16

# =============================================================================
# CONSTANTES MATÉRIELLES (doc mode développeur)
# =============================================================================
SYSEX_HEADER = [0xF0, 0x00, 0x21, 0x7E, 0x7F]
SYSEX_END = 0xF7

CMD_DEV_MODE = 0x00        # 00 mask
CMD_SET_LED = 0x04         # 04 start_id (R G B fx)...
CMD_TEMPO = 0x05           # 05 MSB LSB
CMD_ROOT = 0x06            # 06 note (0 = C ... 11 = B)
CMD_CUSTOM_SCALE = 0x08    # 08 degree(0)...degree(11)

TEMPO_MIN, TEMPO_MAX = 20, 240

# Zones du mode développeur (bits du masque, cumulables)
ZONE_PADS = 0x01
ZONE_ENCODERS = 0x02
ZONE_SLIDER = 0x04
ZONE_UP_DOWN = 0x08
ZONE_SETTINGS_SOUND = 0x10
ZONE_OTHER_BUTTONS = 0x20
DEV_MASK_OFF = 0x00
# Tout sauf les pads : le jeu MPE reste natif
DEV_MASK_CONTROLS = (ZONE_ENCODERS | ZONE_SLIDER | ZONE_UP_DOWN
                     | ZONE_SETTINGS_SOUND | ZONE_OTHER_BUTTONS)

DEV_CHANNEL = 15           # canal 16 (index 0-15), réservé au mode développeur
STATUS_NOTE_OFF = 0x80
STATUS_NOTE_ON = 0x90
STATUS_CC = 0xB0
BUTTON_PRESSED = 0x7F
ENCODER_CENTER = 64        # encodeurs relatifs : delta = valeur - 64, > 0 = horaire
SLIDER_RELEASED = 127      # CC 90 = 127 quand le slider n'est pas touché

# Identifiants des contrôles (numéro de note/CC sur le canal 16 = index LED)
PADS = range(0, 61)                     # 0 = bas gauche, 60 = haut droite
SLIDER_ZONES = range(80, 86)            # 6 portions du slider
SLIDER_POS = 90
BTN_SETTINGS = 100
BTN_SOUND = 101
BTN_RECORD = 102
BTN_LOOP = 103
BTN_CLIPS = 104
BTN_PLAY = 105
BTN_DOWN = 106
BTN_UP = 107
BTN_UNDO = 108
BTN_REDO = 109
BUTTONS = range(100, 110)
ENCODERS = range(110, 114)
# [À VÉRIFIER : la doc annonce « 114-118 » pour 4 boutons ; 114-117 retenu]
ENCODER_BUTTONS = range(114, 118)

# LED pilotées par le script (les pads restent gérés par l'Exquis en MPE)
CONTROL_LEDS = list(SLIDER_ZONES) + list(BUTTONS) + list(ENCODERS) + list(ENCODER_BUTTONS)

# Effets LED (octet fx)
FX_NONE = 0x00
FX_PULSE_BLACK = 0x3F
FX_PULSE_WHITE = 0x7F
FX_PULSE_RED = 0x3E
FX_PULSE_GREEN = 0x7E

# Couleurs d'état (choix de conception, RGB 0-127)
OFF = (0, 0, 0, FX_NONE)
IDLE = (16, 16, 16, FX_NONE)            # contrôle disponible, sans fonction active
SHIFT_ON = (127, 127, 127, FX_NONE)

# =============================================================================
# COUCHE PROTOCOLE (fonctions pures, testables hors FL)
# =============================================================================
def to_hex(data):
    return ' '.join('%02X' % b for b in data)


def build_sysex(payload):
    """F0 00 21 7E 7F <payload> F7, chaque octet borné à 7 bits."""
    return bytes(SYSEX_HEADER + [b & 0x7F for b in payload] + [SYSEX_END])


def build_dev_mode(mask):
    return build_sysex([CMD_DEV_MODE, mask])


def build_tempo(bpm):
    bpm = max(TEMPO_MIN, min(TEMPO_MAX, int(round(bpm))))
    return build_sysex([CMD_TEMPO, (bpm >> 7) & 0x7F, bpm & 0x7F])


def build_root(note):
    return build_sysex([CMD_ROOT, note % 12])


def build_custom_scale(degrees):
    if len(degrees) != 12:
        raise ValueError('custom scale needs 12 degrees')
    return build_sysex([CMD_CUSTOM_SCALE] + [1 if d else 0 for d in degrees])


def build_leds(start_id, states):
    """04 start_id puis R G B fx pour chaque LED consécutive."""
    payload = [CMD_SET_LED, start_id]
    for r, g, b, fx in states:
        payload += [r, g, b, fx]
    return build_sysex(payload)


def build_led_runs(changes, run_max=LED_RUN_MAX):
    """{led_id: state} -> liste de SysEx 04, un par suite d'ID consécutifs.
    Les trous (ID absents de changes) coupent la suite."""
    messages = []
    run_start, run = None, []
    for led_id in sorted(changes):
        if run and (led_id != run_start + len(run) or len(run) >= run_max):
            messages.append(build_leds(run_start, run))
            run = []
        if not run:
            run_start = led_id
        run.append(changes[led_id])
    if run:
        messages.append(build_leds(run_start, run))
    return messages


def diff_leds(wanted, sent):
    """LED dont l'état voulu diffère du dernier état envoyé."""
    return {i: s for i, s in wanted.items() if sent.get(i) != s}


# =============================================================================
# UTILITAIRES
# =============================================================================
def log(*args):
    if DEBUG:
        print("[Exquis]", *args)


_reported_api_errors = set()


def safe(fn, *args, **kw):
    """Appel API protégé : renvoie `default` en cas d'erreur ou de fonction absente.
    La 1re erreur de chaque fonction est toujours affichée dans la Script output."""
    default = kw.pop('default', None)
    if fn is None:
        return default
    try:
        return fn(*args, **kw)
    except Exception as e:  # noqa
        name = "%s.%s" % (getattr(fn, '__module__', None) or '?', getattr(fn, '__name__', fn))
        if DEBUG or name not in _reported_api_errors:
            _reported_api_errors.add(name)
            print("[Exquis] API error in %s%r: %s" % (name, args, e))
        return default


def api(module, name):
    """module.name s'il existe dans cette version de FL, sinon None."""
    return getattr(module, name, None)


# =============================================================================
# COUCHE FL (seuls appels à l'API FL Studio)
# =============================================================================
def fl_send_sysex(msg):
    if DEBUG:
        print("[Exquis OUT]", to_hex(msg))
    # device.midiOutSysex — stubs FL (module device)
    safe(api(device, 'midiOutSysex'), msg)


def fl_hint(msg):
    # ui.setHintMsg — stubs FL (module ui)
    safe(api(ui, 'setHintMsg'), msg)


# =============================================================================
# CONTRÔLEUR (état, rendu, dispatch)
# =============================================================================
class Exquis(object):

    def __init__(self):
        self.initialised = False
        self.dirty = True        # un rendu est nécessaire
        self.shift = False       # Settings maintenu
        self.sent = {}           # cache LED : id -> dernier état envoyé
        self.dispatch = self.build_dispatch()

    # ---------------------------------------------------------- cycle de vie
    def on_init(self):
        fl_send_sysex(build_dev_mode(DEV_MASK_CONTROLS))
        self.sent = {}
        self.initialised = True
        self.dirty = True
        self.flush()
        print("Intuitive Instruments Exquis (Ableton style) v%s (%s) by %s - %s license"
              % (__version__, VERSION_DATE, __author__, __license__))
        fl_hint("Exquis v%s: ready" % __version__)

    def on_deinit(self):
        self.initialised = False
        for msg in build_led_runs({i: OFF for i in CONTROL_LEDS}):
            fl_send_sysex(msg)
        fl_send_sysex(build_dev_mode(DEV_MASK_OFF))
        self.sent = {}

    def on_idle(self):
        if self.initialised and self.dirty:
            self.flush()

    def on_refresh(self, flags):
        self.dirty = True

    def on_project_load(self, status):
        # Nouveau projet : l'Exquis peut avoir été rebranché, on renvoie tout
        self.sent = {}
        self.dirty = True

    # ------------------------------------------------------------------ rendu
    def wanted_leds(self):
        leds = {i: IDLE for i in CONTROL_LEDS}
        if self.shift:
            leds[BTN_SETTINGS] = SHIFT_ON
        return leds

    def flush(self):
        self.dirty = False
        changes = diff_leds(self.wanted_leds(), self.sent)
        for msg in build_led_runs(changes):
            fl_send_sysex(msg)
        self.sent.update(changes)

    # --------------------------------------------------------------- dispatch
    def build_dispatch(self):
        table = {(STATUS_CC, BTN_SETTINGS): self.on_settings}
        for cc in BUTTONS:
            table.setdefault((STATUS_CC, cc), self.on_button)
        for cc in ENCODERS:
            table[(STATUS_CC, cc)] = self.on_encoder
        for cc in ENCODER_BUTTONS:
            table[(STATUS_CC, cc)] = self.on_encoder_button
        for cc in SLIDER_ZONES:
            table[(STATUS_CC, cc)] = self.on_slider_zone
        table[(STATUS_CC, SLIDER_POS)] = self.on_slider
        return table

    def on_midi(self, event):
        if DEBUG:
            print("[Exquis IN] status=%02X data1=%d data2=%d port=%s"
                  % (event.status, event.data1, event.data2, getattr(event, 'port', '?')))
        # Canaux 1-15 : notes MPE des pads, laissées à FL
        if (event.status & 0x0F) != DEV_CHANNEL:
            return
        handler = self.dispatch.get((event.status & 0xF0, event.data1))
        if handler is None:
            return
        handler(event.data1, event.data2)
        event.handled = True

    # --------------------------------------------------- handlers (squelette)
    def on_settings(self, cc, value):
        self.shift = value == BUTTON_PRESSED
        self.dirty = True

    def on_button(self, cc, value):
        log("button", cc, "pressed" if value == BUTTON_PRESSED else "released")

    def on_encoder(self, cc, value):
        log("encoder", cc - ENCODERS.start, "delta", value - ENCODER_CENTER)

    def on_encoder_button(self, cc, value):
        log("encoder button", cc - ENCODER_BUTTONS.start,
            "pressed" if value == BUTTON_PRESSED else "released")

    def on_slider_zone(self, cc, value):
        log("slider zone", cc - SLIDER_ZONES.start,
            "pressed" if value == BUTTON_PRESSED else "released")

    def on_slider(self, cc, value):
        log("slider", "released" if value == SLIDER_RELEASED else value)


# =============================================================================
# CALLBACKS FL STUDIO
# =============================================================================
exquis = Exquis()


def OnInit():
    exquis.on_init()


def OnDeInit():
    exquis.on_deinit()


def OnMidiMsg(event):
    exquis.on_midi(event)


def OnIdle():
    exquis.on_idle()


def OnRefresh(flags):
    exquis.on_refresh(flags)


def OnProjectLoad(status):
    exquis.on_project_load(status)
