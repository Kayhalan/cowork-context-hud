#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Kayhalan
# Licensed under the PolyForm Noncommercial License 1.0.0, see the LICENSE file.
"""
context_hud.py - floating HUD that shows how full the context window of your
Claude Cowork conversations is (Claude Desktop), per conversation and per model.

Source: the local cache of the Cowork interface (Claude Desktop's IndexedDB),
read-only. No network access, no external dependency (Python 3.8+ with tkinter).
Windows: tested. macOS: experimental, not tested.

    python  context_hud.py          HUD (Windows: pythonw, no console window)
    python  context_hud.py --once   table in the terminal
    python  context_hud.py --debug  diagnostics of the sources read

In the HUD:
    drag                move
    double-click        show / hide all conversations
    click on a row      pin that conversation (when the list is shown)
    Ctrl + wheel        size            Shift + wheel   opacity
    Alt + wheel         width (Option + wheel on macOS)
    right click         menu: auto mode, size, width, opacity, alert threshold,
                        sound, always on top, language, quit
                        (macOS: Ctrl + click)

Measure: tokens of the last turn of the main thread (input + cache_creation +
cache_read + output) compared with the official window of the selected model
(contextWindow returned by Cowork, otherwise an internal table). The red mark on
the bar is the auto-compaction threshold observed in your own sessions.

Limit: the app writes this cache when it (re)loads a conversation (opening,
end of a turn). The age of the data is shown in the HUD.
"""
import argparse
import json
import os
import re
import struct
import sys
import threading
import time
import traceback
from pathlib import Path

__version__ = "0.1.0"

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
ALT = "Option" if IS_MAC else "Alt"          # name of the modifier used for the width wheel
# Rough allowance for the macOS menu bar and Dock (estimates, not measured on a Mac).
MAC_MENUBAR, MAC_DOCK = 28, 80

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "context_hud_state.json"
LOG_FILE = HERE / "context_hud.log"
LOCK_FILE = HERE / "context_hud.lock"

USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens",
              "cache_read_input_tokens", "output_tokens")

# Known windows (tokens). The contextWindow read from Cowork takes priority.
MODEL_WINDOWS = (
    ("haiku", 200_000),
    ("fable", 1_000_000), ("mythos", 1_000_000),
    ("opus-5", 1_000_000), ("sonnet-5", 1_000_000),
    ("opus-4-8", 1_000_000), ("opus-4-7", 1_000_000),
    ("opus-4-6", 1_000_000), ("sonnet-4-6", 1_000_000),
)
DEFAULT_WINDOW = 200_000

# --------------------------------------------------------------------------
# Interface text: English by default, French as an option (--lang fr or the HUD menu)
# --------------------------------------------------------------------------
LANGUAGES = (("en", "English"), ("fr", "Français"))
STRINGS = {
    "en": {
        "unit_day": "d",
        "tbl_title": "Cowork - context per conversation",
        "col_win": "%win", "col_cmp": "%cmp", "col_tokens": "tokens", "col_compact": "compact",
        "col_model": "model", "col_data": "data", "col_title": "title",
        "not_cached": "not cached",
        "no_rows": "No Cowork conversation in cache. Folders read:",
        "no_dirs": "(no Claude Desktop data folder found: try --debug, or --data-dir PATH)",
        "quota_prefix": "Quota: ",
        "q_session": "session", "q_week": "week",
        "q_item": "{label} {pct:.0f} % ({age} ago)",
        "legend_1": "> active conversation (auto)   * running",
        "legend_2": "%win = share of the model's window, %cmp = share of the auto-compaction "
                    "threshold observed for this model (of the window if none)",
        "dbg_files": "Files decoded:", "dbg_folders": "Folders:", "dbg_learned": "Learned:",
        "ignored": "ignored ({n})",
        "already_running": "A HUD is already running.",
        "no_lock": "Could not write next to the script (read-only folder?): settings will not "
                   "be saved and a second HUD will not be detected.",
        "m_auto": "Auto mode (active conversation)",
        "m_all": "Show all conversations",
        "m_size": "Size", "m_width": "Width", "m_opacity": "Opacity",
        "m_fine_ctrl": "Ctrl + wheel: fine adjustment",
        "m_fine_alt": "{alt} + wheel: fine adjustment",
        "m_fine_shift": "Shift + wheel: fine adjustment",
        "m_warn": "Alert threshold",
        "m_warn_item": "{v} % of the compaction threshold",
        "m_sound": "Alert sound",
        "m_top": "Always on top",
        "m_lang": "Language",
        "m_reset": "Reset appearance",
        "m_quit": "Quit",
        "w_narrow": "Narrow", "w_normal": "Normal", "w_wide": "Wide", "w_xwide": "Extra wide",
        "t_size": "Size {v:.0f} %",
        "t_width": "Width {v} px",
        "t_opacity": "Opacity {v:.0f} %",
        "h_loading": "Reading the Cowork cache...",
        "h_none": "No Cowork conversation",
        "h_open": "Open a Cowork conversation in Claude Desktop",
        "h_compact": "compact ≈ {v}",
        "h_left": " ({v} left)",
        "h_reached": " (reached)",
        "h_notcached": "not cached yet: open it once",
        "h_noturn": "no turn measured",
        "f_pinned": "● pinned", "f_auto": "AUTO", "f_running": "running",
        "f_data": "data: {age}",
        "f_lastturn": "last turn: {m}",
        "f_error": "error: {e}",
    },
    "fr": {
        "unit_day": "j",
        "tbl_title": "Cowork - contexte par conversation",
        "col_win": "%fen", "col_cmp": "%cmp", "col_tokens": "tokens", "col_compact": "compact",
        "col_model": "modèle", "col_data": "données", "col_title": "titre",
        "not_cached": "pas en cache",
        "no_rows": "Aucune conversation Cowork en cache. Dossiers lus :",
        "no_dirs": "(aucun dossier de données de Claude Desktop trouvé : essayez --debug, "
                   "ou --data-dir CHEMIN)",
        "quota_prefix": "Quota : ",
        "q_session": "session", "q_week": "semaine",
        "q_item": "{label} {pct:.0f} % (il y a {age})",
        "legend_1": "> conversation active (auto)   * en cours d'exécution",
        "legend_2": "%fen = part de la fenêtre du modèle, %cmp = part du seuil d'auto-compactage "
                    "observé pour ce modèle (sinon de la fenêtre)",
        "dbg_files": "Fichiers décodés :", "dbg_folders": "Dossiers :", "dbg_learned": "Appris :",
        "ignored": "ignoré ({n})",
        "already_running": "Un HUD est déjà lancé.",
        "no_lock": "Impossible d'écrire à côté du script (dossier en lecture seule ?) : les "
                   "réglages ne seront pas enregistrés et un second HUD ne sera pas détecté.",
        "m_auto": "Mode auto (conversation active)",
        "m_all": "Afficher toutes les conversations",
        "m_size": "Taille", "m_width": "Largeur", "m_opacity": "Opacité",
        "m_fine_ctrl": "Ctrl + molette : réglage fin",
        "m_fine_alt": "{alt} + molette : réglage fin",
        "m_fine_shift": "Maj + molette : réglage fin",
        "m_warn": "Seuil d'alerte",
        "m_warn_item": "{v} % du seuil de compactage",
        "m_sound": "Son d'alerte",
        "m_top": "Toujours au premier plan",
        "m_lang": "Langue",
        "m_reset": "Réinitialiser l'apparence",
        "m_quit": "Quitter",
        "w_narrow": "Étroite", "w_normal": "Normale", "w_wide": "Large", "w_xwide": "Très large",
        "t_size": "Taille {v:.0f} %",
        "t_width": "Largeur {v} px",
        "t_opacity": "Opacité {v:.0f} %",
        "h_loading": "Lecture du cache Cowork...",
        "h_none": "Aucune conversation Cowork",
        "h_open": "Ouvrez une conversation Cowork dans Claude Desktop",
        "h_compact": "compact ≈ {v}",
        "h_left": " (reste {v})",
        "h_reached": " (atteint)",
        "h_notcached": "pas encore en cache : ouvrez-la une fois",
        "h_noturn": "aucun tour mesuré",
        "f_pinned": "● épinglée", "f_auto": "AUTO", "f_running": "en cours",
        "f_data": "données : {age}",
        "f_lastturn": "dernier tour : {m}",
        "f_error": "erreur : {e}",
    },
}
LANG = "en"


