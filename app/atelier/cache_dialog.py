
from .i18n import tr,tf
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QDialogButtonBox,QTableWidget,QTableWidgetItem,QAbstractItemView,QSpinBox,QFormLayout
from .ui_common import async_task
from .disk_space import usage,locations,clean_temp,deduplicate_ldraw

def size_text(size):
 return f'{size/1073741824:.2f} '+tr('Gio') if size>=1073741824 else f'{size/1048576:.1f} '+tr('Mio')

class SpaceDialog(QDialog):
 def __init__(self,parent):
  super().__init__(parent);self.parent_app=parent;self.busy=False;self.closed=False;self.buttons=[]
  self.setWindowTitle(tr('Espace disque et caches'));self.resize(740,560);self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)
  layout=QVBoxLayout(self);info=QLabel(tr('Données personnelles : ')+str(parent.db.path.parent)+tr('\nLes miniatures sont réutilisées. Une limite disque de 0 conserve uniquement le cache en RAM.'));info.setWordWrap(True);layout.addWidget(info)
  form=QFormLayout();layout.addLayout(form);self.ram=QSpinBox();self.ram.setRange(0,512);self.ram.setSuffix(' Mio');self.ram.setValue(parent.db.setting('thumbnail_ram_mb',32));form.addRow(tr('Cache miniatures en RAM'),self.ram)
  self.disk=QSpinBox();self.disk.setRange(0,4096);self.disk.setSuffix(' Mio');self.disk.setValue(parent.db.setting('thumbnail_disk_mb',256));form.addRow(tr('Cache miniatures sur disque'),self.disk)
  apply=QPushButton(tr('Appliquer les limites'));apply.clicked.connect(self.apply_limits);layout.addWidget(apply);self.buttons.append(apply)
  self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels([tr('Dossier / contenu'),tr('Taille'),tr('Fichiers')]);self.table.horizontalHeader().setStretchLastSection(True);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.itemDoubleClicked.connect(self.open_folder);self.table.setToolTip(tr('Double-clic sur une ligne : ouvrir son dossier'));layout.addWidget(self.table,1)
  for label,func in [(tr('Actualiser les tailles'),self.refresh),(tr('Vider le cache des miniatures'),self.clear_cache),(tr('Nettoyer les temporaires de plus de 7 jours'),lambda:self.operate(lambda:clean_temp(parent.db))),(tr('Supprimer les copies LDraw identiques'),lambda:self.operate(lambda:deduplicate_ldraw(parent.db)))]:
   button=QPushButton(label);button.clicked.connect(func);self.buttons.append(button);layout.addWidget(button)
  text=QLabel(tr('Les temporaires récents, fichiers référencés, images importées, notices, stock et réglages sont conservés. LDraw : seules des copies au contenu identique sont supprimées, avec conservation de l’archive active. Aucun nettoyage du dossier Temp de Windows.'));text.setWordWrap(True);layout.addWidget(text)
  self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
  self.result_label=QLabel();self.result_label.setWordWrap(True);layout.addWidget(self.result_label)
  close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);close.rejected.connect(self.reject);close.button(QDialogButtonBox.StandardButton.Close).setText(tr('Fermer'));self.buttons.append(close.button(QDialogButtonBox.StandardButton.Close));layout.addWidget(close);self.refresh()
 def set_busy(self,value):
  self.busy=value
  for button in self.buttons:button.setEnabled(not value)
 def refresh(self):
  if self.busy:return
  self.set_busy(True);self.status.setText(tr('Calcul des tailles…'))
  def done(rows):
   if self.closed:return
   self.table.setRowCount(len(rows));folders=locations(self.parent_app.db)
   for r,(label,size,count) in enumerate(rows):
    for c,value in enumerate((label,size_text(size),str(count))):
     cell=QTableWidgetItem(value);cell.setData(Qt.ItemDataRole.UserRole,str(folders[label].resolve()));cell.setToolTip(tr('Double-clic : ')+cell.data(Qt.ItemDataRole.UserRole));self.table.setItem(r,c,cell)
   self.table.resizeColumnsToContents();self.table.setColumnWidth(0,330);self.set_busy(False);self.status.setText(tr('Mesure terminée. Les fichiers temporaires Windows ne sont pas inclus.'))
  async_task(self,lambda progress:usage(self.parent_app.db),done,self.fail)
 def open_folder(self,item):
  if self.busy:return
  from pathlib import Path
  target=item.data(Qt.ItemDataRole.UserRole)
  if not target:return
  folder=Path(target)
  if not folder.is_dir():self.status.setText(tr('Ce dossier n’existe pas encore : ')+str(folder));return
  if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):self.status.setText(tr('Impossible d’ouvrir ce dossier : ')+str(folder))
  else:self.status.setText(tr('Dossier ouvert : ')+str(folder))
 def fail(self,error):
  if not self.closed:self.set_busy(False);self.status.setText(tr('Opération interrompue : ')+error)
 def operate(self,work,after=None):
  if self.busy:return
  self.set_busy(True);self.status.setText(tr('Nettoyage en cours…'))
  def done(result):
   if self.closed:return
   count,freed,errors=result
   if after:after()
   self.set_busy(False);self.refresh()
   # Retain cleanup result as a separate summary while refreshing measurements.
   self.result_label.setText(str(count)+tr(' fichier(s) supprimé(s), ')+size_text(freed)+tr(' libérés.')+(tr(' Certains fichiers sont conservés : ')+' ; '.join(errors[:3]) if errors else ''))
  async_task(self,lambda progress:work(),done,self.fail)
 def apply_limits(self):
  self.parent_app.db.set_setting('thumbnail_ram_mb',self.ram.value());self.parent_app.db.set_setting('thumbnail_disk_mb',self.disk.value());self.parent_app.engine.thumbnail_cache.configure(self.ram.value()*1048576,self.disk.value()*1048576);self.refresh()
 def clear_cache(self):
  def work():
   cache=self.parent_app.engine.thumbnail_cache;before=cache.usage()[1];count=sum(1 for _ in cache.folder.glob('*.png'));cache.invalidate();self.parent_app.engine.render_cache.clear()
   if self.parent_app.engine.ldraw:self.parent_app.engine.ldraw.clear_mesh_cache()
   return max(0,count-sum(1 for _ in cache.folder.glob('*.png'))),max(0,before-cache.usage()[1]),[]
  def after():
   for cat in self.parent_app.catalogues:
    if getattr(cat,'thumbnails',None):cat.thumbnails.suspend();cat.thumbnails.schedule()
  self.operate(work,after)
 def reject(self):
  if not self.busy:self.closed=True;super().reject()
 def closeEvent(self,event):
  if self.busy:event.ignore();return
  self.closed=True;super().closeEvent(event)

def show_cache(parent):SpaceDialog(parent).exec()
