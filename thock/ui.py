"""Tray menu and settings window (GTK 3)."""
import os
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gtk, Gdk, GLib, Gio, AyatanaAppIndicator3 as AI

from . import autostart, __version__
from .packs import list_packs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_APP = os.path.join(ROOT, "data", "thock.svg")
ICON_ON = os.path.join(ROOT, "data", "thock-tray.svg")
ICON_OFF = os.path.join(ROOT, "data", "thock-tray-off.svg")

VOLUMES = [10, 25, 40, 60, 80, 100]
TONES = [("Deep Thock", -1.0), ("Thock", -0.5), ("Balanced", 0.0), ("Clack", 0.5), ("Bright Clack", 1.0)]
ACCENT = "#E95420"

PALETTES = {
    "light": dict(bg="#F6F6F7", side="#EEEEF0", panel="#FFFFFF", border="rgba(0,0,0,0.10)",
                  sep="rgba(0,0,0,0.07)", fg="#1F2023", muted="#6B6E76", hover="rgba(0,0,0,0.035)",
                  sel="rgba(233,84,32,0.08)", side_sel="rgba(0,0,0,0.07)"),
    "dark": dict(bg="#1E1F22", side="#18191B", panel="#26272B", border="rgba(255,255,255,0.08)",
                 sep="rgba(255,255,255,0.06)", fg="#ECECEF", muted="#9A9CA3", hover="rgba(255,255,255,0.04)",
                 sel="rgba(233,84,32,0.14)", side_sel="rgba(255,255,255,0.08)"),
}

CSS = """
@define-color t_bg {bg}; @define-color t_side {side}; @define-color t_panel {panel};
@define-color t_border {border}; @define-color t_sep {sep}; @define-color t_fg {fg};
@define-color t_muted {muted}; @define-color t_hover {hover}; @define-color t_sel {sel};
@define-color t_side_sel {side_sel}; @define-color t_accent {accent};

window.thock {{ background-color: @t_bg; color: @t_fg; }}
.thock .content {{ background-color: @t_bg; }}
.thock .sidebar {{ background-color: @t_side; border-right: 1px solid @t_border; padding: 16px 8px; }}
.thock .sidebar list {{ background-color: transparent; }}
.thock .sidebar row {{ border-radius: 8px; padding: 8px 8px; margin-bottom: 2px; color: @t_fg; }}
.thock .sidebar row:hover {{ background-color: @t_hover; }}
.thock .sidebar row:selected {{ background-color: @t_side_sel; color: @t_fg; }}
.thock .sidebar row:selected image {{ color: @t_accent; }}
.thock .sidebar .brand {{ font-weight: 700; font-size: 13px; color: @t_muted; padding: 0 8px 8px 8px; }}

.thock .app-title {{ font-size: 20px; font-weight: 700; }}
.thock .app-sub {{ color: @t_muted; font-size: 13px; }}
.thock .heading {{ font-size: 13px; font-weight: 700; color: @t_fg; }}
.thock .heading-sub {{ font-size: 12px; color: @t_muted; }}
.thock .muted {{ color: @t_muted; }}
.thock .small {{ font-size: 12px; }}
.thock .value {{ font-feature-settings: "tnum"; color: @t_muted; }}

.thock .panel {{ background-color: @t_panel; border: 1px solid @t_border; border-radius: 12px; }}
.thock .panel list {{ background-color: transparent; }}
.thock .panel row {{ padding: 0; border-bottom: 1px solid @t_sep; }}
.thock .panel row:last-child {{ border-bottom: none; }}
.thock .panel row:hover {{ background-color: @t_hover; }}
.thock .panel row:selected {{ background-color: @t_sel; color: @t_fg; }}
.thock .panel row:first-child {{ border-top-left-radius: 11px; border-top-right-radius: 11px; }}
.thock .panel row:last-child {{ border-bottom-left-radius: 11px; border-bottom-right-radius: 11px; }}
.thock .panel row:focus {{ outline: 2px solid alpha(@t_accent, 0.6); outline-offset: -2px; }}
.thock .prow {{ padding: 12px 16px; }}
.thock .pname {{ font-weight: 600; }}
.thock .pdesc {{ color: @t_muted; font-size: 12px; }}
.thock .dot {{ min-width: 16px; min-height: 16px; border-radius: 999px;
               border: 2px solid alpha(@t_fg, 0.30); background-color: transparent; }}
.thock row:selected .dot {{ border-color: @t_accent; background-color: @t_accent;
                            box-shadow: inset 0 0 0 3px @t_panel; }}
.thock .badge {{ color: @t_accent; font-size: 11px; font-weight: 700; }}

.thock button.pill {{ border-radius: 8px; padding: 4px 12px; min-height: 24px; }}
.thock button.danger {{ color: #C7162B; }}
.thock button.flat-link {{ color: @t_accent; }}
.thock scale highlight {{ background-color: @t_accent; }}
.thock scale trough {{ min-height: 4px; border-radius: 4px; }}
.thock switch:checked {{ background-color: @t_accent; border-color: @t_accent; }}
.thock .footer {{ color: @t_muted; font-size: 11px; }}
"""


