"""Modeless release viewer; updates run only after explicit user actions."""
import os
import threading

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, QVBoxLayout

from .i18n import tr, tf
from .paths import application_root
from .ui_common import async_task
from .version import VERSION
from .windows import application_owner
from .software_updates import RELEASES_PAGE, check_updates, prepare_update, previous_installation
from .update_installer import native_path, display_path


class SoftwareUpdateDialog(QDialog):
    def __init__(self, parent=None, root=None, auto_check=True):
        super().__init__(parent)
        self.root = native_path(root or application_root())
        self.release = None
        self.prepared = None
        self.running = False
        self.cancel_event = threading.Event()
        self.setWindowTitle(tr('Mise à jour du logiciel BrickLabo'))
        self.resize(850, 650)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)
        layout = QVBoxLayout(self)
        self.version_label = QLabel(tf('Version installée : v{0}', VERSION))
        layout.addWidget(self.version_label)
        description = QLabel(tr('La recherche consulte les releases publiques de BrickLabo sur GitHub. Seules les versions stables plus récentes sont proposées. Le dossier Donnees est conservé.'))
        description.setWordWrap(True)
        layout.addWidget(description)
        self.status = QLabel(tr('Prêt à rechercher une mise à jour.'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setPlaceholderText(tr('Les notes de la nouvelle version apparaîtront ici.'))
        layout.addWidget(self.notes, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        row = QHBoxLayout()
        self.check_button = QPushButton(tr('Rechercher une mise à jour'))
        self.check_button.clicked.connect(self.check)
        self.download_button = QPushButton(tr('Télécharger le ZIP complet'))
        self.download_button.clicked.connect(self.download)
        self.install_button = QPushButton(tr('Installer et redémarrer'))
        self.install_button.setProperty('primary', True)
        self.install_button.clicked.connect(self.install)
        for button in (self.check_button, self.download_button, self.install_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.install_help = QLabel(tr('Installer et redémarrer ferme BrickLabo, attend la fin des tâches et remplace uniquement le logiciel. Si le remplacement échoue, l’ancienne installation est rétablie.'))
        self.install_help.setWordWrap(True)
        layout.addWidget(self.install_help)
        self.previous = previous_installation(self.root)
        self.previous_button = QPushButton(tr('Ouvrir le dossier de l’ancienne installation'))
        self.previous_button.clicked.connect(self.open_previous)
        self.previous_button.setVisible(self.previous is not None)
        layout.addWidget(self.previous_button)
        bottom = QHBoxLayout()
        self.release_button = QPushButton(tr('Ouvrir les releases sur GitHub'))
        self.release_button.clicked.connect(self.open_release)
        bottom.addWidget(self.release_button)
        self.cancel_button = QPushButton(tr('Annuler le téléchargement'))
        self.cancel_button.clicked.connect(self.cancel)
        bottom.addWidget(self.cancel_button)
        close = QPushButton(tr('Fermer'))
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        layout.addLayout(bottom)
        self.automatic = os.name == 'nt' and (self.root / 'app' / 'python.exe').is_file() and (self.root / 'BrickLabo.exe').is_file()
        if not self.automatic:
            self.install_help.setText(tr('L’installation automatique est disponible dans la distribution Windows complète.'))
        self.controls()
        if auto_check:
            QTimer.singleShot(0, self.check)

    def controls(self):
        self.check_button.setEnabled(not self.running)
        self.download_button.setEnabled(not self.running and self.automatic and self.release is not None and self.release.installable and self.prepared is None)
        self.install_button.setEnabled(not self.running and self.automatic and self.prepared is not None)
        self.cancel_button.setEnabled(self.running)

    def check(self):
        if self.running:
            return
        if self.prepared is not None:
            self.prepared.discard()
            self.prepared = None
        self.release = None
        self.notes.clear()
        self.running = True
        self.cancel_event = threading.Event()
        event = self.cancel_event
        self.status.setText(tr('Recherche des releases sur GitHub…'))
        self.progress.setRange(0, 0)
        self.controls()
        async_task(self, lambda progress: check_updates(cancel=event), self.checked, self.failed)

    def checked(self, release):
        self.running = False
        self.release = release
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        if release is None:
            self.status.setText(tf('Aucune version stable plus récente que v{0}.', VERSION))
        else:
            self.notes.setPlainText(release.notes or tr('Aucune note publiée pour cette version.'))
            message = tf('Nouvelle version disponible : v{0}', release.version)
            if release.installable:
                message += ' · ' + tf('ZIP complet : {0} Mio', round(release.size / 1024**2))
            else:
                message += '\n' + release.problem
            self.status.setText(message)
        self.controls()

    def download(self):
        if self.running or not self.automatic or self.release is None or not self.release.installable:
            return
        self.running = True
        self.cancel_event = threading.Event()
        root, release, event = self.root, self.release, self.cancel_event
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.controls()
        async_task(self, lambda progress: prepare_update(root, release, progress, event),
                   self.downloaded, self.failed, self.show_progress)

    def show_progress(self, value):
        text, percent = value
        self.status.setText(text)
        self.progress.setValue(percent)

    def downloaded(self, prepared):
        self.running = False
        if self.cancel_event.is_set():
            prepared.discard()
            self.status.setText(tr('Téléchargement annulé. Aucun fichier du logiciel n’a été remplacé.'))
        else:
            self.prepared = prepared
            self.status.setText(tr('Mise à jour prête. Clique sur Installer et redémarrer.'))
            self.progress.setValue(100)
        self.controls()

    def failed(self, message):
        self.running = False
        self.status.setText(message)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.controls()

    def cancel(self):
        self.cancel_event.set()
        self.cancel_button.setEnabled(False)
        self.status.setText(tr('Annulation demandée…'))

    def install(self):
        if self.running or self.prepared is None or not self.automatic:
            return
        owner = application_owner(self.parent())
        if not hasattr(owner, 'request_software_update'):
            self.status.setText(tr('Ouvre cette fenêtre depuis la fenêtre principale de BrickLabo.'))
            return
        prepared = self.prepared
        # The main window must own the prepared plan before it closes children.
        self.prepared = None
        if not owner.request_software_update(prepared):
            self.prepared = prepared
            self.controls()

    def open_release(self):
        QDesktopServices.openUrl(QUrl(self.release.page if self.release else RELEASES_PAGE))

    def open_previous(self):
        if self.previous is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(display_path(self.previous)))

    def reject(self):
        self.cancel_event.set()
        if self.prepared is not None:
            self.prepared.discard()
            self.prepared = None
        super().reject()
