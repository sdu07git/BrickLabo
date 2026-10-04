from __future__ import annotations
from .fileio import atomic_output,error_message

from .i18n import tr,tf,document,install_qt_language

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


NAV=[(tr('Catalogue Rebrickable'),'RB','part','catalogue'),(tr('Catalogue BrickLink'),'BL','part','catalogue'),
     ('BrickArchitect','BA','part','catalogue'),(tr('Catalogue Mini-Figs'),None,'minifig','catalogue'),(tr('Catalogue Briques Alternatives'),'ALT','part','catalogue'),
     (tr('Catalogue Set Rebrickable'),'RB','set','catalogue'),(tr('Catalogue Set BrickLink'),'BL','set','catalogue'),
     (tr('Catalogue Set Alternatif'),'ALT','set','catalogue'),(tr('Mon Stock'),None,None,'stock'),
     (tr('Impression Étiquettes'),None,None,'queue'),(tr('Historique'),None,None,'history')]


class MainWindow(QMainWindow):
    def __init__(self,db):
        super().__init__();self.db=db;self.engine=VisualEngine(db);self.current_item=None;self.catalogues=[];self.generating=False
        self.setWindowTitle(f'{APP_NAME} — v{VERSION}');self.resize(1500,900);self.setMinimumSize(950,650)
        outer=QWidget();self.setCentralWidget(outer);root=QVBoxLayout(outer)
        top=QHBoxLayout();root.addLayout(top)
        edit=QGroupBox(tr('Édition de l’étiquette'));erow=QHBoxLayout(edit)
        for name,func in [(tr('Contours'),self.category_colors),(tr('Couleur 3D'),self.default_color),(tr('Arêtes 3D'),self.edge_settings),(tr('Éditeur d’étiquettes'),self.editor),(tr('Taille par défaut'),self.label_size)]:
            b=QPushButton(name);b.clicked.connect(func);erow.addWidget(b)
        top.addWidget(edit,1)
        tools=QGroupBox(tr('Données et réglages'));trow=QGridLayout(tools)
        for index,(name,func) in enumerate([(tr('Langue'),self.language_settings),(tr('Clés API'),self.api),(tr('Aide'),lambda:help_dialog(self)),(tr('Mise à jour des données'),self.imports),(tr('Dossier PNG / PDF'),self.output_folder),(tr('Logs'),self.open_logs),(tr('Espace disque'),self.cache_settings),(tr('Sauvegardes'),self.backup_settings),(tr('Sources et licences'),self.sources_licenses)]):
            b=QPushButton(name);b.clicked.connect(func);trow.addWidget(b,index//5,index%5)
        top.addWidget(tools,1)
        split=QSplitter();root.addWidget(split,1)
        self.nav=QListWidget();self.nav.addItems([x[0] for x in NAV]);self.nav.setMinimumWidth(225);self.nav.setMaximumWidth(300);split.addWidget(self.nav)
        self.stack=QStackedWidget();split.addWidget(self.stack)
        for title,source,kind,scope in NAV:
            if scope=='stock':
                widget=QWidget();vl=QVBoxLayout(widget);vl.setContentsMargins(0,0,0,0)
                export_stock=QPushButton(tr('Exporter tout mon stock vers Rebrickable'));export_stock.clicked.connect(self.export_stock_rebrickable);vl.addWidget(export_stock)
                build_stock=QPushButton(tr("Sets réalisables avec Mon stock"));build_stock.clicked.connect(self.build_from_stock);vl.addWidget(build_stock)
                vertical=QSplitter(Qt.Orientation.Vertical);vl.addWidget(vertical)
                for k,label in [(('part','minifig'),tr('Pièces et mini-figs en stock')),('set',tr('Sets en stock'))]:
                    box=QGroupBox(label);bl=QVBoxLayout(box);cat=Catalogue(db,kind=k,scope='stock');bl.addWidget(cat);vertical.addWidget(box);self.bind(cat)
                self.stack.addWidget(widget)
            else:
                widget=QWidget();vl=QVBoxLayout(widget);vl.setContentsMargins(0,0,0,0)
                if scope=='queue':self.queue_toolbar(vl)
                if scope=='history':
                    row=QHBoxLayout();clear=QPushButton(tr('Supprimer tout l’historique'));clear.clicked.connect(self.clear_history);row.addWidget(clear);dates=QPushButton(tr('Supprimer avant une date…'));dates.clicked.connect(self.clear_before);row.addWidget(dates);row.addStretch();vl.addLayout(row)
                if source=='BA':
                    from .brickarchitect import BrickArchitectCatalogue
                    cat=BrickArchitectCatalogue(db)
                else:cat=Catalogue(db,source,kind,scope)
                vl.addWidget(cat);self.bind(cat)
                if scope=='queue':self.queue=cat
                self.stack.addWidget(widget)
        self.right_scroll=QScrollArea();self.right_scroll.setWidgetResizable(True);self.preview=Preview(db,self.engine);self.preview.visual_changed.connect(self.visual_changed);self.right_scroll.setWidget(self.preview);self.right_scroll.setMinimumWidth(290);split.addWidget(self.right_scroll);split.setSizes([235,920,345])
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex);self.nav.setCurrentRow(0)
        self.statusBar().showMessage(tr('Prêt — importe les ressources pour remplir les catalogues.'))
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

    def build_from_stock(self):
        from .build_stock import BuildStockDialog
        BuildStockDialog(self.db,self.engine,self).exec()

    def export_stock_rebrickable(self):
        from .stock_export import StockExportDialog
        StockExportDialog(self.db,self).exec()

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
        d=dialog(tr('Sources et licences'),self);layout=QVBoxLayout(d);browser=QTextBrowser();browser.setOpenExternalLinks(True);browser.setSource(QUrl.fromLocalFile(str(document('SOURCES_ET_LICENCES'))));layout.addWidget(browser);close=QPushButton(tr('Fermer'));close.clicked.connect(d.accept);layout.addWidget(close);d.exec()

    def language_settings(self):
        from .i18n import language_dialog
        language_dialog(self.db,self)

    def backup_settings(self):
        if self.generating:
            QMessageBox.information(self,tr('Sauvegardes'),tr('Attends la fin de la génération.'));return
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
        c=QColorDialog.getColor(QColor(self.db.setting('default_color','#f3d55b')),self,tr('Couleur par défaut des pièces en 3D'))
        if c.isValid():self.db.set_setting('default_color',c.name());self.preview.refresh();self.visual_changed(None)
    def category_colors(self):
        from .contours import ContourDialog
        d=ContourDialog(self.db,self.engine,self.current_item,self)
        if d.exec():
            self.db.set_setting('template',d.template);self.preview.refresh()
    def label_size(self):
        d=dialog(tr('Taille par défaut de l’étiquette'),self);d.resize(450,200);layout=QVBoxLayout(d);form=QFormLayout();layout.addLayout(form);t=self.db.setting('template',default_template());values={}
        for key,name in [('width',tr('Largeur (mm)')),('height',tr('Hauteur (mm)'))]:
            w=QDoubleSpinBox();w.setRange(5,280);w.setDecimals(2);w.setValue(t[key]);values[key]=w;form.addRow(name,w)
        b=QPushButton(tr('Appliquer'));b.clicked.connect(d.accept);layout.addWidget(b)
        if d.exec():
            # Redimensionner proportionnellement les calques du modèle existant.
            sx=values['width'].value()/t['width'];sy=values['height'].value()/t['height']
            for l in t['layers']:l['x']*=sx;l['w']*=sx;l['y']*=sy;l['h']*=sy
            t.update({k:w.value() for k,w in values.items()});self.db.set_setting('template',t);self.preview.refresh()
    def output_folder(self):
        path=QFileDialog.getExistingDirectory(self,tr('Dossier des fichiers PNG et PDF'),self.export_path)
        if path:
            from .storage import application_directory
            if not Path(path).resolve().is_relative_to(application_directory()):
                QMessageBox.information(self,tr('Dossier des fichiers'),tr('Choisis un dossier à l’intérieur du dossier BrickLabo pour conserver tous les fichiers avec le logiciel.'));return
            self.export_path=path;self.db.set_setting('output',path)
    def queue_toolbar(self,layout):
        row=QHBoxLayout();self.format=QComboBox();self.format.addItems(['PDF + PNG','PDF','PNG']);row.addWidget(self.format)
        self.single_file=QCheckBox(tr('Un fichier PDF par étiquette'));row.addWidget(self.single_file)
        b=QPushButton(tr('Générer'));b.clicked.connect(lambda:self.generate('export'));row.addWidget(b)
        b=QPushButton(tr('Aperçu avant impression'));b.clicked.connect(lambda:self.generate('preview'));row.addWidget(b)
        b=QPushButton(tr('Imprimer les étiquettes'));b.setProperty('primary',True);b.clicked.connect(lambda:self.generate('print'));row.addWidget(b);row.addStretch();layout.addLayout(row)
    def generate(self,mode):
        if self.generating:return
        entries=self.queue.selection()
        if not entries:
            entries=self.db.rows('SELECT i.*,q.id AS entry_id,q.color AS chosen_color,q.quantity AS chosen_quantity FROM queue q JOIN items i ON i.id=q.item_id ORDER BY q.id')
        entries=[dict(e,_scope='queue') for e in entries]
        if not entries:QMessageBox.information(self,tr('Étiquettes'),tr('Ajoute des références aux étiquettes à imprimer.'));return
        self.generating=True;template=self.db.setting('template',default_template());folder=Path(self.export_path);fmt=self.format.currentText();separate=self.single_file.isChecked()
        def work(progress):
            images=[];names=[];errors=[];successful=[];stamp=time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns())[-6:]
            for index,item in enumerate(entries):
                progress(tf('Préparation {1} / {3} — ', None, index + 1, None, len(entries), None)+item['ref'])
                try:
                    visual,note=self.engine.visuals(item,item.get('chosen_color'),True);im=render_label(item,self.db,visual,template_for_item(item,self.db,template))
                    count=int(item.get('chosen_quantity',1));successful.append(item)
                    for k in range(count):images.append(im);names.append(re.sub(r'[^A-Za-z0-9_.-]','_',item['source']+'-'+item['ref'])+'-'+str(index+1)+'-'+str(k+1))
                    if not visual.get('main'):errors.append(item['ref']+' : visuel indisponible')
                except Exception as e:errors.append(item['ref']+' : '+str(e))
            paths=[]
            if mode=='export' and images:
                try:
                    folder.mkdir(parents=True,exist_ok=True)
                    if 'PNG' in fmt:
                        for im,name in zip(images,names):
                            p=folder/(stamp+'-'+name+'.png')
                            with atomic_output(p) as tmp:im.save(tmp,format='PNG',dpi=(300,300))
                            paths.append(str(p))
                    if 'PDF' in fmt:
                        if separate:
                            for im,name in zip(images,names):
                                p=folder/(stamp+'-'+name+'.pdf')
                                with atomic_output(p) as tmp:export_pdf([im],tmp,template['width'],template['height'])
                                paths.append(str(p))
                        else:
                            p=folder/('etiquettes-'+stamp+'.pdf')
                            with atomic_output(p) as tmp:export_pdf(images,tmp,template['width'],template['height'])
                            paths.append(str(p))
                except OSError as error:
                    raise RuntimeError(error_message(error)+'\n'+str(len(paths))+tr(' fichier(s) déjà enregistré(s). Génération interrompue ; aucun ajout à l’historique.')) from error
            return images,paths,errors,successful
        def done(result):
            self.generating=False;images,paths,errors,successful=result
            if not images:QMessageBox.warning(self,tr('Génération'),tr('Aucune étiquette créée.\n')+'\n'.join(errors));return
            if errors and mode!='export':
                answer=QMessageBox.question(self,tr('Visuels manquants'),'\n'.join(errors[:15])+tr('\n\nLes étiquettes correspondantes indiquent « Visuel indisponible ». Continuer ?'),QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
                if answer!=QMessageBox.StandardButton.Yes:return
            if mode=='export':
                self.record_history(successful,fmt);self.statusBar().showMessage(tf('{0} étiquette(s), {2} fichier(s) générés dans {4}', len(images), None, len(paths), None, folder))
                warning=tr('\n\nVisuels à compléter :\n')+'\n'.join(errors[:15]) if errors else ''
                QMessageBox.information(self,tr('Génération terminée'),tf('{0} étiquette(s) générée(s).\nDossier : {2}', len(images), None, folder)+warning)
            else:
                p=PrintPreview(images,template['width'],template['height'],self,lambda:self.record_history(successful,tr('Impression')))
                p.exec()
        def fail(error):self.generating=False;QMessageBox.warning(self,tr('Génération'),error)
        async_task(self,work,done,fail)
    def record_history(self,entries,method):
        for e in entries:self.db.run('INSERT INTO history(item_id,color,quantity,method) VALUES(?,?,?,?)',(e['id'],str(e.get('chosen_color','')),e.get('chosen_quantity',1),method))
        self.refresh_counts()
    def clear_history(self):
        if QMessageBox.question(self,tr('Historique'),tr('Supprimer tout l’historique ?'))==QMessageBox.StandardButton.Yes:self.db.run('DELETE FROM history');self.refresh_counts()
    def clear_before(self):
        date,ok=QInputDialog.getText(self,tr('Historique'),tr('Supprimer les entrées avant cette date (AAAA-MM-JJ) :'))
        if ok and re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):self.db.run('DELETE FROM history WHERE date<?',(date,));self.refresh_counts()
    def closeEvent(self,event):
        if self.generating:QMessageBox.information(self,tr('Génération'),tr('Attends la fin de la génération avant de fermer.'));event.ignore();return
        self.startup_timer.stop()
        super().closeEvent(event)


def main():
    from .storage import prepare_portable_storage,configure_portable_database
    root=prepare_portable_storage()
    logger,logs=setup_logging()
    app=QApplication(sys.argv);install_qt_language(app);from PySide6.QtGui import QIcon;app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent.parent/'ressources'/'BrickLabo.ico')));app.setApplicationName(APP_NAME);app.setApplicationVersion(VERSION);app.setOrganizationName('SDU7');app.setStyle('Fusion');app.setStyleSheet(STYLE)
    db=Database(root/'atelier.sqlite');configure_portable_database(db);window=MainWindow(db);window.show()
    def exception(typ,value,tb):
        logger.critical(tr('Exception de l’application'),exc_info=(typ,value,tb))
        QMessageBox.critical(window,tr('Erreur'),str(value)+tr('\nDétail enregistré dans :\n')+str(logs/'BrickLabo_logs.txt'))
    sys.excepthook=exception
    status=app.exec()
    logger.info(tr('Fermeture de l’application, code %s'),status)
    return status