def _system_dark():
    forced = os.environ.get("THOCK_THEME")
    if forced in ("light", "dark"):
        return forced == "dark"
    try:
        s = Gio.Settings.new("org.gnome.desktop.interface")
        if s.get_string("color-scheme") == "prefer-dark":
            return True
        return s.get_string("gtk-theme").lower().endswith("-dark")
    except Exception:
        return False


# --------------------------------------------------------------------------------------- tray
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

    def _check(self, menu, label, key):
        it = Gtk.CheckMenuItem(label=label)
        it.connect("toggled", lambda w: self._set(key, w.get_active()))
        menu.append(it)
        return it

    def _radio_sub(self, menu, label, items, key):
        top = Gtk.MenuItem(label=label)
        sub = Gtk.Menu()
        group, out = None, []
        for text, value in items:
            it = Gtk.RadioMenuItem.new_with_label_from_widget(group, text)
            group = it
            it.connect("toggled", lambda w, v=value: w.get_active() and self._set(key, v))
            sub.append(it)
            out.append((it, value))
        top.set_submenu(sub)
        menu.append(top)
        return top, out

    def _build(self):
        m = Gtk.Menu()
        self.mi_enabled = self._check(m, "Sounds On", "enabled")
        m.append(Gtk.SeparatorMenuItem())
        self.packs = list_packs()
        self.top_pack, self.r_pack = self._radio_sub(m, "Sound Pack", [(p["name"], p["id"]) for p in self.packs], "pack")
        self.top_vol, self.r_vol = self._radio_sub(m, "Volume", [(f"{v}%", v / 100.0) for v in VOLUMES], "volume")
        self.top_tone, self.r_tone = self._radio_sub(m, "Tone", TONES, "tone")
        m.append(Gtk.SeparatorMenuItem())
        self.mi_release = self._check(m, "Key Release Sounds", "release")
        self.mi_mouse = self._check(m, "Mouse Clicks", "mouse")
        self.mi_spatial = self._check(m, "Spatial Audio", "spatial")
        self.mi_var = self._check(m, "Natural Variation", "pitch_variation")
        m.append(Gtk.SeparatorMenuItem())
        s = Gtk.MenuItem(label="Settings…")
        s.connect("activate", lambda w: self.app.show_settings())
        m.append(s)
        m.append(Gtk.SeparatorMenuItem())
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
        for it, k in ((self.mi_enabled, "enabled"), (self.mi_release, "release"), (self.mi_mouse, "mouse"),
                      (self.mi_spatial, "spatial"), (self.mi_var, "pitch_variation")):
            it.set_active(c[k])
        name = c["pack"]
        for it, v in self.r_pack:
            if v == c["pack"]:
                it.set_active(True)
                name = it.get_label()
        vol = min(self.r_vol, key=lambda iv: abs(iv[1] - c["volume"]))
        vol[0].set_active(True)
        tone = min(self.r_tone, key=lambda iv: abs(iv[1] - c["tone"]))
        tone[0].set_active(True)
        self.top_pack.set_label(f"Sound Pack: {name}")
        self.top_vol.set_label(f"Volume: {round(c['volume'] * 100)}%")
        self.top_tone.set_label(f"Tone: {tone[0].get_label()}")
        self.ind.set_icon_full(ICON_ON if c["enabled"] else ICON_OFF, "Thock on" if c["enabled"] else "Thock off")
        self._sync = False
        return False


