import os
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gtk, Gdk, GLib, AyatanaAppIndicator3 as AI

from . import autostart
from .packs import list_packs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_ON = os.path.join(ROOT, "data", "thock-tray.svg")
ICON_OFF = os.path.join(ROOT, "data", "thock-tray-off.svg")

VOLUMES = [10, 25, 40, 60, 80, 100]
TONES = [("Deep thock", -1.0), ("Thock", -0.5), ("Balanced", 0.0), ("Clack", 0.5), ("Bright clack", 1.0)]

CSS = b"""
window.thock { background-color: #1d1f24; color: #e9eaee; }
.thock .title { font-size: 20px; font-weight: 700; }
.thock .subtitle { color: #9aa0ab; }
.thock .section { font-size: 12px; font-weight: 700; color: #9aa0ab; letter-spacing: 1px; }
.thock .card { background-color: #272a31; border-radius: 12px; padding: 14px 16px; }
.thock .packname { font-weight: 700; }
.thock .packdesc { color: #9aa0ab; font-size: 12px; }
.thock .note { color: #7d828c; font-size: 11px; }
.thock button.try { padding: 2px 12px; }
.thock scale trough { min-height: 6px; }
"""


class Tray:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self._sync = False
        self.ind = AI.Indicator.new("thock", ICON_ON, AI.IndicatorCategory.APPLICATION_STATUS)
        self.ind.set_status(AI.IndicatorStatus.ACTIVE)
        self.ind.set_title("Thock")
        self._build()
        self.refresh()
        self.cfg.on_change(lambda k, v, s: GLib.idle_add(self.refresh))

    def _build(self):
        m = Gtk.Menu()
        self.mi_enabled = Gtk.CheckMenuItem(label="Sounds on")
        self.mi_enabled.connect("toggled", lambda w: self._set("enabled", w.get_active()))
        m.append(self.mi_enabled)
        m.append(Gtk.SeparatorMenuItem())

        def radio_sub(label, items, key):
            top = Gtk.MenuItem(label=label)
            sub = Gtk.Menu()
            group = None
            out = []
            for text, value in items:
                it = Gtk.RadioMenuItem.new_with_label_from_widget(group, text)
                group = it
                it.connect("toggled", lambda w, v=value: w.get_active() and self._set(key, v))
                sub.append(it)
                out.append((it, value))
            top.set_submenu(sub)
            m.append(top)
            return out

        self.r_pack = radio_sub("Sound pack", [(p["name"], p["id"]) for p in list_packs()], "pack")
        self.r_vol = radio_sub("Volume", [(f"{v}%", v / 100.0) for v in VOLUMES], "volume")
        self.r_tone = radio_sub("Tone", TONES, "tone")
        m.append(Gtk.SeparatorMenuItem())
        self.mi_mouse = Gtk.CheckMenuItem(label="Mouse clicks")
        self.mi_mouse.connect("toggled", lambda w: self._set("mouse", w.get_active()))
        m.append(self.mi_mouse)
        self.mi_spatial = Gtk.CheckMenuItem(label="Spatial audio")
        self.mi_spatial.connect("toggled", lambda w: self._set("spatial", w.get_active()))
        m.append(self.mi_spatial)
        m.append(Gtk.SeparatorMenuItem())
        s = Gtk.MenuItem(label="Settings…")
        s.connect("activate", lambda w: self.app.show_settings())
        m.append(s)
        q = Gtk.MenuItem(label="Quit Thock")
        q.connect("activate", lambda w: self.app.quit())
        m.append(q)
        m.show_all()
        self.ind.set_menu(m)
        self.ind.set_secondary_activate_target(self.mi_enabled)

    def _set(self, key, value):
        if not self._sync:
            self.cfg.set(key, value, source="tray")

    def refresh(self):
        self._sync = True
        c = self.cfg
        self.mi_enabled.set_active(c["enabled"])
        self.mi_mouse.set_active(c["mouse"])
        self.mi_spatial.set_active(c["spatial"])
        for it, v in self.r_pack:
            if v == c["pack"]:
                it.set_active(True)
        nearest = min(self.r_vol, key=lambda iv: abs(iv[1] - c["volume"]))
        nearest[0].set_active(True)
        nearest = min(self.r_tone, key=lambda iv: abs(iv[1] - c["tone"]))
        nearest[0].set_active(True)
        self.ind.set_icon_full(ICON_ON if c["enabled"] else ICON_OFF, "Thock on" if c["enabled"] else "Thock off")
        self._sync = False
        return False


class SettingsWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="Thock")
        self.app = app
        self.cfg = app.cfg
        self._sync = False
        self.set_default_size(460, -1)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_from_file(os.path.join(ROOT, "data", "thock.svg"))
        self.get_style_context().add_class("thock")
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.connect("delete-event", lambda *a: (self.hide(), True)[1])

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=20)
        self.add(outer)

        head = Gtk.Box(spacing=12)
        tbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        t = Gtk.Label(label="Thock", xalign=0); t.get_style_context().add_class("title")
        st = Gtk.Label(label="Mechanical keyboard sounds while you type", xalign=0); st.get_style_context().add_class("subtitle")
        tbox.pack_start(t, False, False, 0); tbox.pack_start(st, False, False, 0)
        head.pack_start(tbox, True, True, 0)
        self.sw_enabled = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.sw_enabled.connect("notify::active", lambda w, p: self._set("enabled", w.get_active()))
        head.pack_end(self.sw_enabled, False, False, 0)
        outer.pack_start(head, False, False, 0)

        # Sound
        outer.pack_start(self._section("SOUND"), False, False, 0)
        card = self._card(); outer.pack_start(card, False, False, 0)
        grid = Gtk.Grid(column_spacing=12, row_spacing=10); card.add(grid)
        grid.attach(Gtk.Label(label="Volume", xalign=0), 0, 0, 1, 1)
        self.sc_vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.sc_vol.set_hexpand(True); self.sc_vol.set_value_pos(Gtk.PositionType.RIGHT)
        self.sc_vol.connect("value-changed", lambda w: self._debounce("volume", w.get_value() / 100.0))
        grid.attach(self.sc_vol, 1, 0, 2, 1)
        grid.attach(Gtk.Label(label="Tone", xalign=0), 0, 1, 1, 1)
        tone_box = Gtk.Box(spacing=8)
        lt = Gtk.Label(label="Thock"); lt.get_style_context().add_class("packdesc")
        rt = Gtk.Label(label="Clack"); rt.get_style_context().add_class("packdesc")
        self.sc_tone = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -100, 100, 5)
        self.sc_tone.set_draw_value(False); self.sc_tone.set_hexpand(True)
        self.sc_tone.add_mark(0, Gtk.PositionType.BOTTOM, None)
        self.sc_tone.connect("value-changed", lambda w: self._debounce("tone", w.get_value() / 100.0))
        tone_box.pack_start(lt, False, False, 0); tone_box.pack_start(self.sc_tone, True, True, 0); tone_box.pack_start(rt, False, False, 0)
        grid.attach(tone_box, 1, 1, 2, 1)

        # Packs
        outer.pack_start(self._section("SWITCH PACK"), False, False, 0)
        card = self._card(); outer.pack_start(card, False, False, 0)
        pbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); card.add(pbox)
        self.pack_radios = []
        group = None
        for p in list_packs():
            row = Gtk.Box(spacing=10)
            rb = Gtk.RadioButton.new_from_widget(group); group = rb
            rb.connect("toggled", lambda w, pid=p["id"]: w.get_active() and self._set("pack", pid))
            lbl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            n = Gtk.Label(label=p["name"], xalign=0); n.get_style_context().add_class("packname")
            d = Gtk.Label(label=p["description"], xalign=0); d.get_style_context().add_class("packdesc")
            d.set_line_wrap(True); d.set_max_width_chars(42)
            lbl.pack_start(n, False, False, 0); lbl.pack_start(d, False, False, 0)
            rb.add(lbl)
            row.pack_start(rb, True, True, 0)
            b = Gtk.Button(label="Try", valign=Gtk.Align.CENTER); b.get_style_context().add_class("try")
            b.connect("clicked", lambda w, pid=p["id"]: self.app.engine.preview(pid))
            row.pack_end(b, False, False, 0)
            pbox.pack_start(row, False, False, 0)
            self.pack_radios.append((rb, p["id"]))

        # Options
        outer.pack_start(self._section("OPTIONS"), False, False, 0)
        card = self._card(); outer.pack_start(card, False, False, 0)
        obox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); card.add(obox)
        self.toggles = {}
        for key, label in (("release", "Key release sounds"), ("mouse", "Mouse click sounds"),
                           ("spatial", "Spatial audio (left keys left, right keys right)"),
                           ("pitch_variation", "Natural variation (tiny pitch and volume changes)")):
            self.toggles[key] = self._toggle_row(obox, label, lambda w, p, k=key: self._set(k, w.get_active()))
        self.sw_login = self._toggle_row(obox, "Start at login", lambda w, p: self._sync or autostart.set_enabled(w.get_active()))

        note = Gtk.Label(label="Private by design: keys are never recorded, logged or sent anywhere.", xalign=0)
        note.get_style_context().add_class("note"); note.set_line_wrap(True)
        outer.pack_start(note, False, False, 0)

        self._timers = {}
        self.refresh()
        self.cfg.on_change(lambda k, v, s: s != "window" and GLib.idle_add(self.refresh))

    def _section(self, text):
        l = Gtk.Label(label=text, xalign=0); l.get_style_context().add_class("section"); return l

    def _card(self):
        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); b.get_style_context().add_class("card"); return b

    def _toggle_row(self, box, label, cb):
        row = Gtk.Box(spacing=10)
        row.pack_start(Gtk.Label(label=label, xalign=0), True, True, 0)
        sw = Gtk.Switch(valign=Gtk.Align.CENTER)
        sw.connect("notify::active", cb)
        row.pack_end(sw, False, False, 0)
        box.pack_start(row, False, False, 0)
        return sw

    def _set(self, key, value):
        if not self._sync:
            self.cfg.set(key, value, source="window")

    def _debounce(self, key, value):
        if self._sync:
            return
        if key == "volume":
            self._set(key, round(value, 2)); return
        if key in self._timers:
            GLib.source_remove(self._timers[key])
        def fire():
            self._timers.pop(key, None); self._set(key, round(value, 2)); return False
        self._timers[key] = GLib.timeout_add(180, fire)

    def refresh(self):
        self._sync = True
        c = self.cfg
        self.sw_enabled.set_active(c["enabled"])
        self.sc_vol.set_value(round(c["volume"] * 100))
        self.sc_tone.set_value(round(c["tone"] * 100))
        for rb, pid in self.pack_radios:
            if pid == c["pack"]:
                rb.set_active(True)
        for k, sw in self.toggles.items():
            sw.set_active(c[k])
        self.sw_login.set_active(autostart.is_enabled())
        self._sync = False
        return False
