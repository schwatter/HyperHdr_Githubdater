# -*- coding: utf-8 -*-
from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
import os
import requests
import subprocess

# BeautifulSoup laden/prüfen
try:
    from bs4 import BeautifulSoup
except ImportError:
    os.system("opkg update && opkg install python-beautifulsoup4")
    from bs4 import BeautifulSoup

# --- Einstellungen ---
TOKEN = ""  # Dein GitHub Personal Access Token
BASE_URL = "https://github.com"
ACTIONS_URL = "https://github.com/awawa-dev/HyperHDR/actions"
ARTIFACT_NAME = "HyperHDR-24.0.0~bookworm~beta0-armhf.deb"

HEADERS = {
    "Authorization": "Bearer {}".format(TOKEN),
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

class HyperHdrUpdaterScreen(Screen):
    skin = """
    <screen name="HyperHdrUpdaterScreen" position="center,center" size="800,500" title="HyperHDR GitHub Updater">
        <widget name="status" position="10,10" size="780,30" font="Regular;20" halign="left" />
        <widget name="menu" position="10,50" size="780,380" itemHeight="35" scrollbarMode="showOnDemand" enableWrapAround="1" />

        <!-- Rot: Text oben (Höhe 25px), Farbstreifen darunter (Höhe 5px) -->
        <widget name="key_red" position="10,440" size="180,25" font="Regular;18" halign="center" foregroundColor="white" transparent="1" />
        <eLabel position="10,468" size="180,5" backgroundColor="red" />

        <!-- Grün: Text oben (Höhe 25px), Farbstreifen darunter (Höhe 5px) -->
        <widget name="key_green" position="200,440" size="180,25" font="Regular;18" halign="center" foregroundColor="white" transparent="1" />
        <eLabel position="200,468" size="180,5" backgroundColor="green" />

        <!-- Gelb: Text oben (Höhe 25px), Farbstreifen darunter (Höhe 5px) -->
        <widget name="key_yellow" position="390,440" size="220,25" font="Regular;18" halign="center" foregroundColor="white" transparent="1" />
        <eLabel position="390,468" size="220,5" backgroundColor="yellow" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        
        self["status"] = Label("Pruefe GitHub Actions auf verfuegbare .deb Pakete...")
        self["key_red"] = Label("Beenden")
        self["key_green"] = Label("Aktualisieren")
        self["key_yellow"] = Label("Backup Restore")
        
        self.list = []
        self["menu"] = MenuList(self.list)
        
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
            "ok": self.select_item,
            "green": self.fetch_runs,
            "yellow": self.confirm_restore,
            "red": self.close,
            "cancel": self.close,
            "up": self.go_up,
            "down": self.go_down,
            "pageUp": self.go_page_up,
            "pageDown": self.go_page_down
        }, -1)
        
        self.onLayoutFinish.append(self.fetch_runs)

    def go_up(self):
        self["menu"].up()

    def go_down(self):
        self["menu"].down()

    def go_page_up(self):
        self["menu"].pageUp()

    def go_page_down(self):
        self["menu"].pageDown()

    def fetch_runs(self):
        self["status"].setText("Scanne Webseiten-Seiten 1 & 2 wie im Browser...")
        self.list = []
        self["menu"].setList(self.list)
        
        try:
            # Abhängigkeiten (xz) sicherstellen
            if subprocess.call(["which", "xz"]) != 0:
                os.system("opkg update && opkg install xz")

            found_runs = []

            # Genau Seite 1 und Seite 2 der GitHub-Webseite parsen
            for page in (1, 2):
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

            # Gefundene Runs über die API auf das .deb Artifact abfragen
            for run in found_runs:
                run_id = run['id']
                
                run_info_url = "https://api.github.com/repos/awawa-dev/HyperHDR/actions/runs/{}".format(run_id)
                info_res = requests.get(run_info_url, headers=HEADERS, timeout=5)
                
                title = "Run #{}".format(run_id)
                created_date = ""
                
                if info_res.status_code == 200:
                    run_data = info_res.json()
                    title = "Run #{} - {}".format(run_data.get("run_number", run_id), run_data.get("display_title", "")[:30])
                    created_date = run_data.get("created_at", "").replace("T", " ")[:16]

                artifacts_url = "https://api.github.com/repos/awawa-dev/HyperHDR/actions/runs/{}/artifacts".format(run_id)
                art_res = requests.get(artifacts_url, headers=HEADERS, timeout=5)
                
                if art_res.status_code == 200:
                    artifacts = art_res.json().get("artifacts", [])
                    
                    matching_artifact = None
                    for art in artifacts:
                        if art.get("name") == ARTIFACT_NAME or ARTIFACT_NAME in art.get("name", ""):
                            matching_artifact = art
                            break
                    
                    if matching_artifact:
                        download_url = matching_artifact.get("archive_download_url")
                        display_name = "{} ({})".format(title, created_date)
                        self.list.append((display_name, download_url, run_id))

            if self.list:
                self["menu"].setList(self.list)
                self["status"].setText("{} aktuelle Versionen gefunden (OK zum Installieren):".format(len(self.list)))
            else:
                self["status"].setText("Keine passenden Artifacts auf den Web-Seiten 1 & 2 gefunden.")
                
        except Exception as e:
            self["status"].setText("Fehler beim Scannen: {}".format(str(e)))

    def select_item(self):
        selection = self["menu"].getCurrent()
        if selection and isinstance(selection, tuple):
            display_name, download_url, run_id = selection
            self.session.openWithCallback(
                lambda confirm: self.start_download_and_install(download_url) if confirm else None,
                MessageBox,
                "Moechtest du das Package aus Run ID {} wirklich herunterladen und installieren?".format(run_id),
                MessageBox.TYPE_YESNO
            )

    def start_download_and_install(self, download_url):
        self["status"].setText("Lade Artifact herunter...")
        
        try:
            dl_res = requests.get(download_url, headers=HEADERS, stream=True, timeout=30)
            if dl_res.status_code == 200:
                file_path = "/tmp/hyperhdr_update.deb"
                with open(file_path, "wb") as f:
                    for chunk in dl_res.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                self["status"].setText("Entpacke und installiere...")
                self.install_deb(file_path)
            else:
                self.session.open(MessageBox, "Download fehlgeschlagen. HTTP Status: {}".format(dl_res.status_code), MessageBox.TYPE_ERROR)
        except Exception as e:
            self.session.open(MessageBox, "Download-Fehler: {}".format(str(e)), MessageBox.TYPE_ERROR)

    def install_deb(self, deb_path):
        try:
            os.system("/etc/init.d/hyperhdr stop 2>/dev/null")
            os.system("killall -9 hyperhdr 2>/dev/null")

            os.chdir("/tmp")
            os.system("rm -f debian-binary control.tar.* data.tar.*")
            
            # Backup des aktuellen Ordners erstellen vor dem Überschreiben
            os.system("rm -rf /usr/share/hyperhdr_s && mkdir -p /usr/share/hyperhdr_s")
            os.system("cp -r /usr/share/hyperhdr/* /usr/share/hyperhdr_s/ 2>/dev/null")
            
            os.system("ar -x {}".format(deb_path))
            os.system("tar -xf data.tar.* -C /")

            self.session.openWithCallback(
                self.reboot_system,
                MessageBox,
                "Installation von HyperHDR abgeschlossen!\nSoll die Box jetzt neu gestartet werden?",
                MessageBox.TYPE_YESNO
            )
        except Exception as e:
            self.session.open(MessageBox, "Installationsfehler: {}".format(str(e)), MessageBox.TYPE_ERROR)

    def confirm_restore(self):
        backup_path = "/usr/share/hyperhdr_s"
        if not os.path.exists(backup_path) or not os.listdir(backup_path):
            self.session.open(MessageBox, "Kein wiederherstellbares Backup in '/usr/share/hyperhdr_s' gefunden!", MessageBox.TYPE_ERROR)
            return

        self.session.openWithCallback(
            self.execute_restore,
            MessageBox,
            "Moechtest du das vorherige Backup aus '/usr/share/hyperhdr_s' wirklich wiederherstellen?",
            MessageBox.TYPE_YESNO
        )

    def execute_restore(self, confirm):
        if confirm:
            try:
                self["status"].setText("Stelle Backup wieder her...")
                os.system("/etc/init.d/hyperhdr stop 2>/dev/null")
                os.system("killall -9 hyperhdr 2>/dev/null")
                
                # Restore durchführen
                os.system("rm -rf /usr/share/hyperhdr/*")
                os.system("cp -r /usr/share/hyperhdr_s/* /usr/share/hyperhdr/")

                self.session.openWithCallback(
                    self.reboot_system,
                    MessageBox,
                    "Backup erfolgreich wiederhergestellt!\nSoll die Box jetzt neu gestartet werden?",
                    MessageBox.TYPE_YESNO
                )
            except Exception as e:
                self.session.open(MessageBox, "Wiederherstellungsfehler: {}".format(str(e)), MessageBox.TYPE_ERROR)

    def reboot_system(self, answer):
        if answer:
            os.system("reboot")

def main(session, **kwargs):
    session.open(HyperHdrUpdaterScreen)

def Plugins(**kwargs):
    return [
        PluginDescriptor(
            name="HyperHDR Updater",
            description="Aktualisiert HyperHDR direkt aus GitHub Actions",
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon="plugin.png",
            fnc=main
        )
    ]