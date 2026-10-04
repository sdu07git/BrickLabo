
from .i18n import tr,tf
import time,json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QFileDialog,QMessageBox
from .ui_common import async_task
from .backups import create_backup,queue_restore,cancel_restore,REQUEST,REPORT

class BackupDialog(QDialog):
 def __init__(self,parent):
  super().__init__(parent);self.db=parent.db;self.busy=False;self.buttons=[]
  self.setWindowTitle(tr('Sauvegardes et restauration'));self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint);self.resize(660,420)
  layout=QVBoxLayout(self)
  text=QLabel(tr('La sauvegarde contient les données de Donnees : catalogues, inventaires manuels, stock, étiquettes, historique, réglages, clés API, images et notices.\n\nLes caches, logs et temporaires sont exclus. Les fichiers enregistrés en dehors de Donnees ne sont pas copiés.\n\nCette sauvegarde contient vos clés API : gardez-la privée. Choisissez un dossier de sauvegarde en dehors de Donnees.'));text.setWordWrap(True);layout.addWidget(text)
  for name,action in [(tr('Créer une sauvegarde…'),self.save),(tr('Restaurer une sauvegarde…'),self.restore),(tr('Annuler la restauration prévue'),self.cancel)]:
   button=QPushButton(name);button.clicked.connect(action);self.buttons.append(button);layout.addWidget(button)
  self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status,1)
  button=QPushButton(tr('Fermer'));button.clicked.connect(self.reject);self.buttons.append(button);layout.addWidget(button);self.update_pending()
 def update_pending(self):
  pending=(self.db.path.parent/REQUEST).exists();self.buttons[2].setEnabled(pending and not self.busy)
  if pending:self.status.setText(tr('Une restauration est prévue au prochain démarrage. Fermez puis relancez BrickLabo pour l’appliquer.'))
 def run(self,work,message):
  if self.busy:return
  self.busy=True
  for button in self.buttons:button.setEnabled(False)
  def finished(result):
   self.busy=False
   for button in self.buttons:button.setEnabled(True)
   self.status.setText(message(result));self.update_pending()
  def failed(error):
   finished(None);self.status.setText(tr('Opération interrompue : ')+error)
  async_task(self,work,finished,failed,lambda value:self.status.setText(str(value)))
 def save(self):
  default=self.db.path.parent.parent/'Sauvegardes'/('BrickLabo_sauvegarde_'+time.strftime('%Y%m%d_%H%M%S')+'.zip')
  path,_=QFileDialog.getSaveFileName(self,tr('Enregistrer une sauvegarde privée'),str(default),tr('Sauvegarde BrickLabo (*.zip)'))
  if path:self.run(lambda progress:create_backup(self.db,path,progress),lambda result:tr('Sauvegarde vérifiée : ')+str(result))
 def restore(self):
  path,_=QFileDialog.getOpenFileName(self,tr('Restaurer une sauvegarde privée'),'',tr('Sauvegarde BrickLabo (*.zip)'))
  if not path:return
  text=tr('La sauvegarde remplacera Donnees au prochain démarrage. L’état actuel sera conservé dans un dossier Donnees_avant_restauration à côté du logiciel. Préparer cette restauration ?')
  if QMessageBox.question(self,tr('Restaurer les données'),text)==QMessageBox.StandardButton.Yes:self.run(lambda progress:queue_restore(self.db,path,progress),lambda result:tr('Restauration préparée. Fermez puis relancez BrickLabo.'))
 def cancel(self):self.run(lambda progress:cancel_restore(self.db),lambda result:tr('Restauration annulée. Les données actuelles sont conservées.'))
 def reject(self):
  if not self.busy:super().reject()
 def closeEvent(self,event):
  if self.busy:event.ignore()
  else:super().closeEvent(event)

def show_report(parent):
 path=parent.db.path.parent/REPORT
 if not path.exists():return
 try:report=json.loads(path.read_text(encoding='utf-8'))
 except Exception:return
 path.unlink(missing_ok=True)
 method=QMessageBox.information if report.get('success') else QMessageBox.warning
 method(parent,tr('Restauration des données'),report['message'])
