# -*- coding: utf-8 -*-
import os
import requests
import subprocess
import threading
from enigma import eTimer
from twisted.internet import reactor
from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

PLUGIN_PATH = os.path.dirname(__file__)

TOKEN_FILE = "/etc/enigma2/github_token.txt"

# Pfade zur Token-Datei (Prüft erst Enigma2 Config, dann Plugin-Ordner)
TOKEN_PATHS = [
    TOKEN_FILE,
    os.path.join(PLUGIN_PATH, "github_token.txt")
]

TOKEN_OK = "ok"
TOKEN_MISSING = "missing"   # Datei existiert nicht
TOKEN_EMPTY = "empty"       # Datei existiert, aber kein Token drin


def load_github_token():
    """
    Liest den GitHub Token ein.
    Rueckgabe: (status, token) mit status = TOKEN_OK / TOKEN_MISSING / TOKEN_EMPTY
    """
    file_found = False
    for path in TOKEN_PATHS:
        if os.path.isfile(path):
            file_found = True
            try:
                with open(path, "r") as f:
                    token = f.read().strip()
                if token:
                    return TOKEN_OK, token
            except Exception:
                pass
    if file_found:
        return TOKEN_EMPTY, ""
    return TOKEN_MISSING, ""


TOKEN_STATUS, TOKEN = load_github_token()

BASE_URL = "https://github.com"
ACTIONS_URL = "https://github.com/awawa-dev/HyperHDR/actions"
ARTIFACT_NAME = "HyperHDR-24.0.0~bookworm~beta0-armhf.deb"

HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

if TOKEN:
    HEADERS["Authorization"] = "Bearer {}".format(TOKEN)


