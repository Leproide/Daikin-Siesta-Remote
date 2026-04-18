"""
Daikin Siesta — telecomando virtuale GUI completo.
Supporta 4 modalità (Cool/Heat/Dry/Fan) + temperatura, ventola, swing, LED, X-FAN.

Uso:
    python daikin_remote_gui.py                    # apre la GUI
    python daikin_remote_gui.py --send nome        # invia il preset e termina
    python daikin_remote_gui.py --list             # mostra i preset salvati
    python daikin_remote_gui.py --delete nome      # elimina un preset
"""

import tkinter as tk
from tkinter import simpledialog, messagebox
import threading, json, os, sys, argparse

try:
    from tinytuya import Contrib
    from daikin_siesta_encoder import generate
except ImportError as e:
    print(f"Import mancante: {e}")
    raise SystemExit(1)


# ── CONFIG DEVICE ─────────────────────────────────────────────
# Copy config.example.py to config.py and fill in your credentials.
# Recover them via: python -m tinytuya wizard
try:
    from config import DEVICE_ID, DEVICE_IP, DEVICE_KEY
except ImportError:
    print("ERROR: config.py not found.")
    print("Copy config.example.py to config.py and fill in your credentials.")
    print("Get them via: python -m tinytuya wizard")
    raise SystemExit(1)

# File dove salvare i preset (nella stessa cartella dello script)
PRESETS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "daikin_presets.json"
)

# ── PALETTE ───────────────────────────────────────────────────
BG        = "#1a1a1a"
PANEL     = "#2b2b2b"
DISPLAY   = "#0d3a3a"
DISPLAY_T = "#7fffd4"
BTN       = "#3a3a3a"
BTN_ACT   = "#4a7fff"
BTN_WARN  = "#d94646"
BTN_OK    = "#3fa64a"
BTN_LED   = "#e6b800"
BTN_XFAN  = "#17a2b8"
BTN_SAVE  = "#8a56c2"
TEXT      = "#e0e0e0"
MUTED     = "#808080"

MODE_COLORS = {
    "cool": "#4a9fff", "heat": "#ff6b4a",
    "dry":  "#ffb94a", "fan":  "#9f9f9f",
}