def set_lang(code):
    global LANG
    LANG = code if code in STRINGS else "en"


def tr(key, **kw):
    text = STRINGS[LANG].get(key) or STRINGS["en"][key]
    return text.format(**kw) if kw else text


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def log_error(msg):
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 200_000:
            LOG_FILE.unlink()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def _int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def norm_model(m):
    m = str(m or "").lower().replace("[1m]", "").strip()
    return re.sub(r"-\d{8}$", "", m)


def table_window(model):
    m = norm_model(model)
    for key, w in MODEL_WINDOWS:
        if key in m:
            return w
    return DEFAULT_WINDOW


def pretty_model(m):
    parts = norm_model(m).replace("claude-", "").split("-")
    if not parts or not parts[0]:
        return "?"
    ver = ".".join(p for p in parts[1:] if p.isdigit())
    return f"{parts[0].capitalize()} {ver}".strip()


def fk(n):
    if n is None:
        return "?"
    if n >= 1_000_000:
        return f"{n / 1e6:.2f}".rstrip("0").rstrip(".") + " M"
    if n >= 1000:
        return f"{n / 1000:.0f} k"
    return str(int(n))


def ago(seconds):
    if seconds is None or seconds < 0:
        return "?"
    if seconds < 90:
        return f"{int(seconds)} s"
    if seconds < 5400:
        return f"{int(seconds // 60)} min"
    if seconds < 172800:
        return f"{int(seconds // 3600)} h"
    return f"{int(seconds // 86400)} {tr('unit_day')}"


# --------------------------------------------------------------------------
# Decoding: raw Snappy + V8 serialization (format of the IndexedDB values)
# --------------------------------------------------------------------------
def snappy_raw(buf, pos=0):
    def varint(p):
        r = s = 0
        while True:
            b = buf[p]
            p += 1
            r |= (b & 0x7F) << s
            s += 7
            if b < 0x80:
                return r, p
    n, p = varint(pos)
    out = bytearray()
    end = len(buf)
    while p < end and len(out) < n:
        t = buf[p]
        p += 1
        kind = t & 3
        if kind == 0:
            ln = t >> 2
            if ln >= 60:
                nb = ln - 59
                ln = int.from_bytes(buf[p:p + nb], "little")
                p += nb
            ln += 1
            out += buf[p:p + ln]
            p += ln
            continue
        if kind == 1:
            ln = ((t >> 2) & 7) + 4
            off = ((t >> 5) << 8) | buf[p]
            p += 1
        elif kind == 2:
            ln = (t >> 2) + 1
            off = int.from_bytes(buf[p:p + 2], "little")
            p += 2
        else:
            ln = (t >> 2) + 1
            off = int.from_bytes(buf[p:p + 4], "little")
            p += 4
        if off <= 0 or off > len(out):
            raise ValueError("snappy: invalid offset")
        start = len(out) - off
        if off >= ln:
            out += out[start:start + ln]
        else:
            for i in range(ln):
                out.append(out[start + i])
    if len(out) != n:
        raise ValueError("snappy: unexpected size")
    return bytes(out)


class V8Reader:
    """Subset of the V8 ValueSerializer format that is needed here."""

    def __init__(self, data):
        self.b = data
        self.p = 0
        self.objs = []

    def u8(self):
        v = self.b[self.p]
        self.p += 1
        return v

    def var(self):
        r = s = 0
        while True:
            c = self.b[self.p]
            self.p += 1
            r |= (c & 0x7F) << s
            s += 7
            if c < 0x80:
                return r

    def raw(self, n):
        v = self.b[self.p:self.p + n]
        if len(v) != n:
            raise ValueError("v8: end of data")
        self.p += n
        return v

    def peek(self):
        return self.b[self.p]

    def value(self):
        while True:
            t = self.u8()
            if t == 0x00:            # padding
                continue
            if t == 0xFF:            # version
                self.var()
                continue
            if t == 0xFE:            # Blink trailer (offset + size)
                self.p += 12
                continue
            if t == 0x3F:            # verify object count
                self.var()
                continue
            break
        c = chr(t)
        if c == '"':
            return self.raw(self.var()).decode("latin-1")
        if c == "c":
            return self.raw(self.var()).decode("utf-16-le", "replace")
        if c == "S":
            return self.raw(self.var()).decode("utf-8", "replace")
        if c == "I":
            v = self.var()
            return (v >> 1) ^ -(v & 1)
        if c == "U":
            return self.var()
        if c == "N":
            return struct.unpack("<d", self.raw(8))[0]
        if c == "D":
            v = struct.unpack("<d", self.raw(8))[0]
            self.objs.append(v)
            return v
        if c == "T":
            return True
        if c == "F":
            return False
        if c in "0_-":
            return None
        if c == "Z":
            self.raw(self.var() >> 1)
            return 0
        if c == "^":
            i = self.var()
            return self.objs[i] if i < len(self.objs) else None
        if c == "o":
            o = {}
            self.objs.append(o)
            while self.peek() != ord("{"):
                k = self.value()
                o[str(k)] = self.value()
            self.p += 1
            self.var()
            return o
        if c == "A":
            n = self.var()
            a = []
            self.objs.append(a)
            for _ in range(n):
                a.append(self.value())
            while self.peek() != ord("$"):
                self.value()
                self.value()
            self.p += 1
            self.var()
            self.var()
            return a
        if c == "a":
            self.var()
            d = {}
            self.objs.append(d)
            while self.peek() != ord("@"):
                k = self.value()
                d[k] = self.value()
            self.p += 1
            self.var()
            self.var()
            return [d[k] for k in sorted((k for k in d if isinstance(k, int)))]
        if c == ";":
            m = {}
            self.objs.append(m)
            while self.peek() != ord(":"):
                k = self.value()
                m[str(k)] = self.value()
            self.p += 1
            self.var()
            return m
        if c == "'":
            st = []
            self.objs.append(st)
            while self.peek() != ord(","):
                st.append(self.value())
            self.p += 1
            self.var()
            return st
        if c in "yx":
            self.objs.append(c == "y")
            return c == "y"
        if c == "n":
            v = struct.unpack("<d", self.raw(8))[0]
            self.objs.append(v)
            return v
        if c == "s":
            v = self.value()
            self.objs.append(v)
            return v
        if c == "R":
            self.value()
            self.var()
            self.objs.append(None)
            return None
        if c == "B":
            self.raw(self.var())
            self.objs.append(None)
            return None
        if c == "V":
            self.u8()
            self.var()
            self.var()
            self.var()
            return None
        if c == "\\":               # Blink host object (e.g. a Blob reference)
            self.u8()
            self.var()
            return None
        raise ValueError(f"v8: unknown tag {t:#x} at {self.p - 1}")


