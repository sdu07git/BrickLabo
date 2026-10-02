from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtGui import QAction,QDesktopServices,QColor
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QSplitter,
    QListWidget,QStackedWidget,QScrollArea,QPushButton,QLabel,QComboBox,QFileDialog,QMessageBox,
    QMenu,QInputDialog,QColorDialog,QCheckBox,QGroupBox,QDoubleSpinBox,QFormLayout,QDialog,QGridLayout)

from .version import APP_NAME,VERSION
from .diagnostics import setup_logging,log_directory
from .data import Database
from .catalogue import Catalogue
from .preview import VisualEngine,Preview
from .dialogs import APIDialog,ImportDialog,RelationsDialog,help_dialog
from .editor import LabelEditor
from .labels import default_template,render_label,export_pdf,template_for_item,category_outline
from .printing import PrintPreview
from .ui_common import STYLE,async_task,dialog


NAV=[('Catalogue Rebrickable','RB','part','catalogue'),('Catalogue BrickLink','BL','part','catalogue'),
     ('BrickArchitect','BA','part','catalogue'),('Catalogue Mini-Figs',None,'minifig','catalogue'),('Catalogue Briques Alternatives','ALT','part','catalogue'),
     ('Catalogue Set Rebrickable','RB','set','catalogue'),('Catalogue Set BrickLink','BL','set','catalogue'),
     ('Catalogue Set Alternatif','ALT','set','catalogue'),('Mon Stock',None,None,'stock'),
     ('Impression Étiquettes',None,None,'queue'),('Historique',None,None,'history')]