# ── Gestione preset ──────────────────────────────────────────
def load_presets():
    if not os.path.exists(PRESETS_FILE):
        return {}
    try:
        with open(PRESETS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_presets(presets):
    with open(PRESETS_FILE, "w") as f:
        json.dump(presets, f, indent=2)


# ── Invio senza GUI ──────────────────────────────────────────
def connect_device():
    d = Contrib.IRRemoteControlDevice(
        DEVICE_ID, DEVICE_IP, DEVICE_KEY,
        version=3.3, control_type=1, persist=True,
    )
    d.set_socketTimeout(3)
    return d

def send_preset(name):
    """Carica un preset e lo invia, per uso CLI."""
    presets = load_presets()
    if name not in presets:
        print(f"✗ Preset '{name}' non trovato")
        print(f"  Disponibili: {', '.join(sorted(presets.keys())) or '(nessuno)'}")
        sys.exit(1)

    state = presets[name]
    print(f"→ invio preset '{name}': {state}")
    try:
        device = connect_device()
        code = generate(**state)
        try: device.send_button(code)
        except Exception: pass
        print("✓ inviato")
        sys.exit(0)
    except Exception as e:
        print(f"✗ errore connessione: {e}")
        sys.exit(2)

def list_presets():
    presets = load_presets()
    if not presets:
        print("(nessun preset salvato)")
        return
    print(f"{len(presets)} preset in {PRESETS_FILE}:\n")
    for name in sorted(presets.keys()):
        s = presets[name]
        if not s.get("power", True):
            desc = "OFF"
        else:
            desc = (f"{s.get('mode','cool').upper()} {s.get('temp',22)}°C "
                    f"{'TURBO' if s.get('turbo') else 'AUTO'} "
                    f"sw:{'on' if s.get('swing') else 'off'} "
                    f"led:{'on' if s.get('led',True) else 'off'} "
                    f"xf:{'on' if s.get('xfan',True) else 'off'}")
        print(f"  {name:25s} → {desc}")

def delete_preset(name):
    presets = load_presets()
    if name not in presets:
        print(f"✗ Preset '{name}' non trovato")
        sys.exit(1)
    del presets[name]
    save_presets(presets)
    print(f"✓ preset '{name}' eliminato")


# ── GUI ───────────────────────────────────────────────────────
class DaikinRemote:
    def __init__(self, root):
        self.root = root
        self.root.title("Daikin Siesta")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        self.power = False
        self.mode  = "cool"
        self.temp  = 22
        self.turbo = False
        self.swing = False
        self.led   = True
        self.xfan  = True

        self.device = None
        self._build_ui()
        self._refresh_display()

    def _build_ui(self):
        body = tk.Frame(self.root, bg=PANEL, bd=0, padx=20, pady=20)
        body.pack(padx=15, pady=15)

        tk.Label(body, text="DAIKIN", bg=PANEL, fg=TEXT,
                 font=("Arial Black", 14, "bold")).pack(pady=(0, 4))
        tk.Label(body, text="SIESTA", bg=PANEL, fg=MUTED,
                 font=("Arial", 8)).pack(pady=(0, 10))

        # Display
        self.display = tk.Frame(body, bg=DISPLAY, padx=15, pady=12,
                                  relief="sunken", bd=2)
        self.display.pack(fill="x", pady=(0, 15))
        self.lbl_power = tk.Label(self.display, text="OFF",
                                   bg=DISPLAY, fg=DISPLAY_T,
                                   font=("Consolas", 11, "bold"))
        self.lbl_power.grid(row=0, column=0, sticky="w")
        self.lbl_mode = tk.Label(self.display, text="COOL",
                                  bg=DISPLAY, fg=DISPLAY_T,
                                  font=("Consolas", 11, "bold"))
        self.lbl_mode.grid(row=0, column=1, sticky="e", padx=(60, 0))
        self.lbl_temp = tk.Label(self.display, text="--",
                                  bg=DISPLAY, fg=DISPLAY_T,
                                  font=("Consolas", 36, "bold"))
        self.lbl_temp.grid(row=1, column=0, columnspan=2, pady=(5, 0))
        self.lbl_unit = tk.Label(self.display, text="°C",
                                  bg=DISPLAY, fg=DISPLAY_T,
                                  font=("Consolas", 12))
        self.lbl_unit.grid(row=1, column=2, sticky="sw", pady=(0, 10))
        self.lbl_info = tk.Label(self.display, text="",
                                  bg=DISPLAY, fg=DISPLAY_T,
                                  font=("Consolas", 9))
        self.lbl_info.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.display.columnconfigure(1, weight=1)

        # Power
        self.btn_power = tk.Button(body, text="POWER",
                                    command=self._toggle_power,
                                    bg=BTN_WARN, fg="white",
                                    font=("Arial", 12, "bold"),
                                    width=22, pady=10, relief="flat",
                                    activebackground="#ff6666")
        self.btn_power.pack(pady=(0, 12))

        # Modalità
        mode_frame = tk.LabelFrame(body, text=" MODE ",
                                    bg=PANEL, fg=MUTED,
                                    font=("Arial", 8), padx=8, pady=8)
        mode_frame.pack(fill="x", pady=(0, 10))
        self.mode_buttons = {}
        for m, label in [("cool","❄ COOL"), ("heat","☀ HEAT"),
                          ("dry","💧 DRY"), ("fan","🌀 FAN")]:
            btn = tk.Button(mode_frame, text=label,
                             command=lambda mm=m: self._set_mode(mm),
                             bg=BTN, fg=TEXT,
                             font=("Arial", 9, "bold"),
                             width=8, pady=6, relief="flat")
            btn.pack(side="left", expand=True, fill="x", padx=2)
            self.mode_buttons[m] = btn

        # Temperatura
        temp_row = tk.Frame(body, bg=PANEL)
        temp_row.pack(pady=(0, 12))
        tk.Button(temp_row, text="▼", command=self._temp_down,
                  bg=BTN, fg=TEXT, font=("Arial", 14, "bold"),
                  width=4, pady=8, relief="flat",
                  activebackground=BTN_ACT).pack(side="left", padx=(0, 8))
        tk.Label(temp_row, text="TEMP", bg=PANEL, fg=MUTED,
                 font=("Arial", 10), width=8).pack(side="left")
        tk.Button(temp_row, text="▲", command=self._temp_up,
                  bg=BTN, fg=TEXT, font=("Arial", 14, "bold"),
                  width=4, pady=8, relief="flat",
                  activebackground=BTN_ACT).pack(side="left", padx=(8, 0))

        # Ventola
        fan_frame = tk.LabelFrame(body, text=" FAN ",
                                   bg=PANEL, fg=MUTED,
                                   font=("Arial", 8), padx=10, pady=8)
        fan_frame.pack(fill="x", pady=(0, 10))
        self.btn_auto = tk.Button(fan_frame, text="AUTO",
                                   command=lambda: self._set_turbo(False),
                                   bg=BTN_ACT, fg="white",
                                   font=("Arial", 10, "bold"),
                                   width=10, pady=6, relief="flat")
        self.btn_auto.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.btn_turbo = tk.Button(fan_frame, text="TURBO",
                                    command=lambda: self._set_turbo(True),
                                    bg=BTN, fg=TEXT,
                                    font=("Arial", 10, "bold"),
                                    width=10, pady=6, relief="flat")
        self.btn_turbo.pack(side="left", expand=True, fill="x", padx=(5, 0))

        # Swing
        swing_frame = tk.LabelFrame(body, text=" SWING ",
                                     bg=PANEL, fg=MUTED,
                                     font=("Arial", 8), padx=10, pady=8)
        swing_frame.pack(fill="x", pady=(0, 10))
        self.btn_swing_off = tk.Button(swing_frame, text="OFF",
                                        command=lambda: self._set_swing(False),
                                        bg=BTN_ACT, fg="white",
                                        font=("Arial", 10, "bold"),
                                        width=10, pady=6, relief="flat")
        self.btn_swing_off.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.btn_swing_on = tk.Button(swing_frame, text="ON",
                                       command=lambda: self._set_swing(True),
                                       bg=BTN, fg=TEXT,
                                       font=("Arial", 10, "bold"),
                                       width=10, pady=6, relief="flat")
        self.btn_swing_on.pack(side="left", expand=True, fill="x", padx=(5, 0))

        # LED
        led_frame = tk.LabelFrame(body, text=" LED ",
                                   bg=PANEL, fg=MUTED,
                                   font=("Arial", 8), padx=10, pady=8)
        led_frame.pack(fill="x", pady=(0, 10))
        self.btn_led_off = tk.Button(led_frame, text="OFF",
                                      command=lambda: self._set_led(False),
                                      bg=BTN, fg=TEXT,
                                      font=("Arial", 10, "bold"),
                                      width=10, pady=6, relief="flat")
        self.btn_led_off.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.btn_led_on = tk.Button(led_frame, text="ON",
                                     command=lambda: self._set_led(True),
                                     bg=BTN_LED, fg="black",
                                     font=("Arial", 10, "bold"),
                                     width=10, pady=6, relief="flat")
        self.btn_led_on.pack(side="left", expand=True, fill="x", padx=(5, 0))

        # X-FAN
        xfan_frame = tk.LabelFrame(body, text=" X-FAN ",
                                    bg=PANEL, fg=MUTED,
                                    font=("Arial", 8), padx=10, pady=8)
        xfan_frame.pack(fill="x", pady=(0, 10))
        self.btn_xfan_off = tk.Button(xfan_frame, text="OFF",
                                       command=lambda: self._set_xfan(False),
                                       bg=BTN, fg=TEXT,
                                       font=("Arial", 10, "bold"),
                                       width=10, pady=6, relief="flat")
        self.btn_xfan_off.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.btn_xfan_on = tk.Button(xfan_frame, text="ON",
                                      command=lambda: self._set_xfan(True),
                                      bg=BTN_XFAN, fg="white",
                                      font=("Arial", 10, "bold"),
                                      width=10, pady=6, relief="flat")
        self.btn_xfan_on.pack(side="left", expand=True, fill="x", padx=(5, 0))

        # ── PRESET ──
        preset_frame = tk.LabelFrame(body, text=" PRESET ",
                                      bg=PANEL, fg=MUTED,
                                      font=("Arial", 8), padx=10, pady=8)
        preset_frame.pack(fill="x", pady=(0, 6))

        # Riga salva
        save_row = tk.Frame(preset_frame, bg=PANEL)
        save_row.pack(fill="x", pady=(0, 6))
        tk.Button(save_row, text="💾 SAVE CURRENT COMMAND",
                  command=self._save_preset,
                  bg=BTN_SAVE, fg="white",
                  font=("Arial", 9, "bold"),
                  pady=8, relief="flat").pack(fill="x")

        # Riga carica (dropdown + bottoni)
        load_row = tk.Frame(preset_frame, bg=PANEL)
        load_row.pack(fill="x")

        self.preset_var = tk.StringVar()
        self.preset_menu = tk.OptionMenu(load_row, self.preset_var, "")
        self.preset_menu.config(bg=BTN, fg=TEXT, font=("Arial", 9),
                                 activebackground=BTN_ACT,
                                 highlightthickness=0, relief="flat")
        self.preset_menu["menu"].config(bg=BTN, fg=TEXT)
        self.preset_menu.pack(side="left", expand=True, fill="x", padx=(0, 5))

        tk.Button(load_row, text="LOAD", command=self._load_selected_preset,
                  bg=BTN, fg=TEXT, font=("Arial", 8, "bold"),
                  width=8, pady=4, relief="flat",
                  activebackground=BTN_ACT).pack(side="left", padx=(0, 3))
        tk.Button(load_row, text="✕", command=self._delete_selected_preset,
                  bg=BTN_WARN, fg="white", font=("Arial", 8, "bold"),
                  width=3, pady=4, relief="flat").pack(side="left")

        self._refresh_preset_menu()

        # Status bar
        self.status = tk.Label(self.root, text="Ready",
                                bg=BG, fg=MUTED, font=("Arial", 9),
                                anchor="w", padx=20)
        self.status.pack(fill="x", pady=(0, 8))

    def _refresh_display(self):
        if self.power:
            self.lbl_power.config(text="● ON ", fg=DISPLAY_T)
            self.lbl_mode.config(text=self.mode.upper(),
                                  fg=MODE_COLORS.get(self.mode, DISPLAY_T))
            if self.mode == "fan":
                self.lbl_temp.config(text="--")
            else:
                self.lbl_temp.config(text=f"{self.temp:02d}")
        else:
            self.lbl_power.config(text="○ OFF", fg=MUTED)
            self.lbl_mode.config(text="----", fg=MUTED)
            self.lbl_temp.config(text="--")

        info = []
        info.append("TURBO" if self.turbo else "AUTO ")
        info.append(f"SW:{'ON' if self.swing else 'OFF'}")
        info.append(f"LED:{'ON' if self.led else 'OFF'}")
        info.append(f"XF:{'ON' if self.xfan else 'OFF'}")
        self.lbl_info.config(text="  ".join(info))

        for m, btn in self.mode_buttons.items():
            if m == self.mode and self.power:
                btn.config(bg=MODE_COLORS[m], fg="white")
            else:
                btn.config(bg=BTN, fg=TEXT)

        self.btn_auto.config(bg=BTN_ACT if not self.turbo else BTN,
                              fg="white" if not self.turbo else TEXT)
        self.btn_turbo.config(bg=BTN_ACT if self.turbo else BTN,
                               fg="white" if self.turbo else TEXT)
        self.btn_swing_off.config(bg=BTN_ACT if not self.swing else BTN,
                                    fg="white" if not self.swing else TEXT)
        self.btn_swing_on.config(bg=BTN_ACT if self.swing else BTN,
                                   fg="white" if self.swing else TEXT)
        self.btn_led_off.config(bg=BTN_ACT if not self.led else BTN,
                                  fg="white" if not self.led else TEXT)
        self.btn_led_on.config(bg=BTN_LED if self.led else BTN,
                                 fg="black" if self.led else TEXT)
        self.btn_xfan_off.config(bg=BTN_ACT if not self.xfan else BTN,
                                    fg="white" if not self.xfan else TEXT)
        self.btn_xfan_on.config(bg=BTN_XFAN if self.xfan else BTN,
                                   fg="white" if self.xfan else TEXT)
        self.btn_power.config(bg=BTN_OK if self.power else BTN_WARN,
                               text="ON" if self.power else "OFF")

    # ── Preset ──────────────────────────────────────────────
    def _refresh_preset_menu(self):
        presets = load_presets()
        menu = self.preset_menu["menu"]
        menu.delete(0, "end")
        if not presets:
            self.preset_var.set("(Empty)")
            menu.add_command(label="(no preset)",
                              command=lambda: None)
            return
        names = sorted(presets.keys())
        self.preset_var.set(names[0])
        for name in names:
            menu.add_command(label=name,
                              command=lambda n=name: self.preset_var.set(n))

    def _current_state(self):
        return {
            "power": self.power, "mode": self.mode, "temp": self.temp,
            "turbo": self.turbo, "swing": self.swing,
            "led": self.led, "xfan": self.xfan,
        }

    def _save_preset(self):
        # suggerisci un nome auto basato sullo stato
        if self.power:
            suggested = f"{self.mode}_{self.temp}_"
            suggested += "turbo" if self.turbo else "auto"
            if self.swing: suggested += "_swing"
        else:
            suggested = "off"

        name = simpledialog.askstring(
            "Save preset",
            "Preset name:",
            initialvalue=suggested,
            parent=self.root,
        )
        if not name:
            return
        name = name.strip().replace(" ", "_")
        if not name:
            return

        presets = load_presets()
        if name in presets:
            ok = messagebox.askyesno(
                "Overwrite?",
                f"Preset '{name}' already exists. Overwrite?",
                parent=self.root,
            )
            if not ok:
                return

        presets[name] = self._current_state()
        save_presets(presets)
        self._refresh_preset_menu()
        self.preset_var.set(name)
        self._set_status(f"✓ preset '{name}' saved")

    def _load_selected_preset(self):
        name = self.preset_var.get()
        presets = load_presets()
        if name not in presets:
            self._set_status("Select a valid preset", warn=True); return

        s = presets[name]
        self.power = s.get("power", True)
        self.mode  = s.get("mode", "cool")
        self.temp  = s.get("temp", 22)
        self.turbo = s.get("turbo", False)
        self.swing = s.get("swing", False)
        self.led   = s.get("led", True)
        self.xfan  = s.get("xfan", True)
        self._refresh_display()
        self._set_status(f"preset '{name}' loaded — sending...")
        self._send()

    def _delete_selected_preset(self):
        name = self.preset_var.get()
        presets = load_presets()
        if name not in presets:
            return
        ok = messagebox.askyesno(
            "Delete?", f"Delete preset '{name}'?",
            parent=self.root,
        )
        if not ok: return
        del presets[name]
        save_presets(presets)
        self._refresh_preset_menu()
        self._set_status(f"preset '{name}' deleted")

    # ── Azioni ──────────────────────────────────────────────
    def _toggle_power(self):
        self.power = not self.power
        self._refresh_display(); self._send()

    def _set_mode(self, m):
        if not self.power:
            self._set_status("Switch it on first", warn=True); return
        if self.mode == m: return
        self.mode = m
        self._refresh_display(); self._send()

    def _temp_up(self):
        if not self.power or self.mode == "fan":
            self._set_status("Can't set the temperature here", warn=True); return
        if self.temp < 30:
            self.temp += 1
            self._refresh_display(); self._send()

    def _temp_down(self):
        if not self.power or self.mode == "fan":
            self._set_status("Can't set the temperature here", warn=True); return
        if self.temp > 16:
            self.temp -= 1
            self._refresh_display(); self._send()

    def _set_turbo(self, val):
        if not self.power:
            self._set_status("Switch it on first", warn=True); return
        if self.turbo == val: return
        self.turbo = val
        self._refresh_display(); self._send()

    def _set_swing(self, val):
        if not self.power:
            self._set_status("Switch it on first", warn=True); return
        if self.swing == val: return
        self.swing = val
        self._refresh_display(); self._send()

    def _set_led(self, val):
        if not self.power:
            self._set_status("Switch it on first", warn=True); return
        if self.led == val: return
        self.led = val
        self._refresh_display(); self._send()

    def _set_xfan(self, val):
        if not self.power:
            self._set_status("Switch it on first", warn=True); return
        if self.xfan == val: return
        self.xfan = val
        self._refresh_display(); self._send()

    # ── Invio IR ──────────────────────────────────────────────
    def _connect_if_needed(self):
        if self.device is None:
            self.device = connect_device()

    def _send(self):
        threading.Thread(target=self._send_thread, daemon=True).start()

    def _send_thread(self):
        desc = self._describe()
        self._set_status(f"invio {desc}...")
        try:
            self._connect_if_needed()
            code = generate(**self._current_state())
            try: self.device.send_button(code)
            except Exception: pass
            self._set_status(f"✓ {desc}")
        except Exception as e:
            self._set_status(f"✗ errore: {e}", warn=True)
            self.device = None

    def _describe(self):
        if not self.power: return "OFF"
        return (f"ON {self.mode.upper()} {self.temp}°C "
                f"{'TURBO' if self.turbo else 'AUTO'} "
                f"sw:{'on' if self.swing else 'off'} "
                f"led:{'on' if self.led else 'off'} "
                f"xf:{'on' if self.xfan else 'off'}")

    def _set_status(self, msg, warn=False):
        self.status.config(text=msg, fg="#ff8080" if warn else MUTED)


# ── Entry point ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Daikin Siesta remote")
    parser.add_argument("--send",   metavar="NAME", help="Invia un preset e termina")
    parser.add_argument("--list",   action="store_true", help="Elenca preset salvati")
    parser.add_argument("--delete", metavar="NAME", help="Elimina un preset")
    args = parser.parse_args()

    if args.send:
        send_preset(args.send)
    elif args.list:
        list_presets()
    elif args.delete:
        delete_preset(args.delete)
    else:
        root = tk.Tk()
        DaikinRemote(root)
        root.mainloop()


if __name__ == "__main__":
    main()
