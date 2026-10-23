"""Scheduled verified backups and checkpoints before large user-data writes."""
from pathlib import Path
import re
import threading
import time
import uuid

from .i18n import tr

_locks={};_guard=threading.Lock()


def policy(db):
    defaults=dict(enabled=False,hours=24,retention=7,before_changes=True,destination=str(db.path.parent.parent/'Sauvegardes_automatiques'))
    value=db.setting('automatic_backups',{})
    if isinstance(value,dict):defaults.update(value)
    return defaults


def configure(db,value):
    if any(type(value.get(key)) is not bool for key in ('enabled','before_changes')) or type(value.get('hours')) is not int or not 1<=value['hours']<=720 or type(value.get('retention')) is not int or not 1<=value['retention']<=100:raise ValueError(tr('Réglages de sauvegarde invalides.'))
    destination=Path(value.get('destination','')).expanduser().resolve()
    if not str(value.get('destination','')).strip() or destination.is_relative_to(db.path.parent.resolve()):raise ValueError(tr('Choisir un dossier de sauvegarde en dehors de Donnees.'))
    db.set_setting('automatic_backups',dict(value,destination=str(destination)))


def run(db,reason='periodic',force=False,progress=lambda _:None):
    config=policy(db)
    if not force and (not config['enabled'] or reason!='periodic' and not config['before_changes']):return None
    key=str(db.path.resolve())
    with _guard:lock=_locks.setdefault(key,threading.RLock())
    with lock:
        status=db.setting('automatic_backup_status',{});now=time.time()
        interval=config['hours']*3600 if reason=='periodic' else 60
        if not force and now-float(status.get('time',0))<interval:return None
        identity=db.setting('automatic_backup_identity')
        if not identity:identity=uuid.uuid4().hex;db.set_setting('automatic_backup_identity',identity)
        folder=Path(config['destination']);path=folder/('BrickLabo_auto_'+identity+'_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]+'.zip')
        try:
            from .backups import create_backup
            create_backup(db,path,progress)
            db.set_setting('automatic_backup_status',dict(time=now,path=str(path),reason=reason,error=''))
            pattern=re.compile(r'BrickLabo_auto_'+re.escape(identity)+r'_\d{8}_\d{6}_[a-f0-9]{8}\.zip')
            owned=sorted((p for p in folder.iterdir() if p.is_file() and not p.is_symlink() and pattern.fullmatch(p.name)),key=lambda p:p.name,reverse=True)
            for old in owned[config['retention']:]:old.unlink()
            return path
        except Exception as error:
            db.set_setting('automatic_backup_status',dict(status,error=str(error),failed_at=now))
            raise


def checkpoint(db,reason='before_change',large=True):
    if large:return run(db,reason)
    return None


def install(parent):
    from PySide6.QtCore import QTimer
    from .ui_common import async_task
    timer=QTimer(parent);timer.setInterval(60000);busy=[False]
    def tick():
        if busy[0] or getattr(parent,'_closing',False) or not policy(parent.db)['enabled']:return
        busy[0]=True
        def finished(_):busy[0]=False
        def failed(error):
            busy[0]=False;parent.statusBar().showMessage(tr('Sauvegarde automatique interrompue : ')+str(error),30000)
        async_task(parent,lambda progress:run(parent.db,progress=progress),finished,failed)
    timer.timeout.connect(tick);timer.start();return timer


def settings_dialog(parent):
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QCheckBox,QSpinBox,QLineEdit,QPushButton,QFileDialog,QLabel,QDialogButtonBox
    from .windows import show_window
    from .collection_dialogs import safe
    from .ui_common import async_task
    dialog=QDialog(parent);dialog.setWindowTitle(tr('Sauvegardes automatiques'));dialog.resize(640,420);layout=QVBoxLayout(dialog);form=QFormLayout();layout.addLayout(form);db=parent.db;value=policy(db)
    enabled=QCheckBox(tr('Activer les sauvegardes automatiques'));enabled.setChecked(value['enabled']);form.addRow(enabled)
    hours=QSpinBox();hours.setRange(1,720);hours.setValue(value['hours']);form.addRow(tr('Intervalle en heures'),hours)
    retention=QSpinBox();retention.setRange(1,100);retention.setValue(value['retention']);form.addRow(tr('Nombre de sauvegardes à conserver'),retention)
    before=QCheckBox(tr('Sauvegarder avant les imports importants et le vidage du stock'));before.setChecked(value['before_changes']);form.addRow(before)
    folder=QLineEdit(value['destination']);form.addRow(tr('Dossier externe à Donnees'),folder)
    def browse():
        path=QFileDialog.getExistingDirectory(dialog,tr('Dossier des sauvegardes automatiques'),folder.text())
        if path:folder.setText(path)
    choose=QPushButton(tr('Choisir le dossier de sauvegarde…'));choose.clicked.connect(browse);layout.addWidget(choose)
    status=QLabel();status.setWordWrap(True);layout.addWidget(status)
    def refresh():
        saved=db.setting('automatic_backup_status',{});status.setText((tr('Dernière sauvegarde : ')+saved.get('path','—'))+('\n'+saved['error'] if saved.get('error') else ''))
    def save():
        def run():configure(db,dict(enabled=enabled.isChecked(),hours=hours.value(),retention=retention.value(),before_changes=before.isChecked(),destination=folder.text()));return True
        return safe(dialog,run)
    now=QPushButton(tr('Sauvegarder maintenant'));layout.addWidget(now)
    def execute():
        if not save():return
        now.setEnabled(False)
        def finished(result):now.setEnabled(True);refresh()
        async_task(dialog,lambda progress:run(db,force=True,progress=progress),finished,lambda error:(finished(None),status.setText(str(error))))
    now.clicked.connect(execute)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Close);layout.addWidget(buttons);buttons.accepted.connect(save);buttons.rejected.connect(dialog.reject);refresh();show_window(dialog,parent);return dialog