class MainWindow(QMainWindow):
    def __init__(self,db):
        super().__init__();self.db=db;self.engine=VisualEngine(db);self.current_item=None;self.catalogues=[];self.generating=False
        self.setWindowTitle(f'{APP_NAME} — v{VERSION}');self.resize(1500,900);self.setMinimumSize(950,650)
        outer=QWidget();self.setCentralWidget(outer);root=QVBoxLayout(outer)
        top=QHBoxLayout();root.addLayout(top)
        edit=QGroupBox('Édition de l’étiquette');erow=QHBoxLayout(edit)
        for name,func in [('Contours',self.category_colors),('Couleur 3D',self.default_color),('Arêtes 3D',self.edge_settings),('Éditeur d’étiquettes',self.editor),('Taille par défaut',self.label_size)]:
            b=QPushButton(name);b.clicked.connect(func);erow.addWidget(b)
        top.addWidget(edit,1)
        tools=QGroupBox('Données et réglages');trow=QGridLayout(tools)
        for index,(name,func) in enumerate([('Clés API',self.api),('Aide',lambda:help_dialog(self)),('Mise à jour des données',self.imports),('Dossier PNG / PDF',self.output_folder),('Logs',self.open_logs),('Espace disque',self.cache_settings),('Sauvegardes',self.backup_settings),('Sources et licences',self.sources_licenses)]):
            b=QPushButton(name);b.clicked.connect(func);trow.addWidget(b,index//4,index%4)
        top.addWidget(tools,1)
        split=QSplitter();root.addWidget(split,1)
        self.nav=QListWidget();self.nav.addItems([x[0] for x in NAV]);self.nav.setMinimumWidth(225);self.nav.setMaximumWidth(300);split.addWidget(self.nav)
        self.stack=QStackedWidget();split.addWidget(self.stack)
        for title,source,kind,scope in NAV:
            if scope=='stock':
                widget=QWidget();vl=QVBoxLayout(widget);vl.setContentsMargins(0,0,0,0);vertical=QSplitter(Qt.Orientation.Vertical);vl.addWidget(vertical)
                for k,label in [(('part','minifig'),'Pièces et mini-figs en stock'),('set','Sets en stock')]:
                    box=QGroupBox(label);bl=QVBoxLayout(box);cat=Catalogue(db,kind=k,scope='stock');bl.addWidget(cat);vertical.addWidget(box);self.bind(cat)
                self.stack.addWidget(widget)
            else:
                widget=QWidget();vl=QVBoxLayout(widget);vl.setContentsMargins(0,0,0,0)
                if scope=='queue':self.queue_toolbar(vl)
                if scope=='history':
                    row=QHBoxLayout();clear=QPushButton('Supprimer tout l’historique');clear.clicked.connect(self.clear_history);row.addWidget(clear);dates=QPushButton('Supprimer avant une date…');dates.clicked.connect(self.clear_before);row.addWidget(dates);row.addStretch();vl.addLayout(row)
                if source=='BA':
                    from .brickarchitect import BrickArchitectCatalogue
                    cat=BrickArchitectCatalogue(db)
                else:cat=Catalogue(db,source,kind,scope)
                vl.addWidget(cat);self.bind(cat)
                if scope=='queue':self.queue=cat
                self.stack.addWidget(widget)
        self.right_scroll=QScrollArea();self.right_scroll.setWidgetResizable(True);self.preview=Preview(db,self.engine);self.preview.visual_changed.connect(self.visual_changed);self.right_scroll.setWidget(self.preview);self.right_scroll.setMinimumWidth(290);split.addWidget(self.right_scroll);split.setSizes([235,920,345])
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex);self.nav.setCurrentRow(0)
        self.statusBar().showMessage('Prêt — importe les ressources pour remplir les catalogues.')
        self.export_path=db.setting('output',str(db.path.parent/'Exports'))
        from .backup_dialog import show_report
        QTimer.singleShot(0,lambda:show_report(self))
        self.import_window=None
        self.startup_timer=QTimer(self);self.startup_timer.setSingleShot(True);self.startup_timer.timeout.connect(self.first_import);self.startup_timer.start(100)

    def bind(self,cat):
        self.catalogues.append(cat);cat.selected.connect(self.item_selected);cat.opened.connect(self.open_item);cat.changed.connect(self.refresh_counts)
        cat.engine=self.engine
        cat.load_thumbnails()
    def item_selected(self,item):self.current_item=item;self.preview.set_item(item)
    def visual_changed(self,item):
        for cat in self.catalogues:
            if cat.isVisible():cat.refresh_visual(item)

    def open_item(self,item):
        d=RelationsDialog(self.db,self.engine,item,self);d.exec();self.refresh_counts()
    def refresh_counts(self):
        for c in self.catalogues:
            if c.scope in ('stock','queue','history') or c.source=='ALT':c.reload()
    def refresh_all(self):
        for c in self.catalogues:c.reload_categories();c.reload()
        if self.current_item:self.preview.set_item(self.db.get_item(self.current_item['id']))
    def first_import(self):
        base=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent.parent
        resources=base/'ressources'
        paths=[str(p) for p in resources.iterdir() if p.suffix.lower() in ('.zip','.txt','.csv','.gz') and p.name!='brickarchitect_ldraw.zip'] if resources.exists() else []
        empty=not self.db.rows("SELECT COUNT(*) AS n FROM items WHERE source<>'BA'")[0]['n']
        if not empty:
            supplemental={'colors.txt','codes.txt','categories.txt','itemtypes.txt','original boxes.txt'}
            imported={r['file'].lower() for r in self.db.rows('SELECT file FROM imports')}
            if supplemental.issubset(imported):return
            paths=[p for p in paths if Path(p).name.lower() in supplemental]
        if paths:
            if empty:
                d=ImportDialog(self.db,self,paths,auto_start=True);d.finished_import.connect(self.refresh_all);self.import_window=d;d.exec()
            else:self.imports(paths)

    def sources_licenses(self):
        from PySide6.QtWidgets import QTextBrowser
        d=dialog('Sources et licences',self);layout=QVBoxLayout(d);browser=QTextBrowser();browser.setOpenExternalLinks(True);browser.setSource(QUrl.fromLocalFile(str(Path(__file__).resolve().parent.parent/'SOURCES_ET_LICENCES.html')));layout.addWidget(browser);close=QPushButton('Fermer');close.clicked.connect(d.accept);layout.addWidget(close);d.exec()

    def backup_settings(self):
        if self.generating:
            QMessageBox.information(self,'Sauvegardes','Attends la fin de la génération.');return
        from .backup_dialog import BackupDialog
        BackupDialog(self).exec()

    def cache_settings(self):
        from .cache_dialog import show_cache
        show_cache(self)

    def open_logs(self):
        folder=log_directory();folder.mkdir(parents=True,exist_ok=True);QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def imports(self,paths=None):
        if isinstance(paths,bool):paths=None
        d=ImportDialog(self.db,self,paths);d.finished_import.connect(self.refresh_all);self.import_window=d;d.exec()
    def api(self):APIDialog(self.db,self).exec()
    def editor(self):
        d=LabelEditor(self.db,self.engine,self.current_item,self)
        if d.exec():
            if self.current_item:self.preview.refresh()
    def edge_settings(self):
        from .edges import EdgeDialog
        d=EdgeDialog(self.db,self.engine,self.current_item,self)
        if d.exec():
            self.db.set_setting('edge_settings',d.settings());self.preview.refresh();self.visual_changed(None)

    def default_color(self):
        c=QColorDialog.getColor(QColor(self.db.setting('default_color','#f3d55b')),self,'Couleur par défaut des pièces en 3D')
        if c.isValid():self.db.set_setting('default_color',c.name());self.preview.refresh();self.visual_changed(None)
    def category_colors(self):
        from .contours import ContourDialog
        d=ContourDialog(self.db,self.engine,self.current_item,self)
        if d.exec():
            self.db.set_setting('template',d.template);self.preview.refresh()
    def label_size(self):
        d=dialog('Taille par défaut de l’étiquette',self);d.resize(450,200);layout=QVBoxLayout(d);form=QFormLayout();layout.addLayout(form);t=self.db.setting('template',default_template());values={}
        for key,name in [('width','Largeur (mm)'),('height','Hauteur (mm)')]:
            w=QDoubleSpinBox();w.setRange(5,280);w.setDecimals(2);w.setValue(t[key]);values[key]=w;form.addRow(name,w)
        b=QPushButton('Appliquer');b.clicked.connect(d.accept);layout.addWidget(b)
        if d.exec():
            # Redimensionner proportionnellement les calques du modèle existant.
            sx=values['width'].value()/t['width'];sy=values['height'].value()/t['height']
            for l in t['layers']:l['x']*=sx;l['w']*=sx;l['y']*=sy;l['h']*=sy
            t.update({k:w.value() for k,w in values.items()});self.db.set_setting('template',t);self.preview.refresh()
    def output_folder(self):
        path=QFileDialog.getExistingDirectory(self,'Dossier des fichiers PNG et PDF',self.export_path)
        if path:
            from .storage import application_directory
            if not Path(path).resolve().is_relative_to(application_directory()):
                QMessageBox.information(self,'Dossier des fichiers','Choisis un dossier à l’intérieur du dossier BrickLabo pour conserver tous les fichiers avec le logiciel.');return
            self.export_path=path;self.db.set_setting('output',path)
    def queue_toolbar(self,layout):
        row=QHBoxLayout();self.format=QComboBox();self.format.addItems(['PDF + PNG','PDF','PNG']);row.addWidget(self.format)
        self.single_file=QCheckBox('Un fichier PDF par étiquette');row.addWidget(self.single_file)
        b=QPushButton('Générer');b.clicked.connect(lambda:self.generate('export'));row.addWidget(b)
        b=QPushButton('Aperçu avant impression');b.clicked.connect(lambda:self.generate('preview'));row.addWidget(b)
        b=QPushButton('Imprimer les étiquettes');b.setProperty('primary',True);b.clicked.connect(lambda:self.generate('print'));row.addWidget(b);row.addStretch();layout.addLayout(row)
    def generate(self,mode):
        if self.generating:return
        entries=self.queue.selection()
        if not entries:
            entries=self.db.rows('SELECT i.*,q.id AS entry_id,q.color AS chosen_color,q.quantity AS chosen_quantity FROM queue q JOIN items i ON i.id=q.item_id ORDER BY q.id')
        entries=[dict(e,_scope='queue') for e in entries]
        if not entries:QMessageBox.information(self,'Étiquettes','Ajoute des références aux étiquettes à imprimer.');return
        self.generating=True;template=self.db.setting('template',default_template());folder=Path(self.export_path);fmt=self.format.currentText();separate=self.single_file.isChecked()
        def work(progress):
            images=[];names=[];errors=[];successful=[];stamp=time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns())[-6:]
            for index,item in enumerate(entries):
                progress(f'Préparation {index+1} / {len(entries)} — '+item['ref'])
                try:
                    visual,note=self.engine.visuals(item,item.get('chosen_color'),True);im=render_label(item,self.db,visual,template_for_item(item,self.db,template))
                    count=int(item.get('chosen_quantity',1));successful.append(item)
                    for k in range(count):images.append(im);names.append(re.sub(r'[^A-Za-z0-9_.-]','_',item['source']+'-'+item['ref'])+'-'+str(index+1)+'-'+str(k+1))
                    if not visual.get('main'):errors.append(item['ref']+' : visuel indisponible')
                except Exception as e:errors.append(item['ref']+' : '+str(e))
            paths=[]
            if mode=='export' and images:
                folder.mkdir(parents=True,exist_ok=True)
                if 'PNG' in fmt:
                    for im,name in zip(images,names):p=folder/(stamp+'-'+name+'.png');im.save(p,dpi=(300,300));paths.append(str(p))
                if 'PDF' in fmt:
                    if separate:
                        for im,name in zip(images,names):p=folder/(stamp+'-'+name+'.pdf');export_pdf([im],p,template['width'],template['height']);paths.append(str(p))
                    else:p=folder/('etiquettes-'+stamp+'.pdf');export_pdf(images,p,template['width'],template['height']);paths.append(str(p))
            return images,paths,errors,successful
        def done(result):
            self.generating=False;images,paths,errors,successful=result
            if not images:QMessageBox.warning(self,'Génération','Aucune étiquette créée.\n'+'\n'.join(errors));return
            if errors and mode!='export':
                answer=QMessageBox.question(self,'Visuels manquants','\n'.join(errors[:15])+'\n\nLes étiquettes correspondantes indiquent « Visuel indisponible ». Continuer ?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
                if answer!=QMessageBox.StandardButton.Yes:return
            if mode=='export':
                self.record_history(successful,fmt);self.statusBar().showMessage(f'{len(images)} étiquette(s), {len(paths)} fichier(s) générés dans {folder}')
                warning='\n\nVisuels à compléter :\n'+'\n'.join(errors[:15]) if errors else ''
                QMessageBox.information(self,'Génération terminée',f'{len(images)} étiquette(s) générée(s).\nDossier : {folder}'+warning)
            else:
                p=PrintPreview(images,template['width'],template['height'],self,lambda:self.record_history(successful,'Impression'))
                p.exec()
        def fail(error):self.generating=False;QMessageBox.warning(self,'Génération',error)
        async_task(self,work,done,fail)
    def record_history(self,entries,method):
        for e in entries:self.db.run('INSERT INTO history(item_id,color,quantity,method) VALUES(?,?,?,?)',(e['id'],str(e.get('chosen_color','')),e.get('chosen_quantity',1),method))
        self.refresh_counts()
    def clear_history(self):
        if QMessageBox.question(self,'Historique','Supprimer tout l’historique ?')==QMessageBox.StandardButton.Yes:self.db.run('DELETE FROM history');self.refresh_counts()
    def clear_before(self):
        date,ok=QInputDialog.getText(self,'Historique','Supprimer les entrées avant cette date (AAAA-MM-JJ) :')
        if ok and re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):self.db.run('DELETE FROM history WHERE date<?',(date,));self.refresh_counts()
    def closeEvent(self,event):
        if self.generating:QMessageBox.information(self,'Génération','Attends la fin de la génération avant de fermer.');event.ignore();return
        self.startup_timer.stop()
        super().closeEvent(event)


def main():
    from .storage import prepare_portable_storage,configure_portable_database
    root=prepare_portable_storage()
    logger,logs=setup_logging()
    app=QApplication(sys.argv);from PySide6.QtGui import QIcon;app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent.parent/'ressources'/'BrickLabo.ico')));app.setApplicationName(APP_NAME);app.setApplicationVersion(VERSION);app.setOrganizationName('SDU7');app.setStyle('Fusion');app.setStyleSheet(STYLE)
    db=Database(root/'atelier.sqlite');configure_portable_database(db);window=MainWindow(db);window.show()
    def exception(typ,value,tb):
        logger.critical('Exception de l’application',exc_info=(typ,value,tb))
        QMessageBox.critical(window,'Erreur',str(value)+'\nDétail enregistré dans :\n'+str(logs/'BrickLabo_logs.txt'))
    sys.excepthook=exception
    status=app.exec()
    logger.info('Fermeture de l’application, code %s',status)
    return status