def decode_idb_blob(raw):
    if raw[:3] == b"\xff\x11\x02":       # Snappy-compressed value
        raw = snappy_raw(raw, 3)
    return V8Reader(raw).value()


# --------------------------------------------------------------------------
# LevelDB (Claude Desktop's Local Storage): read-only, tables + write-ahead log
# --------------------------------------------------------------------------
def _uvar(b, p):
    r = s = 0
    while True:
        c = b[p]
        p += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, p


def _ldb_block_entries(blk):
    n = struct.unpack("<I", blk[-4:])[0]
    end = len(blk) - 4 - 4 * n
    p, key = 0, b""
    while p < end:
        shared, p = _uvar(blk, p)
        nonshared, p = _uvar(blk, p)
        vlen, p = _uvar(blk, p)
        key = key[:shared] + blk[p:p + nonshared]
        p += nonshared
        yield key, blk[p:p + vlen]
        p += vlen


def _ldb_block(data, off, size):
    raw, kind = data[off:off + size], data[off + size]
    if kind == 0:
        return raw
    if kind == 1:
        return snappy_raw(raw)
    raise ValueError("leveldb: unknown compression")


def _ldb_table(data):
    footer = data[-48:]
    _, p = _uvar(footer, 0)
    _, p = _uvar(footer, p)
    ioff, p = _uvar(footer, p)
    isize, p = _uvar(footer, p)
    for _, handle in _ldb_block_entries(_ldb_block(data, ioff, isize)):
        off, q = _uvar(handle, 0)
        size, q = _uvar(handle, q)
        for k, v in _ldb_block_entries(_ldb_block(data, off, size)):
            tag = struct.unpack("<Q", k[-8:])[0]
            yield k[:-8], tag >> 8, tag & 0xFF, v


def _ldb_log(data):
    p, frag = 0, b""
    while p + 7 <= len(data):
        left = 32768 - (p % 32768)
        if left < 7:
            p += left
            continue
        ln = struct.unpack("<H", data[p + 4:p + 6])[0]
        kind = data[p + 6]
        payload = data[p + 7:p + 7 + ln]
        p += 7 + ln
        if kind == 2:
            frag = payload
            continue
        if kind == 3:
            frag += payload
            continue
        if kind == 4:
            payload, frag = frag + payload, b""
        elif kind != 1:
            continue
        if len(payload) < 12:
            continue
        seq = struct.unpack("<Q", payload[:8])[0]
        count = struct.unpack("<I", payload[8:12])[0]
        q = 12
        for i in range(count):
            tag = payload[q]
            q += 1
            kl, q = _uvar(payload, q)
            k = payload[q:q + kl]
            q += kl
            v = None
            if tag == 1:
                vl, q = _uvar(payload, q)
                v = payload[q:q + vl]
                q += vl
            yield k, seq + i, tag, v


def leveldb_latest(dirpath, wanted=None):
    """{key: most recent value}; deleted keys are left out."""
    best = {}
    for f in list(dirpath.glob("*.ldb")) + list(dirpath.glob("*.log")):
        try:
            data = f.read_bytes()
            items = _ldb_log(data) if f.suffix == ".log" else _ldb_table(data)
            for k, seq, typ, v in items:
                if wanted and not wanted(k, v):
                    continue
                if k not in best or seq > best[k][0]:
                    best[k] = (seq, typ, v)
        except (OSError, ValueError, IndexError, struct.error):
            continue
    return {k: v for k, (seq, typ, v) in best.items() if typ == 1 and v is not None}


def _ls_text(v):
    if v[:1] == b"\x01":
        return v[1:].decode("latin-1")
    if v[:1] == b"\x00":
        return v[1:].decode("utf-16-le", "replace")
    return v.decode("utf-8", "replace")


# --------------------------------------------------------------------------
# Reading the Cowork cache
# --------------------------------------------------------------------------
def app_roots(data_dir=None):
    """Claude Desktop data folders to read. --data-dir replaces the autodetection."""
    roots = []
    if data_dir:
        roots.append(Path(data_dir).expanduser())
    elif IS_WIN:
        ad = os.environ.get("APPDATA")
        if ad:
            roots.append(Path(ad) / "Claude")
        lad = os.environ.get("LOCALAPPDATA")
        if lad:
            try:
                roots += sorted(Path(lad, "Packages").glob("Claude_*/LocalCache/Roaming/Claude"))
            except OSError:
                pass
    elif IS_MAC:
        roots.append(Path.home() / "Library" / "Application Support" / "Claude")
    out, seen = [], set()
    for r in roots:
        try:
            key = os.path.realpath(r)
            if r.is_dir() and key not in seen:
                seen.add(key)
                out.append(r)
        except OSError:
            pass
    return out


def blob_dirs(roots):
    return [d for d in (r / "IndexedDB" / "https_claude.ai_0.indexeddb.blob" for r in roots) if d.is_dir()]


# --------------------------------------------------------------------------
# Plan quota: for each gauge, keep the most recent measure among the three
# local sources, with its timestamp.
# --------------------------------------------------------------------------
def quota_from_local_storage(roots):
    out = []
    for r in roots:
        d = r / "Local Storage" / "leveldb"
        if not d.is_dir():
            continue
        vals = leveldb_latest(d, lambda k, v: k.startswith(b"_https://claude.ai")
                              and v is not None and b"utilization" in v and b"resetsAt" in v)
        for v in vals.values():
            try:
                o = json.loads(_ls_text(v))
            except ValueError:
                continue
            if not isinstance(o, dict):
                continue
            at, reset = _num(o.get("observedAt")), _num(o.get("resetsAt"))
            if at > 1e12:
                at /= 1000
            if not (at and reset) or "utilization" not in o:
                continue
            which = "session" if reset - at <= 5.5 * 3600 else "week"
            out.append((which, _num(o["utilization"]) * 100, at, reset))
    return out


def quota_from_history(roots):
    out = []
    for r in roots:
        try:
            with open(r / "plan-usage-history.json", encoding="utf-8") as f:
                samples = json.load(f).get("samples") or []
        except (OSError, ValueError, AttributeError):
            continue
        if samples and isinstance(samples[-1], dict):
            s = samples[-1]
            u, at = s.get("u") or {}, _num(s.get("t")) / 1000
            if isinstance(u, dict):
                if "fh" in u:
                    out.append(("session", _num(u["fh"]), at, 0.0))
                if "sd" in u:
                    out.append(("week", _num(u["sd"]), at, 0.0))
    return out


def quota_from_rate_event(rate):
    out = []
    if rate:
        info, at = rate
        for key, which in (("five_hour", "session"), ("seven_day", "week")):
            w = (info.get("unifiedWindows") or {}).get(key)
            if isinstance(w, dict) and "utilization" in w:
                out.append((which, _num(w["utilization"]) * 100, at, _num(w.get("resetsAt"))))
    return out


