"""Shoonya phone bot - Kivy launcher / status screen (big buttons)."""
import json
import os

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView


GREEN = (0.16, 0.55, 0.22, 1)
ORANGE = (0.85, 0.52, 0.10, 1)
RED = (0.78, 0.22, 0.18, 1)
GRAY = (0.36, 0.40, 0.45, 1)
DARK = (0.09, 0.11, 0.15, 0.97)


def _where():
    d = os.environ.get("ANDROID_PRIVATE")
    if d and os.path.isdir(d):
        return d
    return os.path.dirname(os.path.abspath(__file__))


def read_status():
    try:
        with open(os.path.join(_where(), "bot_status.json")) as f:
            return json.load(f)
    except Exception:
        return {}


def open_browser(url):
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        PythonActivity.mActivity.startActivity(intent)
        return True
    except Exception:
        pass
    try:
        import webbrowser
        webbrowser.open(url)
        return True
    except Exception:
        return False


def copy_text(text):
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        ClipData = autoclass("android.content.ClipData")
        service = PythonActivity.mActivity.getSystemService("clipboard")
        service.setPrimaryClip(ClipData.newPlainText("url", text))
        return True
    except Exception:
        return False


def service_api():
    try:
        from android import service
        return service
    except Exception:
        return None


def start_service():
    try:
        api = service_api()
        if api is not None:
            api.start_service("myservice", args=[])
            return True, ""
    except Exception:
        pass
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Svc = autoclass("org.shoonya.shoonyabot.ServiceMyservice")
        Svc.start(PythonActivity.mActivity, "")
        return True, ""
    except Exception as e:
        return False, str(e)[:120]


def stop_service():
    try:
        api = service_api()
        if api is not None:
            api.stop_service("myservice")
            return True, ""
    except Exception:
        pass
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Svc = autoclass("org.shoonya.shoonyabot.ServiceMyservice")
        Svc.stop(PythonActivity.mActivity)
        return True, ""
    except Exception as e:
        return False, str(e)[:120]


def request_notifs():
    try:
        from android.permissions import request_permissions, Permission
        request_permissions([Permission.POST_NOTIFICATIONS])
    except Exception:
        pass


def big_button(text, bg, font_size="20sp"):
    return Button(
        text=text,
        size_hint_y=None,
        height=dp(84),
        font_size=font_size,
        bold=True,
        background_normal="",
        background_color=bg,
        color=(1, 1, 1, 1),
    )


class Card(BoxLayout):
    def __init__(self, bg=DARK, **kw):
        self.bg = bg
        super().__init__(**kw)
        self.bind(size=self._redraw, pos=self._redraw)

    def _redraw(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.bg)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)] * 4)


class Root(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=dp(14), spacing=dp(10), **kw)

        self.title = Label(
            text="SHOONYA BOT",
            font_size="30sp",
            bold=True,
            size_hint_y=None,
            height=dp(64),
            color=(1, 1, 1, 1),
        )

        self.card = Card(orientation="vertical", padding=dp(12), spacing=dp(6))
        self.state_lbl = Label(
            text="loading...",
            font_size="24sp",
            bold=True,
            size_hint_y=None,
            height=dp(44),
            color=(1, 1, 1, 1),
        )
        self.card_color = GRAY
        self.url_lbl = Label(
            text="no webhook URL yet",
            font_size="17sp",
            size_hint_y=None,
            height=dp(52),
            color=(0.6, 0.85, 1, 1),
            halign="center",
            valign="middle",
            markup=True,
        )
        self.url_lbl.bind(size=lambda *a: setattr(self.url_lbl, "text_size", (self.url_lbl.width, None)))
        self.log_lbl = Label(
            text="",
            font_size="13sp",
            halign="left",
            valign="top",
            text_size=(None, None),
            size_hint_y=None,
            height=dp(90),
            color=(0.85, 0.85, 0.9, 1),
        )
        self.log_lbl.bind(size=lambda *a: setattr(self.log_lbl, "text_size", (self.log_lbl.width, None)))
        self.card.add_widget(self.state_lbl)
        self.card.add_widget(self.url_lbl)
        self.card.add_widget(self.log_lbl)

        self.btn_open = big_button("OPEN DASHBOARD", (0.12, 0.36, 0.72, 1))
        self.btn_open.bind(on_press=lambda *a: self.open_dash())

        self.btn_copy = big_button("COPY WEBHOOK URL", (0.10, 0.30, 0.60, 1))
        self.btn_copy.bind(on_press=lambda *a: self.copy_url())

        self.btn_on = big_button("START BOT SERVICE", GREEN)
        self.btn_on.bind(on_press=lambda *a: self.on_start())

        self.btn_off = big_button("STOP BOT SERVICE", RED)
        self.btn_off.bind(on_press=lambda *a: self.on_stop())

        self.add_widget(self.title)
        self.add_widget(self.card)
        self.add_widget(self.btn_open)
        self.add_widget(self.btn_copy)
        self.add_widget(self.btn_on)
        self.add_widget(self.btn_off)

        Clock.schedule_interval(self.tick, 2.0)
        self.tick(0)

    def open_dash(self):
        if open_browser("http://127.0.0.1:5000"):
            self.flash("Dashboard open - login with your Shoonya password")
        else:
            self.flash("Could not open browser")

    def copy_url(self):
        st = read_status()
        url = st.get("tunnel_url", "")
        if url:
            full = "%s/webhook?token=%s" % (url, self._token())
            if copy_text(full):
                self.flash("Webhook URL copied")
            else:
                self.flash("Copy failed")
        else:
            self.flash("No tunnel yet - wait for URL")

    def _token(self):
        try:
            from bot import config as cfg
            return cfg.AUTH_TOKEN
        except Exception:
            return ""

    def flash(self, msg):
        self.state_lbl.text = msg
        Clock.schedule_once(lambda dt: self.tick(0), 2)

    def on_start(self):
        ok, msg = start_service()
        if ok:
            self.flash("Service starting...")
        else:
            self.flash("Start failed: %s" % msg)

    def on_stop(self):
        ok, msg = stop_service()
        if ok:
            self.flash("Service stopped")
        else:
            self.flash("Stop failed: %s" % msg)

    def tick(self, dt):
        st = read_status()
        err = st.get("tunnel_error", "") or st.get("service_error", "")
        if err:
            self.state_lbl.text = "PROBLEM - see detail below"
            self.card_color = RED
        elif st.get("running"):
            self.state_lbl.text = "RUNNING"
            self.card_color = GREEN if st.get("tunnel_url") else ORANGE
        else:
            self.state_lbl.text = "IDLE - tap START BOT SERVICE"
            self.card_color = GRAY
        self.card.bg = self.card_color
        self.card._redraw()

        url = st.get("tunnel_url", "")
        if url:
            self.url_lbl.text = "[b]WEBHOOK:[/b]\n%s" % url
        else:
            hint = ""
            if st.get("tunnel_starting"):
                hint = "tunnel starting..."
            elif st.get("flask") == "starting":
                hint = "server starting..."
            self.url_lbl.text = "no tunnel yet\n%s" % hint if hint else "no tunnel yet"

        log = []
        for k in ("service_error", "tunnel_error", "flask_error"):
            if st.get(k):
                log.append("%s: %s" % (k, st[k]))
        lg = st.get("tunnel_log", "")
        if lg:
            log.append("tunnel log:\n" + lg)
        self.log_lbl.text = "\n".join(log)[:1500]


class ShoonyaApp(App):
    def build(self):
        self.title = "Shoonya Bot"
        request_notifs()
        return Root()


if __name__ == "__main__":
    ShoonyaApp().run()