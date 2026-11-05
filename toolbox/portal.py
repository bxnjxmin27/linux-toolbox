"""xdg-desktop-portal-Zugriff (Wayland-tauglich): Bildschirmfreigabe, Farbwähler, Bildschirmfoto."""
from __future__ import annotations

import os
import uuid

from jeepney import DBusAddress, MatchRule, message_bus, new_method_call
from jeepney.io.blocking import Proxy, open_dbus_connection

from .context import Cancelled, ToolError

BUS = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"


def _tok() -> str:
    return "tb" + uuid.uuid4().hex[:12]


class Portal:
    def __init__(self):
        self.conn = open_dbus_connection(bus="SESSION", enable_fds=True)
        self.sender = self.conn.unique_name[1:].replace(".", "_")

    def close(self):
        self.conn.close()

    def _request(self, iface: str, member: str, sig: str, body_fn, timeout=120):
        """Ruft eine Portal-Methode mit handle_token auf und wartet auf die Response."""
        token = _tok()
        req_path = f"/org/freedesktop/portal/desktop/request/{self.sender}/{token}"
        rule = MatchRule(type="signal", interface="org.freedesktop.portal.Request", member="Response", path=req_path)
        Proxy(message_bus, self.conn).AddMatch(rule)
        q: list = []
        self.conn.filter(rule, queue=q)
        addr = DBusAddress(PATH, bus_name=BUS, interface=iface)
        self.conn.send_and_get_reply(new_method_call(addr, member, sig, body_fn(token)), timeout=10)
        msg = self.conn.recv_until_filtered(q, timeout=timeout)
        code, results = msg.body
        if code != 0:
            raise Cancelled() if code == 1 else ToolError("Das Desktop-Portal hat die Anfrage abgelehnt.")
        return results

    # --- Bildschirmfreigabe -------------------------------------------
    def screencast(self, types: int = 3, audio_cursor=True):
        """Gibt (fd, node_id) zurück. types: 1 Monitor, 2 Fenster, 3 beides."""
        r = self._request("org.freedesktop.portal.ScreenCast", "CreateSession", "a{sv}",
                          lambda t: ([{"handle_token": ("s", t), "session_handle_token": ("s", _tok())}],))
        session = r["session_handle"][1]
        self._request("org.freedesktop.portal.ScreenCast", "SelectSources", "oa{sv}",
                      lambda t: (session, {"handle_token": ("s", t), "types": ("u", types),
                                           "cursor_mode": ("u", 2 if audio_cursor else 1), "multiple": ("b", False)}))
        r = self._request("org.freedesktop.portal.ScreenCast", "Start", "osa{sv}",
                          lambda t: (session, "", {"handle_token": ("s", t)}), timeout=300)
        streams = r["streams"][1]
        if not streams:
            raise ToolError("Keine Quelle gewählt.")
        node = streams[0][0]
        addr = DBusAddress(PATH, bus_name=BUS, interface="org.freedesktop.portal.ScreenCast")
        reply = self.conn.send_and_get_reply(new_method_call(addr, "OpenPipeWireRemote", "oa{sv}", (session, {})), timeout=10)
        fd = reply.body[0].to_raw_fd()
        return os.dup(fd), node

    # --- Dateiauswahl (natives GNOME/KDE-Fenster) ----------------------
    def file_chooser(self, title, filt="", multiple=False, directory=False, save_name=None):
        import re
        from urllib.parse import unquote
        opts = lambda t: {"handle_token": ("s", t), "multiple": ("b", multiple), "directory": ("b", directory)}  # noqa: E731

        def body(t):
            o = opts(t)
            m = re.match(r"^(.*?)\s*\((.*)\)$", filt or "")
            if m and not directory:
                pats = m.group(2).split()
                pats += [p.upper() for p in pats if p.startswith("*.")]
                o["filters"] = ("a(sa(us))", [(m.group(1), [(0, p) for p in pats]), ("Alle Dateien", [(0, "*")])])
            return ("", title, o)
        r = self._request("org.freedesktop.portal.FileChooser", "OpenFile", "ssa{sv}", body, timeout=3600)
        return [unquote(u.replace("file://", "")) for u in r["uris"][1]]

    # --- Farbwähler ---------------------------------------------------
    def pick_color(self):
        r = self._request("org.freedesktop.portal.Screenshot", "PickColor", "sa{sv}",
                          lambda t: ("", {"handle_token": ("s", t)}), timeout=300)
        c = r["color"][1]
        return tuple(round(max(0, min(1, v)) * 255) for v in c)

    # --- Bildschirmfoto -----------------------------------------------
    def screenshot(self, interactive=True) -> str:
        r = self._request("org.freedesktop.portal.Screenshot", "Screenshot", "sa{sv}",
                          lambda t: ("", {"handle_token": ("s", t), "interactive": ("b", interactive)}), timeout=300)
        uri = r["uri"][1]
        from urllib.parse import unquote
        return unquote(uri.replace("file://", ""))


def pick_color():
    p = Portal()
    try:
        return p.pick_color()
    finally:
        p.close()


def screenshot(interactive=True) -> str:
    p = Portal()
    try:
        return p.screenshot(interactive)
    finally:
        p.close()