def merge_quota(samples, now):
    best = {}
    for which, pct, at, reset in samples:
        if which not in best or at > best[which]["at"]:
            best[which] = {"pct": pct, "at": at, "reset": reset}
    for q in best.values():
        if q["reset"] and q["reset"] < now:      # window reset since the measure
            q.update(pct=0.0, at=q["reset"])
    return best


def summarize_conversation(o):
    events = (o.get("tree") or {}).get("events") or []
    events = sorted((e for e in events if isinstance(e, dict)), key=lambda e: _num(e.get("seq")))
    tokens = model = None
    source = ""
    compacts, windows, rate = [], {}, None
    for e in events:
        p = e.get("payload")
        if not isinstance(p, dict):
            continue
        t = p.get("type")
        if t == "assistant" and p.get("parent_tool_use_id") is None:
            msg = p.get("message")
            if not isinstance(msg, dict):
                continue
            usage, mod = msg.get("usage"), msg.get("model")
            if isinstance(usage, dict) and isinstance(mod, str) and mod != "<synthetic>":
                n = sum(_int(usage.get(k)) for k in USAGE_KEYS)
                if n > 0:
                    tokens, model, source = n, mod, "tour"
        elif t == "system" and p.get("subtype") == "compact_boundary":
            md = p.get("compact_metadata") or p.get("compactMetadata") or {}
            if isinstance(md, dict):
                pre = _int(md.get("pre_tokens") or md.get("preTokens"))
                post = _int(md.get("post_tokens") or md.get("postTokens"))
                compacts.append((str(md.get("trigger") or ""), pre, post, model or ""))
                if post:
                    tokens, source = post, "compact"
        elif t == "result":
            mu = p.get("modelUsage")
            if isinstance(mu, dict):
                for k, v in mu.items():
                    if isinstance(v, dict) and _int(v.get("contextWindow")):
                        windows[norm_model(v.get("canonicalModel") or k)] = _int(v["contextWindow"])
        elif t == "rate_limit_event" and isinstance(p.get("rate_limit_info"), dict):
            rate = (p["rate_limit_info"], _num(e.get("serverCreatedAt")) / 1000)
    cid = str(o.get("conversationUuid") or "")
    return {
        "kind": "conv",
        "id": cid.split(":", 1)[-1],
        "written": _num(o.get("writtenAt")) / 1000,
        "fetched": _num(o.get("fetchedAt")) / 1000,
        "updated": _num(o.get("conversationUpdatedAt")) / 1000,
        "tokens": tokens, "model": model, "source": source,
        "compacts": compacts, "windows": windows, "rate": rate,
    }


def summarize_client_state(o):
    queries = ((o.get("clientState") or {}).get("queries")) or []
    for q in queries:
        key = q.get("queryKey") if isinstance(q, dict) else None
        if not (isinstance(key, list) and key and key[0] == "cowork-remote-sessions"):
            continue
        state = q.get("state") or {}
        data = state.get("data")
        if not isinstance(data, list):
            continue
        sessions = {}
        for s in data:
            if not isinstance(s, dict) or not s.get("sessionId"):
                continue
            sessions[str(s["sessionId"])] = {
                "title": str(s.get("title") or ""),
                "model": str(s.get("model") or ""),
                "activity": _num(s.get("lastActivityAt")) / 1000,
                "created": _num(s.get("createdAt")) / 1000,
                "running": bool(s.get("isRunning")),
                "archived": bool(s.get("isArchived")),
                "status": str(s.get("liveStatus") or s.get("rawSessionStatus") or ""),
            }
        return {"kind": "sessions", "at": _num(state.get("dataUpdatedAt")) / 1000, "sessions": sessions}
    return None


def summarize(obj):
    if not isinstance(obj, dict):
        return None
    if str(obj.get("product")) == "cowork" and isinstance(obj.get("tree"), dict):
        return summarize_conversation(obj)
    if isinstance(obj.get("clientState"), dict):
        return summarize_client_state(obj)
    return None


class Engine:
    def __init__(self, args, learned):
        self.args = args
        self.cache = {}            # path -> ((mtime, size), summary)
        self.dirs = []
        self.dirs_at = 0.0
        self.learned = learned     # {"windows": {model: w}, "compact": {model: tokens}}
        self.stats = {}
        self.roots = []
        self.ls_sig = None
        self.ls_quota = []

    def files(self):
        now = time.time()
        if now - self.dirs_at > 30 or not self.dirs:
            self.roots = app_roots(self.args.data_dir)
            self.dirs = blob_dirs(self.roots)
            self.dirs_at = now
        out = []
        for d in self.dirs:
            try:
                out += [p for p in d.rglob("*") if p.is_file()]
            except OSError:
                pass
        return out

    def read(self, path):
        try:
            st = path.stat()
        except OSError:
            return None
        sig = (st.st_mtime_ns, st.st_size)
        hit = self.cache.get(path)
        if hit and hit[0] == sig:
            return hit[1]
        summary = None
        if st.st_size <= 64 * 1024 * 1024:
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                t0 = time.perf_counter()
                summary = summarize(decode_idb_blob(raw))
                self.stats[str(path)] = (time.perf_counter() - t0) * 1000
            except (OSError, ValueError, IndexError, KeyError, struct.error, RecursionError) as exc:
                self.stats[str(path)] = tr("ignored", n=type(exc).__name__)
        self.cache[path] = (sig, summary)
        return summary

    def local_storage_quota(self):
        sig = []
        for r in self.roots:
            d = r / "Local Storage" / "leveldb"
            try:
                sig += [(f.name, f.stat().st_mtime_ns, f.stat().st_size)
                        for f in d.iterdir() if f.suffix in (".ldb", ".log")]
            except OSError:
                pass
        if sig != self.ls_sig:
            self.ls_sig = sig
            self.ls_quota = quota_from_local_storage(self.roots)
        return self.ls_quota

    def window_for(self, model):
        n = norm_model(model)
        if self.args.window:
            return self.args.window
        return self.learned["windows"].get(n) or table_window(n)

    def collect(self):
        now = time.time()
        files = self.files()
        live = set(files)
        for p in list(self.cache):
            if p not in live:
                del self.cache[p]
        convs, sessions, sessions_at, rate = {}, {}, 0.0, None
        for p in files:
            s = self.read(p)
            if not s:
                continue
            if s["kind"] == "conv":
                old = convs.get(s["id"])
                if old is None or s["written"] >= old["written"]:
                    convs[s["id"]] = s
                for m, w in s["windows"].items():
                    self.learned["windows"][m] = w
                if s["rate"] and (rate is None or s["rate"][1] > rate[1]):
                    rate = s["rate"]
            elif s["kind"] == "sessions" and s["at"] >= sessions_at:
                sessions, sessions_at = s["sessions"], s["at"]

        # observed auto-compaction threshold, per model (lowest automatic trigger)
        learned_compact = self.learned["compact"]
        for c in convs.values():
            for trig, pre, _post, model in c["compacts"]:
                m = norm_model(model)
                if trig == "auto" and pre > 0 and m:
                    best = learned_compact.get(m)
                    if best is None or pre < best:
                        learned_compact[m] = pre
        # a threshold that is contradicted (same-model conversation above it, never compacted) is not reliable
        peak = {}
        for c in convs.values():
            m = norm_model(c["model"])
            if c["tokens"] and c["source"] == "tour" and m:
                peak[m] = max(peak.get(m, 0), c["tokens"])

        cutoff = now - self.args.days * 86400
        rows = []
        for sid in set(sessions) | set(convs):
            meta = sessions.get(sid)
            conv = convs.get(sid)
            if meta and meta["archived"]:
                continue
            activity = max(meta["activity"] if meta else 0, conv["updated"] if conv else 0)
            fetched = conv["fetched"] if conv else 0
            if max(activity, fetched) < cutoff:
                continue
            model = (meta and meta["model"]) or (conv and conv["model"]) or ""
            tokens = conv["tokens"] if conv else None
            window = self.window_for(model) if model else DEFAULT_WINDOW
            if tokens and tokens > window:
                window = max(window, 1_000_000 if tokens <= 1_000_000 else tokens)
            m = norm_model(model)
            compact_at = learned_compact.get(m)
            if compact_at and peak.get(m, 0) > compact_at * 1.02:
                compact_at = None
            compact_at = self.args.compact_at or compact_at
            limit = compact_at or window
            rows.append({
                "id": sid,
                "title": (meta and meta["title"]) or sid,
                "model": model,
                "last_model": conv["model"] if conv else None,
                "tokens": tokens,
                "window": window,
                "pct": (tokens / window * 100) if tokens else 0.0,
                "compact_at": compact_at,
                "limit_pct": (tokens / limit * 100) if tokens else 0.0,
                "running": bool(meta and meta["running"]),
                "status": meta["status"] if meta else "",
                "activity": activity,
                "fetched": fetched,
                "data_age": (now - conv["written"]) if conv and conv["written"] else None,
                "cached": conv is not None,
                "source": conv["source"] if conv else "",
            })
        rows.sort(key=lambda r: (r["running"], max(r["activity"], r["fetched"])), reverse=True)
        quota = merge_quota(self.local_storage_quota() + quota_from_history(self.roots)
                            + quota_from_rate_event(rate), now)
        return {"rows": rows[: self.args.limit], "quota": quota, "at": now,
                "dirs": [str(d) for d in self.dirs], "nfiles": len(files)}