class HyperHdrUpdaterScreen(Screen):
    skin = """
    <screen name="HyperHdrUpdaterScreen" position="center,center" size="1000,500" title="HyperHDR GitHub Updater">
        <widget name="status" position="10,10" size="980,30" font="Regular;20" halign="left" />
        <widget name="menu" position="10,50" size="980,380" itemHeight="35" scrollbarMode="showOnDemand" enableWrapAround="1" />

        <widget name="key_red" position="10,440" size="235,25" font="Regular;18" halign="center" foregroundColor="white" transparent="1" />
        <eLabel position="10,468" size="235,5" backgroundColor="red" />

        <widget name="key_green" position="255,440" size="235,25" font="Regular;18" halign="center" foregroundColor="white" transparent="1" />
        <eLabel position="255,468" size="235,5" backgroundColor="green" />

        <widget name="key_yellow" position="500,440" size="235,25" font="Regular;18" halign="center" foregroundColor="white" transparent="1" />
        <eLabel position="500,468" size="235,5" backgroundColor="yellow" />

        <widget name="key_blue" position="745,440" size="235,25" font="Regular;18" halign="center" foregroundColor="white" transparent="1" />
        <eLabel position="745,468" size="235,5" backgroundColor="blue" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.is_closed = False

        self["status"] = Label("Checking dependencies...")
        self["key_red"] = Label("Exit")
        self["key_green"] = Label("Update")
        self["key_yellow"] = Label("Refresh")
        self["key_blue"] = Label("Restore")

        self.list = []
        self["menu"] = MenuList(self.list)

        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
            "ok": self.select_item,
            "green": self.select_item,
            "yellow": self.start_fetch_runs_thread,
            "blue": self.confirm_restore,
            "red": self.close,
            "cancel": self.close,
            "up": self.go_up,
            "down": self.go_down,
            "pageUp": self.go_page_up,
            "pageDown": self.go_page_down
        }, -1)

        self.onClose.append(self.on_screen_close)

        # Popups duerfen erst geoeffnet werden, wenn das Fenster wirklich angezeigt wird.
        # Deshalb die Token-Pruefung kurz verzoegert per Timer starten.
        self.start_timer = eTimer()
        self.start_timer.callback.append(self.check_token)
        self.onShown.append(self.start_once)

    def start_once(self):
        if self.start_once in self.onShown:
            self.onShown.remove(self.start_once)
        self.start_timer.start(200, True)

    def on_screen_close(self):
        self.is_closed = True

    # --- THREAD-SICHERE GUI-AUFRUFE ---
    # Hintergrund-Threads duerfen die GUI nicht direkt anfassen. Alles laeuft ueber
    # reactor.callFromThread in den Enigma2-Hauptthread und wird ignoriert,
    # wenn das Fenster schon geschlossen ist.

    def run_in_gui(self, func, *args):
        reactor.callFromThread(self._run_in_gui_safe, func, args)

    def _run_in_gui_safe(self, func, args):
        if self.is_closed:
            return
        try:
            func(*args)
        except Exception as e:
            print("[HyperHDRUpdater] GUI error: {}".format(e))

    def set_status(self, text):
        self.run_in_gui(lambda: self["status"].setText(text))

    def show_message(self, text, msg_type=MessageBox.TYPE_INFO):
        self.run_in_gui(lambda: self.session.open(MessageBox, text, msg_type))

    # --- TOKEN-PRUEFUNG ---

    def check_token(self):
        """Prueft beim Oeffnen, ob ein GitHub Token vorhanden ist."""
        global TOKEN, TOKEN_STATUS
        # Token bei jedem Oeffnen neu einlesen (kein Enigma2-Neustart noetig)
        TOKEN_STATUS, TOKEN = load_github_token()

        if TOKEN_STATUS == TOKEN_OK:
            HEADERS["Authorization"] = "Bearer {}".format(TOKEN)
            self.start_check_dependencies_thread()
            return

        HEADERS.pop("Authorization", None)

        if TOKEN_STATUS == TOKEN_MISSING:
            text = ("The GitHub token file does not exist!\n\n"
                    "Please create the file and enter your token:\n"
                    "{}\n\n"
                    "Without a token, artifacts cannot be downloaded.").format(TOKEN_FILE)
        else:
            text = ("The GitHub token file is empty!\n\n"
                    "No GitHub token found in:\n"
                    "{}\n\n"
                    "Without a token, artifacts cannot be downloaded.").format(TOKEN_FILE)

        self.session.openWithCallback(
            lambda *args: self.start_check_dependencies_thread(),
            MessageBox,
            text,
            MessageBox.TYPE_INFO
        )

    def go_up(self):
        self["menu"].up()

    def go_down(self):
        self["menu"].down()

    def go_page_up(self):
        self["menu"].pageUp()

    def go_page_down(self):
        self["menu"].pageDown()

    # --- THREAD-STEUERUNG & STREAMING ---

    def start_check_dependencies_thread(self):
        if self.is_closed:
            return
        t = threading.Thread(target=self.check_dependencies_worker)
        t.daemon = True
        t.start()

    def check_dependencies_worker(self):
        global BeautifulSoup
        if BeautifulSoup is None:
            self.set_status("Installing python-beautifulsoup4...")
            os.system("opkg update && opkg install python-beautifulsoup4")
            try:
                from bs4 import BeautifulSoup as bs
                BeautifulSoup = bs
            except ImportError:
                self.set_status("Error: python-beautifulsoup4 could not be installed.")
                return

        self.fetch_runs_worker()

    def start_fetch_runs_thread(self):
        t = threading.Thread(target=self.fetch_runs_worker)
        t.daemon = True
        t.start()

    def add_single_item_to_gui(self, item_tuple):
        """ Fügt ein einzelnes gefundenes Element sofort der GUI-Liste hinzu (Hauptthread) """
        self.list.append(item_tuple)
        self["menu"].setList(self.list)
        self["status"].setText("Found: {} versions (still searching...)".format(len(self.list)))

    def clear_list_gui(self):
        self.list = []
        self["menu"].setList(self.list)

    def fetch_runs_worker(self):
        self.set_status("Scanning GitHub Actions (loading entries one by one)...")
        self.run_in_gui(self.clear_list_gui)
        found_count = 0

        try:
            if subprocess.call(["which", "xz"]) != 0:
                os.system("opkg update && opkg install xz")

            found_runs = []

            # 1. Schritt: Alle Run-IDs schnell sammeln
            for page in (1, 2):
                if self.is_closed:
                    return
                page_url = "{}?page={}".format(ACTIONS_URL, page)
                res = requests.get(page_url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=10)

                if res.status_code != 200:
                    continue

                soup = BeautifulSoup(res.text, "html.parser")
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    if "/actions/runs/" in href and not href.endswith("/workflow"):
                        run_id = href.split("/")[-1]
                        if run_id not in [r['id'] for r in found_runs]:
                            found_runs.append({
                                'id': run_id,
                                'url': BASE_URL + href
                            })

            # 2. Schritt: Runs einzeln abfragen & sofort in die Liste pushen
            for run in found_runs:
                if self.is_closed:
                    return
                run_id = run['id']

                # Metadata holen
                run_info_url = "https://api.github.com/repos/awawa-dev/HyperHDR/actions/runs/{}".format(run_id)
                info_res = requests.get(run_info_url, headers=HEADERS, timeout=5)

                title = "Run #{}".format(run_id)
                created_date = ""

                if info_res.status_code == 200:
                    run_data = info_res.json()
                    title = "Run #{} - {}".format(run_data.get("run_number", run_id), (run_data.get("display_title") or "")[:30])
                    created_date = (run_data.get("created_at") or "").replace("T", " ")[:16]

                # Artifacts prüfen
                artifacts_url = "https://api.github.com/repos/awawa-dev/HyperHDR/actions/runs/{}/artifacts".format(run_id)
                art_res = requests.get(artifacts_url, headers=HEADERS, timeout=5)

                if art_res.status_code == 200:
                    artifacts = art_res.json().get("artifacts", [])

                    matching_artifact = None
                    for art in artifacts:
                        if art.get("name") == ARTIFACT_NAME or ARTIFACT_NAME in (art.get("name") or ""):
                            matching_artifact = art
                            break

                    if matching_artifact:
                        download_url = matching_artifact.get("archive_download_url")
                        display_name = "{} ({})".format(title, created_date)

                        # Eintragen, sobald gefunden:
                        item = (display_name, download_url, run_id)
                        found_count += 1
                        self.run_in_gui(self.add_single_item_to_gui, item)

            # Abschluss-Meldung
            if found_count:
                self.set_status("Search finished. {} versions available.".format(found_count))
            else:
                self.set_status("No matching artifacts found.")

        except Exception as e:
            self.set_status("Error while scanning: {}".format(str(e)))

    def select_item(self):
        selection = self["menu"].getCurrent()
        if selection and isinstance(selection, tuple):
            display_name, download_url, run_id = selection
            self.session.openWithCallback(
                lambda confirm: self.start_download_thread(download_url) if confirm else None,
                MessageBox,
                "Do you really want to download and install the package from run ID {}?".format(run_id),
                MessageBox.TYPE_YESNO
            )

    def start_download_thread(self, download_url):
        t = threading.Thread(target=self.download_and_install_worker, args=(download_url,))
        t.daemon = True
        t.start()

    def download_and_install_worker(self, download_url):
        self.set_status("Downloading artifact...")

        try:
            os.system("rm -f /tmp/hyperhdr_update.deb /tmp/debian-binary /tmp/control.tar.* /tmp/data.tar.*")

            dl_res = requests.get(download_url, headers=HEADERS, stream=True, timeout=30)
            if dl_res.status_code == 200:
                file_path = "/tmp/hyperhdr_update.deb"
                with open(file_path, "wb") as f:
                    for chunk in dl_res.iter_content(chunk_size=8192):
                        f.write(chunk)

                self.set_status("Extracting and installing...")
                self.install_deb(file_path)
            else:
                self.show_message("Download failed. HTTP status: {}".format(dl_res.status_code), MessageBox.TYPE_ERROR)
        except Exception as e:
            self.show_message("Download error: {}".format(str(e)), MessageBox.TYPE_ERROR)

    def install_deb(self, deb_path):
        try:
            os.system("/etc/init.d/hyperhdr stop 2>/dev/null")
            os.system("killall -9 hyperhdr 2>/dev/null")

            if os.path.exists("/usr/share/hyperhdr"):
                os.system("rm -rf /usr/share/hyperhdr_s && mkdir -p /usr/share/hyperhdr_s")
                os.system("cp -r /usr/share/hyperhdr/* /usr/share/hyperhdr_s/ 2>/dev/null")

            os.chdir("/tmp")
            os.system("ar -x {}".format(deb_path))
            os.system("tar -xf data.tar.* -C /")

            os.system("rm -f /tmp/hyperhdr_update.deb /tmp/debian-binary /tmp/control.tar.* /tmp/data.tar.*")

            self.restart_service("HyperHDR was updated and restarted successfully!")
        except Exception as e:
            self.show_message("Installation error: {}".format(str(e)), MessageBox.TYPE_ERROR)

    def confirm_restore(self):
        backup_path = "/usr/share/hyperhdr_s"
        if not os.path.exists(backup_path) or not os.listdir(backup_path):
            self.session.open(MessageBox, "No backup found in '/usr/share/hyperhdr_s' to restore!", MessageBox.TYPE_ERROR)
            return

        self.session.openWithCallback(
            self.execute_restore_thread,
            MessageBox,
            "Do you really want to restore the previous backup from '/usr/share/hyperhdr_s'?",
            MessageBox.TYPE_YESNO
        )

    def execute_restore_thread(self, confirm):
        if confirm:
            t = threading.Thread(target=self.execute_restore_worker)
            t.daemon = True
            t.start()

    def execute_restore_worker(self):
        try:
            self.set_status("Restoring backup...")
            os.system("/etc/init.d/hyperhdr stop 2>/dev/null")
            os.system("killall -9 hyperhdr 2>/dev/null")

            os.system("rm -rf /usr/share/hyperhdr/*")
            os.system("cp -r /usr/share/hyperhdr_s/* /usr/share/hyperhdr/")

            self.restart_service("Backup restored and HyperHDR restarted successfully!")
        except Exception as e:
            self.show_message("Restore error: {}".format(str(e)), MessageBox.TYPE_ERROR)

    def restart_service(self, message):
        os.system("/etc/init.d/hyperhdr start")
        self.set_status("HyperHDR is running again.")
        self.show_message(message, MessageBox.TYPE_INFO)


def main(session, **kwargs):
    session.open(HyperHdrUpdaterScreen)


def Plugins(**kwargs):
    return [
        PluginDescriptor(
            name="HyperHDR Updater",
            description="Updates HyperHDR directly from GitHub Actions",
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon="plugin.png",
            fnc=main
        )
    ]