# ----------------------------------------------------------------------------- settings window
def _label(text, *classes, xalign=0.0, wrap=False):
    l = Gtk.Label(label=text, xalign=xalign)
    for c in classes:
        l.get_style_context().add_class(c)
    if wrap:
        l.set_line_wrap(True)
    return l


def _cls(w, *classes):
    for c in classes:
        w.get_style_context().add_class(c)
    return w


def tone_text(t):
    p = round(abs(t) * 100)
    if p < 3:
        return "Balanced"
    return f"Thock {p}%" if t < 0 else f"Clack {p}%"


class SettingsWindow(Gtk.ApplicationWindow):
    SECTIONS = [("sound", "Sound", "audio-volume-high-symbolic"),
                ("tone", "Tone", "multimedia-equalizer-symbolic"),
                ("behavior", "Behavior", "input-keyboard-symbolic"),
                ("general", "General", "preferences-system-symbolic")]

    def __init__(self, app):
        super().__init__(application=app, title="Thock Settings")
        self.app = app
        self.cfg = app.cfg
        self._sync = False
        self._scroll_anim = None
        self._timers = {}
        self.set_default_size(800, 640)
        self.set_size_request(560, 480)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_from_file(ICON_APP)
        self.set_wmclass("thock", "Thock")
        _cls(self, "thock")
        self._css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self._css,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._apply_theme()
        try:
            self._gs = Gio.Settings.new("org.gnome.desktop.interface")
            self._gs.connect("changed::color-scheme", lambda *a: self._apply_theme())
            self._gs.connect("changed::gtk-theme", lambda *a: self._apply_theme())
        except Exception:
            self._gs = None
        self.connect("delete-event", lambda *a: (self.hide(), True)[1])

        hb = Gtk.HeaderBar(title="Thock Settings", show_close_button=True)
        self.set_titlebar(hb)

        root = Gtk.Box()
        self.add(root)
        root.pack_start(self._build_sidebar(), False, False, 0)
        self.scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        _cls(self.scroller, "content")
        root.pack_start(self.scroller, True, True, 0)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, halign=Gtk.Align.CENTER,
                      margin_top=24, margin_bottom=32, margin_start=32, margin_end=32)
        col.set_size_request(480, -1)
        self.content = col
        clamp = Gtk.Box()
        clamp.set_center_widget(col)
        self.scroller.add(clamp)
        self.vadj = self.scroller.get_vadjustment()
        self.vadj.connect("value-changed", self._on_scroll)

        col.pack_start(self._build_header(), False, False, 0)
        self.anchors = {}
        self._section(col, "sound", "Sound", "Choose a switch pack and set the overall level.", self._build_sound())
        self._section(col, "tone", "Tone", "Shape the character of every keystroke.", self._build_tone())
        self._section(col, "behavior", "Behavior", "How Thock reacts to your keyboard and mouse.", self._build_behavior())
        self._section(col, "general", "General", None, self._build_general())
        foot = _label("Private by design: keystrokes are never recorded, logged or sent anywhere. "
                      "Thock makes no network connections.", "footer", wrap=True)
        foot.set_margin_top(24)
        col.pack_start(foot, False, False, 0)

        self.connect("size-allocate", self._on_size)
        self.refresh()
        self.cfg.on_change(lambda k, v, s: s != "window" and GLib.idle_add(self.refresh))
        self.cfg.on_change(lambda k, v, s: GLib.idle_add(self._refresh_header))

    # -- theme
    def _apply_theme(self):
        dark = _system_dark()
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", dark)
        pal = dict(PALETTES["dark" if dark else "light"], accent=ACCENT)
        self._css.load_from_data(CSS.format(**pal).encode())

    # -- layout pieces
    def _build_sidebar(self):
        box = _cls(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "sidebar")
        box.set_size_request(196, -1)
        self.sidebar = box
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.side_rows = {}
        for sid, title, icon in self.SECTIONS:
            row = Gtk.ListBoxRow()
            h = Gtk.Box(spacing=12)
            h.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU), False, False, 0)
            h.pack_start(_label(title), False, False, 0)
            row.add(h)
            row.sid = sid
            lb.add(row)
            self.side_rows[sid] = row
        lb.connect("row-activated", lambda l, r: self._scroll_to(r.sid))
        self.side_list = lb
        box.pack_start(lb, False, False, 0)
        return box

    def _build_header(self):
        h = Gtk.Box(spacing=16, margin_bottom=8)
        try:
            from gi.repository import GdkPixbuf
            pb = GdkPixbuf.Pixbuf.new_from_file_at_size(ICON_APP, 48, 48)
            h.pack_start(Gtk.Image.new_from_pixbuf(pb), False, False, 0)
        except Exception:
            pass
        t = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        t.pack_start(_label("Thock", "app-title"), False, False, 0)
        self.sub = _label("", "app-sub")
        t.pack_start(self.sub, False, False, 0)
        h.pack_start(t, True, True, 0)
        self.sw_enabled = Gtk.Switch(valign=Gtk.Align.CENTER, tooltip_text="Turn all sounds on or off")
        self.sw_enabled.connect("notify::active", lambda w, p: self._set("enabled", w.get_active()))
        h.pack_end(self.sw_enabled, False, False, 0)
        return h

    def _section(self, col, sid, title, sub, body):
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=32, margin_bottom=8,
                       margin_start=4)
        head.pack_start(_label(title, "heading"), False, False, 0)
        if sub:
            head.pack_start(_label(sub, "heading-sub"), False, False, 0)
        col.pack_start(head, False, False, 0)
        col.pack_start(body, False, False, 0)
        self.anchors[sid] = head

    def _panel(self):
        return _cls(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "panel")

    def _list(self, panel, selectable=False):
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE if selectable else Gtk.SelectionMode.NONE)
        lb.set_activate_on_single_click(True)
        panel.pack_start(lb, False, False, 0)
        return lb

    def _row(self, lb, title, subtitle=None, control=None, activatable=False):
        row = Gtk.ListBoxRow(activatable=activatable, selectable=False)
        h = _cls(Gtk.Box(spacing=16), "prow")
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        v.pack_start(_label(title), False, False, 0)
        if subtitle:
            v.pack_start(_label(subtitle, "pdesc", wrap=True), False, False, 0)
        h.pack_start(v, True, True, 0)
        if control is not None:
            control.set_valign(Gtk.Align.CENTER)
            h.pack_end(control, False, False, 0)
        row.add(h)
        lb.add(row)
        return row

    def _build_sound(self):
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        panel = self._panel()
        lb = self._list(panel, selectable=True)
        self.pack_rows = {}
        for p in list_packs():
            row = Gtk.ListBoxRow()
            row.pid = p["id"]
            h = _cls(Gtk.Box(spacing=16), "prow")
            h.pack_start(_cls(Gtk.Box(valign=Gtk.Align.CENTER), "dot"), False, False, 0)
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
            v.pack_start(_label(p["name"], "pname"), False, False, 0)
            v.pack_start(_label(p["description"], "pdesc", wrap=True), False, False, 0)
            h.pack_start(v, True, True, 0)
            b = Gtk.Button(valign=Gtk.Align.CENTER, tooltip_text=f"Preview {p['name']}")
            bh = Gtk.Box(spacing=8)
            bh.pack_start(Gtk.Image.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.MENU), False, False, 0)
            bh.pack_start(Gtk.Label(label="Try"), False, False, 0)
            b.add(bh)
            _cls(b, "pill")
            b.connect("clicked", lambda w, pid=p["id"]: self.app.engine.preview(pid))
            h.pack_end(b, False, False, 0)
            row.add(h)
            lb.add(row)
            self.pack_rows[p["id"]] = row
        lb.connect("row-selected", lambda l, r: r is not None and self._set("pack", r.pid))
        self.pack_list = lb
        wrap.pack_start(panel, False, False, 0)

        panel = self._panel()
        lb = self._list(panel)
        row = Gtk.ListBoxRow(activatable=False, selectable=False)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=16, margin_end=16,
                    margin_top=12, margin_bottom=12)
        top = Gtk.Box(spacing=8)
        top.pack_start(_label("Volume"), True, True, 0)
        self.vol_val = _label("", "value", xalign=1.0)
        self.vol_val.set_width_chars(4)
        top.pack_start(self.vol_val, False, False, 0)
        v.pack_start(top, False, False, 0)
        h = Gtk.Box(spacing=8)
        h.pack_start(_cls(Gtk.Image.new_from_icon_name("audio-volume-low-symbolic", Gtk.IconSize.MENU), "muted"), False, False, 0)
        self.sc_vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.sc_vol.set_draw_value(False)
        self.sc_vol.set_hexpand(True)
        self.sc_vol.connect("value-changed", self._on_vol)
        h.pack_start(self.sc_vol, True, True, 0)
        h.pack_start(_cls(Gtk.Image.new_from_icon_name("audio-volume-high-symbolic", Gtk.IconSize.MENU), "muted"), False, False, 0)
        v.pack_start(h, False, False, 0)
        row.add(v)
        lb.add(row)
        wrap.pack_start(panel, False, False, 0)
        return wrap

    def _build_tone(self):
        panel = self._panel()
        lb = self._list(panel)
        row = Gtk.ListBoxRow(activatable=False, selectable=False)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=16, margin_end=16,
                    margin_top=12, margin_bottom=12)
        top = Gtk.Box(spacing=8)
        top.pack_start(_label("Character"), True, True, 0)
        self.tone_val = _label("", "value", xalign=1.0)
        top.pack_start(self.tone_val, False, False, 0)
        reset = _cls(Gtk.Button(label="Reset", relief=Gtk.ReliefStyle.NONE, tooltip_text="Back to balanced"), "pill", "flat-link")
        reset.connect("clicked", lambda w: self.sc_tone.set_value(0))
        top.pack_start(reset, False, False, 0)
        v.pack_start(top, False, False, 0)
        self.sc_tone = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -100, 100, 5)
        self.sc_tone.set_draw_value(False)
        self.sc_tone.set_has_origin(False)
        for m in (-100, -50, 0, 50, 100):
            self.sc_tone.add_mark(m, Gtk.PositionType.BOTTOM, None)
        self.sc_tone.connect("value-changed", self._on_tone)
        v.pack_start(self.sc_tone, False, False, 0)
        ends = Gtk.Box()
        ends.pack_start(_label("Thock · deeper, softer", "pdesc"), True, True, 0)
        ends.pack_end(_label("Clack · brighter, crisper", "pdesc", xalign=1.0), True, True, 0)
        v.pack_start(ends, False, False, 0)
        row.add(v)
        lb.add(row)
        return panel

    def _build_behavior(self):
        panel = self._panel()
        lb = self._list(panel)
        self.toggles = {}
        for key, title, sub in (
                ("release", "Key release sounds", "Play a second, softer sound when a key comes back up"),
                ("pitch_variation", "Natural variation", "Tiny pitch and volume changes so repeated keys sound real"),
                ("spatial", "Spatial audio", "Left-hand keys play on the left, right-hand keys on the right"),
                ("mouse", "Mouse clicks", "Click sounds for the left, right and middle buttons")):
            sw = Gtk.Switch()
            sw.connect("notify::active", lambda w, p, k=key: self._set(k, w.get_active()))
            self._row(lb, title, sub, sw)
            self.toggles[key] = sw
        return panel

    def _build_general(self):
        panel = self._panel()
        lb = self._list(panel)
        self.sw_login = Gtk.Switch()
        self.sw_login.connect("notify::active", lambda w, p: self._sync or autostart.set_enabled(w.get_active()))
        self._row(lb, "Start at login", "Launch Thock in the tray when you sign in", self.sw_login)
        q = _cls(Gtk.Button(label="Quit Thock"), "pill", "danger")
        q.connect("clicked", lambda w: self.app.quit())
        self._row(lb, "Quit", "Stop all sounds and remove the tray icon until next launch", q)
        self._row(lb, "Version", None, _label(f"Thock {__version__}", "value"))
        return panel

    # -- behaviour
    def _on_size(self, w, alloc):
        show = alloc.width >= 700
        if self.sidebar.get_visible() != show:
            self.sidebar.set_visible(show)

    def _scroll_to(self, sid):
        w = self.anchors[sid]
        r = w.translate_coordinates(self.content, 0, 0)
        if not r:
            return
        target = min(max(0, r[1] + self.content.get_margin_top() - 16),
                     self.vadj.get_upper() - self.vadj.get_page_size())
        start = self.vadj.get_value()
        t0 = GLib.get_monotonic_time()
        if self._scroll_anim:
            GLib.source_remove(self._scroll_anim)
        self._spy_block = sid

        def step():
            k = min(1.0, (GLib.get_monotonic_time() - t0) / 220000.0)
            e = 1 - (1 - k) ** 3
            self.vadj.set_value(start + (target - start) * e)
            if k >= 1.0:
                self._scroll_anim = None
                GLib.timeout_add(60, self._unblock_spy)
                return False
            return True
        self._scroll_anim = GLib.timeout_add(12, step)

    def _unblock_spy(self):
        self._spy_block = None
        return False

    def _on_scroll(self, adj):
        if getattr(self, "_spy_block", None):
            return
        cur = self.SECTIONS[0][0]
        y = adj.get_value() + 48
        if adj.get_value() + adj.get_page_size() >= adj.get_upper() - 2:
            cur = self.SECTIONS[-1][0]
        else:
            for sid, _, _ in self.SECTIONS:
                r = self.anchors[sid].translate_coordinates(self.content, 0, 0)
                if r and r[1] <= y:
                    cur = sid
        row = self.side_rows[cur]
        if self.side_list.get_selected_row() is not row:
            self.side_list.select_row(row)

    def _set(self, key, value):
        if not self._sync:
            self.cfg.set(key, value, source="window")

    def _on_vol(self, w):
        self.vol_val.set_text(f"{int(w.get_value())}%")
        if not self._sync:
            self._set("volume", round(w.get_value() / 100.0, 2))

    def _on_tone(self, w):
        t = w.get_value() / 100.0
        self.tone_val.set_text(tone_text(t))
        if self._sync:
            return
        if "tone" in self._timers:
            GLib.source_remove(self._timers["tone"])

        def fire():
            self._timers.pop("tone", None)
            self._set("tone", round(t, 2))
            return False
        self._timers["tone"] = GLib.timeout_add(180, fire)

    def _refresh_header(self):
        c = self.cfg
        name = next((p["name"] for p in list_packs() if p["id"] == c["pack"]), c["pack"])
        self.sub.set_text(f"Playing {name}" if c["enabled"] else "Paused · sounds are off")
        return False

    def refresh(self):
        self._sync = True
        c = self.cfg
        self.sw_enabled.set_active(c["enabled"])
        self.sc_vol.set_value(round(c["volume"] * 100))
        self.vol_val.set_text(f"{round(c['volume'] * 100)}%")
        self.sc_tone.set_value(round(c["tone"] * 100))
        self.tone_val.set_text(tone_text(c["tone"]))
        row = self.pack_rows.get(c["pack"])
        if row is not None and self.pack_list.get_selected_row() is not row:
            self.pack_list.select_row(row)
        for k, sw in self.toggles.items():
            sw.set_active(c[k])
        self.sw_login.set_active(autostart.is_enabled())
        self._refresh_header()
        if self.side_list.get_selected_row() is None:
            self.side_list.select_row(self.side_rows["sound"])
        self._sync = False
        return False