def quota_text(quota, now):
    parts = []
    for key, label in (("session", tr("q_session")), ("week", tr("q_week"))):
        q = quota.get(key)
        if q:
            parts.append(tr("q_item", label=label, pct=q["pct"], age=ago(now - q["at"])))
    return "  ·  ".join(parts)


def pick_active(rows):
    if not rows:
        return None
    running = [r for r in rows if r["running"]]
    pool = running or rows
    return max(pool, key=lambda r: max(r["activity"], r["fetched"]))


# --------------------------------------------------------------------------
# Persistent state
# --------------------------------------------------------------------------
def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict) and isinstance(st.get("learned", {}), dict):
            st.setdefault("learned", {})
            st["learned"].setdefault("windows", {})
            comp = st["learned"].setdefault("compact", {})
            for k in [k for k in comp if not str(k).startswith("claude-")]:
                del comp[k]        # old format (per window size)
            return st
    except (OSError, ValueError):
        pass
    return {"learned": {"windows": {}, "compact": {}}}


def save_state(st):
    try:
        tmp = STATE_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=1)
        os.replace(tmp, STATE_FILE)
    except OSError as exc:
        log_error(f"save_state: {exc}")


# --------------------------------------------------------------------------
# Text mode
# --------------------------------------------------------------------------
def print_table(snap, debug_stats=None):
    rows = snap["rows"]
    active = pick_active(rows)
    print(tr("tbl_title"))
    print("-" * 104)
    print(f"  {tr('col_win'):>5} {tr('col_cmp'):>5} {tr('col_tokens'):>16} {tr('col_compact'):>8} "
          f"{tr('col_model'):<11} {tr('col_data'):>8}  {tr('col_title')}")
    for r in rows:
        mark = ">" if r is active else " "
        run = "*" if r["running"] else " "
        if not r["cached"]:
            print(f"{mark}{run}{'':>5} {'':>5} {tr('not_cached'):>16} {'':>8} "
                  f"{pretty_model(r['model']):<11} {'':>8}  {r['title'][:44]}")
            continue
        tok = f"{fk(r['tokens'])} / {fk(r['window'])}"
        print(f"{mark}{run}{r['pct']:4.0f}% {r['limit_pct']:4.0f}% {tok:>16} {fk(r['compact_at']) if r['compact_at'] else '-':>8} "
              f"{pretty_model(r['model']):<11} {ago(r['data_age']):>8}  {r['title'][:44]}")
    if not rows:
        print(tr("no_rows"))
        for d in snap["dirs"] or [tr("no_dirs")]:
            print("  ", d)
    if snap["quota"]:
        print("\n" + tr("quota_prefix") + quota_text(snap["quota"], snap["at"]))
    print("\n" + tr("legend_1"))
    print(tr("legend_2"))
    if debug_stats is not None:
        print("\n" + tr("dbg_files"))
        for k, v in sorted(debug_stats.items()):
            print(f"  {v if isinstance(v, str) else f'{v:7.1f} ms'}  {k}")


# --------------------------------------------------------------------------
# tkinter HUD
# --------------------------------------------------------------------------
GREEN, ORANGE, RED = "#3fb950", "#f5a623", "#e5484d"
BG, FG, DIM, TRACK, BORDER = "#1b1b1f", "#ececf1", "#8b8b96", "#34343c", "#3a3a44"
W0, HEAD0, ROW0 = 344, 84, 22


def level_color(limit_pct, warn):
    if limit_pct >= warn:
        return RED
    if limit_pct >= warn - 20:
        return ORANGE
    return GREEN


class Hud:
    ZOOMS = (0.75, 0.9, 1.0, 1.15, 1.3, 1.5, 1.75, 2.0)
    ALPHAS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3)
    WIDTHS = (("w_narrow", 280), ("w_normal", 344), ("w_wide", 420), ("w_xwide", 520))

    def __init__(self, args, state):
        import tkinter as tk
        from tkinter import font as tkfont
        self.tk = tk
        self.tkfont = tkfont
        self.args = args
        self.state = state
        self.engine = Engine(args, state["learned"])
        self.snap = None
        self.lock = threading.Lock()
        self.pinned = state.get("pinned")
        self.expanded = bool(state.get("expanded", False))
        self.warn = float(args.warn if args.warn is not None else state.get("warn", 80.0))
        self.sound = bool(state.get("sound", True))
        self.topmost = bool(state.get("topmost", True))
        self.zoom = self._clamp(args.zoom or state.get("zoom", 1.0), 0.6, 2.5)
        self.alpha = self._clamp(args.alpha or state.get("alpha", 0.94), 0.3, 1.0)
        self.width = int(self._clamp(args.width or state.get("width", 344), 240, 720))
        self.armed = {}
        self.flash_until = 0.0
        self.toast = ("", 0.0)
        self.rows_hit = []
        self.press = (0, 0, 0, 0)
        self.moved = False
        self.error = ""
        self.pos = [0, 0]
        self.menu_stale = False

        if IS_WIN:
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        r = self.root = tk.Tk()
        r.withdraw()
        r.title("Cowork context HUD")
        self.s = max(1.0, r.winfo_fpixels("1i") / 96.0)
        if not args.framed:
            r.overrideredirect(True)
        r.attributes("-topmost", self.topmost)
        r.attributes("-alpha", self.alpha)
        r.configure(bg=BG)
        self.make_fonts()
        self.c = tk.Canvas(r, bg=BG, highlightthickness=0, bd=0)
        self.c.pack(fill="both", expand=True)
        self.build_menu()

        self.c.bind("<ButtonPress-1>", self.on_press)
        self.c.bind("<B1-Motion>", self.on_drag)
        self.c.bind("<ButtonRelease-1>", self.on_release)
        self.c.bind("<Double-Button-1>", lambda e: self.set_expanded(not self.expanded))
        # secondary click: Button-3 on Windows, Button-2 and Ctrl + click on macOS (Tk Aqua)
        for seq in (("<Button-2>", "<Control-Button-1>") if IS_MAC else ("<Button-3>",)):
            self.c.bind(seq, self.show_menu)
        self.c.bind("<Control-MouseWheel>", lambda e: self.set_zoom(self.zoom + (0.05 if e.delta > 0 else -0.05)))
        self.c.bind("<Shift-MouseWheel>", lambda e: self.set_alpha(self.alpha + (0.05 if e.delta > 0 else -0.05)))
        # Alt is not recognised as a modifier on macOS: Option (Mod2) is bound there instead
        for seq in (("<Option-MouseWheel>", "<Mod2-MouseWheel>") if IS_MAC else ("<Alt-MouseWheel>",)):
            try:
                self.c.bind(seq, lambda e: self.set_width(self.width + (20 if e.delta > 0 else -20)))
            except tk.TclError:
                pass
        r.protocol("WM_DELETE_WINDOW", self.quit)

        r.deiconify()
        r.update_idletasks()
        self.place(initial=True)
        threading.Thread(target=self.worker, daemon=True).start()
        self.ui_tick()

    @staticmethod
    def _clamp(v, lo, hi):
        try:
            return max(lo, min(hi, float(v)))
        except (TypeError, ValueError):
            return lo

    def ui_family(self):
        if IS_WIN:
            return "Segoe UI"
        try:                      # the system font of the platform
            return self.tkfont.nametofont("TkDefaultFont").actual("family")
        except Exception:
            return "Helvetica"

    def make_fonts(self):
        def px(n):
            return -max(7, int(round(n * self.s * self.zoom)))
        F = self.tkfont.Font
        fam = self.ui_family()
        self.f_title = F(family=fam, size=px(12), weight="bold")
        self.f_small = F(family=fam, size=px(11))
        self.f_tiny = F(family=fam, size=px(10))
        self.f_pct = F(family=fam, size=px(18), weight="bold")

    def build_menu(self):
        tk = self.tk
        m = self.menu = tk.Menu(self.root, tearoff=0)
        self.v_expanded = tk.BooleanVar(value=self.expanded)
        self.v_sound = tk.BooleanVar(value=self.sound)
        self.v_top = tk.BooleanVar(value=self.topmost)
        self.v_warn = tk.IntVar(value=int(self.warn))
        self.v_zoom = tk.DoubleVar(value=self.zoom)
        self.v_alpha = tk.DoubleVar(value=self.alpha)
        self.v_width = tk.IntVar(value=self.width)
        self.v_lang = tk.StringVar(value=LANG)
        m.add_command(label=tr("m_auto"), command=self.set_auto)
        m.add_checkbutton(label=tr("m_all"), variable=self.v_expanded,
                          command=lambda: self.set_expanded(self.v_expanded.get()))
        m.add_separator()
        sz = tk.Menu(m, tearoff=0)
        for z in self.ZOOMS:
            sz.add_radiobutton(label=f"{z * 100:.0f} %", value=z, variable=self.v_zoom,
                               command=lambda: self.set_zoom(self.v_zoom.get()))
        sz.add_separator()
        sz.add_command(label=tr("m_fine_ctrl"), state="disabled")
        m.add_cascade(label=tr("m_size"), menu=sz)
        wd = tk.Menu(m, tearoff=0)
        for name, w in self.WIDTHS:
            wd.add_radiobutton(label=tr(name), value=w, variable=self.v_width,
                               command=lambda: self.set_width(self.v_width.get()))
        wd.add_separator()
        wd.add_command(label=tr("m_fine_alt", alt=ALT), state="disabled")
        m.add_cascade(label=tr("m_width"), menu=wd)
        op = tk.Menu(m, tearoff=0)
        for a in self.ALPHAS:
            op.add_radiobutton(label=f"{a * 100:.0f} %", value=a, variable=self.v_alpha,
                               command=lambda: self.set_alpha(self.v_alpha.get()))
        op.add_separator()
        op.add_command(label=tr("m_fine_shift"), state="disabled")
        m.add_cascade(label=tr("m_opacity"), menu=op)
        m.add_separator()
        wa = tk.Menu(m, tearoff=0)
        for v in (60, 70, 80, 90):
            wa.add_radiobutton(label=tr("m_warn_item", v=v), value=v, variable=self.v_warn,
                               command=self.set_warn)
        m.add_cascade(label=tr("m_warn"), menu=wa)
        m.add_checkbutton(label=tr("m_sound"), variable=self.v_sound, command=self.set_sound)
        m.add_checkbutton(label=tr("m_top"), variable=self.v_top, command=self.set_top)
        lm = tk.Menu(m, tearoff=0)
        for code, name in LANGUAGES:
            lm.add_radiobutton(label=name, value=code, variable=self.v_lang,
                               command=lambda: self.set_language(self.v_lang.get()))
        m.add_cascade(label=tr("m_lang"), menu=lm)
        m.add_separator()
        m.add_command(label=tr("m_reset"), command=self.reset_look)
        m.add_command(label=tr("m_quit"), command=self.quit)

    def show_menu(self, e):
        if self.menu_stale:               # the language changed: rebuild with the new labels
            old = self.menu
            self.build_menu()
            old.destroy()
            self.menu_stale = False
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    # -- geometry ---------------------------------------------------------
    def S(self, v):
        return int(round(v * self.s * self.zoom))

    def size(self):
        n = len(self.snap["rows"]) if (self.expanded and self.snap) else 0
        h = HEAD0 + (n * ROW0 + 10 + (16 if self.snap and self.snap["quota"] else 0) if n else 0)
        return self.S(self.width), self.S(h)

    def work_area(self, x, y):
        """Usable area (left, top, right, bottom) of the screen containing (x, y)."""
        if IS_WIN:                        # excludes the taskbar
            try:
                import ctypes
                from ctypes import wintypes

                class MONITORINFO(ctypes.Structure):
                    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
                u = ctypes.windll.user32
                u.MonitorFromPoint.restype = wintypes.HMONITOR
                mon = u.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)   # the nearest one
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                if u.GetMonitorInfoW(mon, ctypes.byref(mi)):
                    rc = mi.rcWork
                    return rc.left, rc.top, rc.right, rc.bottom
            except Exception:
                pass
        r = self.root
        w, h = r.winfo_screenwidth(), r.winfo_screenheight()
        if IS_MAC:
            return 0, MAC_MENUBAR, w, h - MAC_DOCK
        return 0, 0, w, h

    def place(self, initial=False):
        w, h = self.size()
        r = self.root
        if initial:
            pos = None if self.args.framed else self.state.get("pos")
            if isinstance(pos, list) and len(pos) == 2:
                self.pos = [int(pos[0]), int(pos[1])]
            else:
                left, top, right, _ = self.work_area(r.winfo_screenwidth() // 2, 0)
                self.pos = [right - w - int(24 * self.s), top + int(48 * self.s)]
        # stay fully visible on the screen where the HUD is
        left, top, right, bottom = self.work_area(self.pos[0] + 20, self.pos[1] + 20)
        x = min(max(self.pos[0], left), max(left, right - w))
        y = min(max(self.pos[1], top), max(top, bottom - h))
        self.pos = [x, y]
        if self.args.framed and not initial:      # the window manager owns the position
            r.geometry(f"{w}x{h}")
        else:
            r.geometry(f"{w}x{h}+{x}+{y}")
        self.c.config(width=w, height=h)

    # -- actions ----------------------------------------------------------
    def persist(self):
        self.state.update(pinned=self.pinned, expanded=self.expanded, warn=self.warn,
                          sound=self.sound, topmost=self.topmost, zoom=self.zoom,
                          alpha=self.alpha, width=self.width)
        if not self.args.framed:
            self.state["pos"] = list(self.pos)
        save_state(self.state)

    def notify(self, text):
        self.toast = (text, time.time() + 1.2)

    def set_auto(self):
        self.pinned = None
        self.persist()
        self.render()

    def set_expanded(self, v):
        self.expanded = bool(v)
        self.v_expanded.set(self.expanded)
        self.place()
        self.persist()
        self.render()

    def set_zoom(self, z):
        self.zoom = round(self._clamp(z, 0.6, 2.5), 2)
        self.v_zoom.set(self.zoom)
        self.make_fonts()
        self.place()
        self.notify(tr("t_size", v=self.zoom * 100))
        self.persist()
        self.render()

    def set_width(self, w):
        self.width = int(self._clamp(w, 240, 720))
        self.v_width.set(self.width)
        self.place()
        self.notify(tr("t_width", v=self.width))
        self.persist()
        self.render()

    def set_alpha(self, a):
        self.alpha = round(self._clamp(a, 0.3, 1.0), 2)
        self.v_alpha.set(self.alpha)
        self.root.attributes("-alpha", self.alpha)
        self.notify(tr("t_opacity", v=self.alpha * 100))
        self.persist()

    def reset_look(self):
        self.alpha = 0.94
        self.root.attributes("-alpha", self.alpha)
        self.v_alpha.set(self.alpha)
        self.width = 344
        self.v_width.set(self.width)
        self.set_zoom(1.0)

    def set_language(self, code):
        set_lang(code)
        self.state["lang"] = LANG
        self.menu_stale = True
        self.persist()
        self.render()

    def set_warn(self):
        self.warn = float(self.v_warn.get())
        self.armed.clear()
        self.persist()

    def set_sound(self):
        self.sound = bool(self.v_sound.get())
        self.persist()

    def set_top(self):
        self.topmost = bool(self.v_top.get())
        self.root.attributes("-topmost", self.topmost)
        self.persist()

    def quit(self):
        self.persist()
        self.root.destroy()

    def on_press(self, e):
        self.press = (e.x_root, e.y_root, self.pos[0], self.pos[1])
        self.moved = False

    def on_drag(self, e):
        if self.args.framed:                      # the title bar moves the window
            return
        dx, dy = e.x_root - self.press[0], e.y_root - self.press[1]
        if abs(dx) + abs(dy) > 3:
            self.moved = True
        if self.moved:
            self.pos = [self.press[2] + dx, self.press[3] + dy]
            self.root.geometry(f"+{self.pos[0]}+{self.pos[1]}")

    def on_release(self, e):
        if IS_MAC and e.state & 0x4:              # Ctrl + click opens the menu, it is not a click on a row
            return
        if self.moved:
            self.persist()
            return
        for y0, y1, sid in self.rows_hit:
            if y0 <= e.y < y1:
                self.pinned = sid
                self.persist()
                self.render()
                return

    # -- data -------------------------------------------------------------
    def worker(self):
        while True:
            try:
                snap = self.engine.collect()
                with self.lock:
                    self.snap, self.error = snap, ""
                    self.state["learned"] = self.engine.learned
            except Exception as exc:
                log_error("collect: " + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
                with self.lock:
                    self.error = f"{type(exc).__name__}: {exc}"[:60]
            time.sleep(max(0.5, self.args.interval))

    def current(self, rows):
        if self.pinned:
            for r in rows:
                if r["id"] == self.pinned:
                    return r, True
        return pick_active(rows), False

    def play_alert(self):
        if IS_WIN:
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                return
            except Exception:
                pass
        self.root.bell()

    def check_alert(self, row):
        if not row or not row["tokens"]:
            return
        key, lp = row["id"], row["limit_pct"]
        if lp >= self.warn and self.armed.get(key, True):
            self.armed[key] = False
            self.flash_until = time.time() + 4
            if self.sound:
                self.play_alert()
        elif lp < self.warn - 10:
            self.armed[key] = True

    # -- drawing ----------------------------------------------------------
    def fit(self, font, text, width):
        if width <= 0:
            return ""
        if font.measure(text) <= width:
            return text
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if font.measure(text[:mid] + "...") <= width:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo] + "..."

    def bar(self, x0, y0, x1, y1, row, color):
        c, S = self.c, self.S
        c.create_rectangle(x0, y0, x1, y1, fill=TRACK, outline="")
        if row["tokens"]:
            fx = x0 + (x1 - x0) * min(row["pct"], 100) / 100
            c.create_rectangle(x0, y0, fx, y1, fill=color, outline="")
        if row["compact_at"] and row["compact_at"] < row["window"]:
            mx = x0 + (x1 - x0) * row["compact_at"] / row["window"]
            c.create_line(mx, y0 - S(2), mx, y1 + S(2), fill=RED, width=max(1, S(2)))
            wx = x0 + (x1 - x0) * row["compact_at"] * self.warn / 100 / row["window"]
            c.create_line(wx, y0, wx, y1, fill=DIM, width=1)

    def render(self):
        c, S = self.c, self.S
        c.delete("all")
        w, h = self.size()
        if (w, h) != (self.root.winfo_width(), self.root.winfo_height()):
            self.place()
        with self.lock:
            snap, err = self.snap, self.error
        now = time.time()
        flashing = now < self.flash_until and int(now * 3) % 2 == 0
        c.create_rectangle(0, 0, w - 1, h - 1, fill=BG, outline=RED if flashing else BORDER,
                           width=S(2) if flashing else 1)
        pad = S(10)
        if snap is None:
            c.create_text(pad, S(HEAD0) / 2, anchor="w", fill=DIM, font=self.f_small,
                          text=err or tr("h_loading"))
            return
        rows = snap["rows"]
        row, pinned = self.current(rows)
        self.check_alert(row)
        if row is None:
            c.create_text(pad, S(30), anchor="w", fill=FG, font=self.f_title, text=tr("h_none"))
            c.create_text(pad, S(52), anchor="w", fill=DIM, font=self.f_small,
                          text=err or tr("h_open"))
            return

        color = level_color(row["limit_pct"], self.warn)
        # line 1: state + title + model
        c.create_oval(pad, S(10), pad + S(8), S(18), fill=GREEN if row["running"] else DIM, outline="")
        model_txt = pretty_model(row["model"]) + " · " + fk(row["window"])
        mw = self.f_small.measure(model_txt)
        c.create_text(w - pad, S(14), anchor="e", fill=DIM, font=self.f_small, text=model_txt)
        tx = pad + S(14)
        c.create_text(tx, S(14), anchor="w", fill=FG, font=self.f_title,
                      text=self.fit(self.f_title, row["title"], w - tx - mw - pad - S(8)))
        # bar
        self.bar(pad, S(26), w - pad, S(36), row, color)
        # line 3: tokens + percentage
        if row["tokens"]:
            left = f"{fk(row['tokens'])} / {fk(row['window'])}"
            if row["compact_at"]:
                rest = row["compact_at"] - row["tokens"]
                left += "  ·  " + tr("h_compact", v=fk(row["compact_at"])) + (
                    tr("h_left", v=fk(rest)) if rest > 0 else tr("h_reached"))
            pct_txt = f"{row['pct']:.0f} %"
        else:
            left = tr("h_notcached") if not row["cached"] else tr("h_noturn")
            pct_txt = "-"
        c.create_text(w - pad, S(51), anchor="e", fill=color if row["tokens"] else DIM,
                      font=self.f_pct, text=pct_txt)
        pw = self.f_pct.measure(pct_txt)
        c.create_text(pad, S(51), anchor="w", fill=FG, font=self.f_small,
                      text=self.fit(self.f_small, left, w - 2 * pad - pw - S(8)))
        # line 4: footer
        foot = [tr("f_pinned") if pinned else tr("f_auto")]
        if row["running"]:
            foot.append(tr("f_running"))
        foot.append(tr("f_data", age=ago(row["data_age"])))
        if row["last_model"] and norm_model(row["last_model"]) != norm_model(row["model"]):
            foot.append(tr("f_lastturn", m=pretty_model(row["last_model"])))
        if err:
            foot.append(tr("f_error", e=err))
        c.create_text(pad, S(70), anchor="w", fill=DIM, font=self.f_tiny,
                      text=self.fit(self.f_tiny, "  ·  ".join(foot), w - 2 * pad))

        # expanded list
        self.rows_hit = []
        if self.expanded and rows:
            y = S(HEAD0)
            c.create_line(pad, y - S(3), w - pad, y - S(3), fill=BORDER)
            for r in rows:
                y0, y1 = y, y + S(ROW0)
                cy = (y0 + y1) / 2
                if r is row:
                    c.create_rectangle(S(3), y0 + 1, w - S(3), y1 - 1, fill="#26262d", outline="")
                rc = level_color(r["limit_pct"], self.warn)
                c.create_oval(pad, cy - S(3), pad + S(6), cy + S(3),
                              fill=GREEN if r["running"] else TRACK, outline="")
                bx0, bx1 = pad + S(12), pad + S(56)
                self.bar(bx0, cy - S(3), bx1, cy + S(3), r, rc)
                pct = f"{r['pct']:.0f} %" if r["tokens"] else "-"
                c.create_text(bx1 + S(38), cy, anchor="e", fill=rc if r["tokens"] else DIM,
                              font=self.f_small, text=pct)
                mt = pretty_model(r["model"])
                c.create_text(w - pad, cy, anchor="e", fill=DIM, font=self.f_tiny, text=mt)
                tx0 = bx1 + S(44)
                c.create_text(tx0, cy, anchor="w", fill=FG if r is row else DIM, font=self.f_small,
                              text=self.fit(self.f_small, r["title"],
                                            w - pad - tx0 - self.f_tiny.measure(mt) - S(8)))
                self.rows_hit.append((y0, y1, r["id"]))
                y = y1
            if snap["quota"]:
                c.create_text(pad, y + S(11), anchor="w", fill=DIM, font=self.f_tiny,
                              text=self.fit(self.f_tiny, tr("quota_prefix") + quota_text(snap["quota"], now),
                                            w - 2 * pad))

        # setting bubble (size / opacity / width)
        text, until = self.toast
        if now < until:
            tw = self.f_small.measure(text) + S(16)
            x0, y0 = (w - tw) / 2, S(28)
            c.create_rectangle(x0, y0, x0 + tw, y0 + S(22), fill="#000000", outline=BORDER)
            c.create_text(w / 2, y0 + S(11), fill=FG, font=self.f_small, text=text)

    def ui_tick(self):
        try:
            self.render()
        except Exception as exc:
            log_error("render: " + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        self.root.after(400, self.ui_tick)

    def run(self):
        self.root.mainloop()


# --------------------------------------------------------------------------
def warn(msg):
    """Message on stderr when there is one (pythonw has none)."""
    try:
        if sys.stderr:
            sys.stderr.write(msg + "\n")
    except (OSError, ValueError):
        pass


def single_instance():
    """Returns (handle, status). status: "ok", "running" (another HUD holds the lock)
    or "nolock" (the lock file cannot be created, e.g. read-only folder)."""
    try:
        fh = open(LOCK_FILE, "a+")
    except OSError as exc:
        log_error(f"lock file: {exc}")
        return None, "nolock"
    try:
        if IS_WIN:
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except ImportError:
        return fh, "ok"            # no locking available: run anyway
    except OSError:
        fh.close()
        return None, "running"
    return fh, "ok"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="print the table once and exit")
    ap.add_argument("--debug", action="store_true", help="table + diagnostics of the files read")
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between two reads (default 2)")
    ap.add_argument("--days", type=float, default=14.0, help="ignore conversations older than this many days")
    ap.add_argument("--limit", type=int, default=10, help="maximum number of conversations listed")
    ap.add_argument("--warn", type=float, default=None,
                    help="alert at X %% of the auto-compaction threshold (default: last chosen value, else 80)")
    ap.add_argument("--window", type=int, default=0, help="force the window size (tokens)")
    ap.add_argument("--compact-at", type=int, default=0, help="force the auto-compaction threshold (tokens)")
    ap.add_argument("--alpha", type=float, default=0, help="opacity 0.3-1.0 (default: last chosen value)")
    ap.add_argument("--zoom", type=float, default=0, help="size 0.6-2.5 (default: last chosen value)")
    ap.add_argument("--width", type=int, default=0, help="width in px at 100 %% (default: last chosen value)")
    ap.add_argument("--lang", choices=[c for c, _ in LANGUAGES],
                    help="interface language (default: the one chosen in the HUD menu, else en)")
    ap.add_argument("--data-dir", metavar="PATH",
                    help="Claude Desktop data folder to read (the one that holds IndexedDB and "
                         "Local Storage); replaces the autodetection")
    ap.add_argument("--framed", action="store_true",
                    help="normal window with a title bar instead of a borderless one "
                         "(fallback if the borderless window misbehaves)")
    ap.add_argument("--version", action="version", version="%(prog)s " + __version__)
    args = ap.parse_args()

    state = load_state()
    set_lang(args.lang or state.get("lang"))
    if args.once or args.debug:
        try:
            sys.stdout.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
        eng = Engine(args, state["learned"])
        snap = eng.collect()
        save_state(state)
        print_table(snap, eng.stats if args.debug else None)
        if args.debug:
            print("\n" + tr("dbg_folders"), *snap["dirs"], sep="\n  ")
            print(tr("dbg_learned"), json.dumps(state["learned"]))
        return

    lock, status = single_instance()      # keep the handle: the lock lasts as long as the process
    if status == "running":
        warn(tr("already_running"))
        return
    if status == "nolock":
        warn(tr("no_lock"))
    Hud(args, state).run()


if __name__ == "__main__":
    main()
