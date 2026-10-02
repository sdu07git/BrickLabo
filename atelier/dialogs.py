from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path

from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QFormLayout,
    QScrollArea,QTableWidget,QTableWidgetItem,QDialogButtonBox,QSplitter,QFileDialog,QMessageBox,QInputDialog,
    QAbstractItemView,QComboBox,QTextBrowser,QCheckBox,QMenu)

from .ui_common import async_task,dialog,scalable,edit_item
from .services import API,request
from .preview import Preview
from .thumbnails import PartThumbnails
from .boxes import BoxDialog,boxes_for_set


class APIDialog(QDialog):
    def __init__(self,db,parent):
        super().__init__(parent);self.db=db;self.setWindowTitle('Clés API');self.resize(640,380);self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.rb=QLineEdit(db.setting('api_rb',''));self.rb.setEchoMode(QLineEdit.EchoMode.Password);form.addRow('Clé Rebrickable',self.rb)
        self.bl={};values=db.setting('api_bl',{})
        for key,label in [('consumer_key','BrickLink — Consumer Key'),('consumer_secret','BrickLink — Consumer Secret'),('token','BrickLink — Token'),('token_secret','BrickLink — Token Secret')]:
            w=QLineEdit(values.get(key,''));w.setEchoMode(QLineEdit.EchoMode.Password);self.bl[key]=w;form.addRow(label,w)
        show=QCheckBox('Afficher les clés');show.toggled.connect(lambda checked:[w.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password) for w in [self.rb,*self.bl.values()]]);layout.addWidget(show)
        note=QLabel('Les identifiants sont conservés dans ta base locale. BrickLink demande quatre valeurs et une adresse IP autorisée dans les réglages du compte.');note.setWordWrap(True);layout.addWidget(note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons);buttons.rejected.connect(self.reject);buttons.accepted.connect(self.save)
    def save(self):self.db.set_setting('api_rb',self.rb.text().strip());self.db.set_setting('api_bl',{k:w.text().strip() for k,w in self.bl.items()});self.accept()


class ImportDialog(QDialog):
    finished_import=__import__('PySide6.QtCore',fromlist=['Signal']).Signal()
    def __init__(self,db,parent,initial=None,auto_start=False):
        super().__init__(parent);self.db=db;self.setWindowTitle('Mise à jour des bases de données');self.resize(900,650);self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)
        self.paths=list(initial or []);self.running=False;self.auto_start=auto_start;layout=QVBoxLayout(self)
        text=QLabel('Rebrickable : ZIP / CSV / CSV.GZ · BrickLink : TXT tabulé · LDraw : complete.zip\nLes catalogues restent séparés. Les inventaires Rebrickable sont remplacés dans une transaction.');text.setWordWrap(True);layout.addWidget(text)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels(['Fichier','Dernier import','Lignes']);self.table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.table,1)
        from .documents import enable_header_menu
        enable_header_menu(self.table,db,'imports')
        self.list_label=QLabel();self.list_label.setWordWrap(True);layout.addWidget(self.list_label)
        row=QHBoxLayout();self.choose=QPushButton('Choisir les fichiers…');self.choose.clicked.connect(self.pick);row.addWidget(self.choose)
        self.run_button=QPushButton('Importer les fichiers choisis');self.run_button.setProperty('primary',True);self.run_button.clicked.connect(self.start);row.addWidget(self.run_button);layout.addLayout(row)
        apirow=QHBoxLayout();self.rb_button=QPushButton('Télécharger les exports complets Rebrickable');self.rb_button.clicked.connect(self.download_rb);apirow.addWidget(self.rb_button)
        self.api_button=QPushButton('Mise à jour API de la référence sélectionnée');self.api_button.clicked.connect(self.update_api);apirow.addWidget(self.api_button);layout.addLayout(apirow)
        self.bl_button=QPushButton('Ouvrir les téléchargements du catalogue BrickLink');self.bl_button.clicked.connect(lambda:QDesktopServices.openUrl(QUrl('https://www.bricklink.com/catalogDownload.asp')));layout.addWidget(self.bl_button)
        self.progress_label=QLabel('Prêt');self.progress_label.setWordWrap(True);layout.addWidget(self.progress_label)
        self.close_button=QPushButton('Fermer');self.close_button.clicked.connect(self.accept);layout.addWidget(self.close_button);self.refresh()
        if auto_start:__import__('PySide6.QtCore',fromlist=['QTimer']).QTimer.singleShot(0,self.start)
    def refresh(self):
        rows=self.db.rows('SELECT * FROM imports ORDER BY file');self.table.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,k in enumerate(['file','date','rows']):self.table.setItem(r,c,QTableWidgetItem(str(row[k])))
        self.table.setColumnWidth(0,300);self.table.setColumnWidth(1,190)
        self.list_label.setText('Fichiers choisis : '+', '.join(Path(p).name for p in self.paths))
    def pick(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Bases de données','','Données (*.zip *.csv *.gz *.txt)')
        if paths:self.paths=paths;self.refresh()
    def busy(self,value):
        self.running=value
        for w in [self.choose,self.run_button,self.rb_button,self.api_button,self.close_button]:w.setEnabled(not value)
    def reject(self):
        if not self.running:super().reject()
    def start(self):
        if not self.paths:return
        self.busy(True);paths=list(self.paths)
        order=['part_categories','themes','colors','parts','sets','minifigs','inventories','inventory_parts','inventory_sets','inventory_minifigs','elements','part_relationships']
        paths.sort(key=lambda p:next((i for i,s in enumerate(order) if Path(p).name.lower().startswith(s+'.')),100))
        def work(progress):
            result=[]
            for p in paths:
                progress('Import de '+Path(p).name)
                try:
                    count=self.db.import_file(p,lambda name,n:progress(name+' : '+f'{n:,}'.replace(',',' ')+' lignes'));result.append((Path(p).name,count,None))
                except Exception as e:result.append((Path(p).name,0,str(e)))
            progress('Classement des mini-figs par les sets…');self.db.categorize_minifigs();return result
        def done(result):
            self.busy(False);self.refresh();self.finished_import.emit()
            self.progress_label.setText('\n'.join(name+' : '+(str(n)+' lignes' if not error else 'ERREUR — '+error) for name,n,error in result))
            if self.auto_start and all(error is None for name,n,error in result):self.accept()
        async_task(self,work,done,lambda e:(self.busy(False),self.progress_label.setText(e)))
    def download_rb(self):
        self.busy(True)
        def work(progress):
            api=API(self.db);folder=self.db.path.parent/'downloads';paths=[]
            for stem in ['part_categories','themes','colors','parts','sets','minifigs','inventories','inventory_parts','inventory_sets','inventory_minifigs','elements','part_relationships']:
                progress('Téléchargement de '+stem);paths.append(str(api.rb_download(stem,folder)))
            return paths
        def done(paths):self.paths=paths;self.busy(False);self.refresh();self.start()
        async_task(self,work,done,lambda e:(self.busy(False),self.progress_label.setText('Téléchargement impossible : '+e)))
    def update_api(self):
        item=getattr(self.parent(),'current_item',None)
        if not item:QMessageBox.information(self,'API','Sélectionne d’abord une référence dans le catalogue.');return
        self.busy(True)
        async_task(self,lambda progress:API(self.db).enrich(item),lambda r:(self.busy(False),self.progress_label.setText('Référence mise à jour.'),self.finished_import.emit()),lambda e:(self.busy(False),self.progress_label.setText(e)))


class DocumentsDialog(QDialog):
    def __init__(self,db,item,parent):
        super().__init__(parent);self.setWindowTitle('Notices — '+item['ref']);self.resize(950,550);self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)
        from .documents import DocumentsPanel
        layout=QVBoxLayout(self);panel=DocumentsPanel(db);layout.addWidget(panel);panel.set_item(item)



class RelationsDialog(QDialog):
    def __init__(self,db,engine,item,parent):
        super().__init__(parent);self.db=db;self.engine=engine;self.item=item;self.is_set=item['kind'] in ('set','minifig');self.show_sets=item['kind']!='set';self.parts=[];self.sets=[];self.set_image_token=0
        self.setWindowTitle(('Pièces de la mini-figure — ' if item['kind']=='minifig' else 'Pièces du set — ' if self.is_set else 'Sets contenant — ')+item['ref']);self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint);self.resize(1150,750)
        layout=QVBoxLayout(self);split=QSplitter();layout.addWidget(split,1);left=QWidget();lv=QVBoxLayout(left);split.addWidget(left)
        self.sets_heading=QLabel('Sets contenant la mini-figure' if item['kind']=='minifig' else 'Sets contenant la pièce');self.sets_heading.setVisible(self.show_sets);lv.addWidget(self.sets_heading)
        self.tables_splitter=QSplitter(Qt.Orientation.Vertical);self.tables_splitter.setHandleWidth(9);self.tables_splitter.setChildrenCollapsible(False);self.tables_splitter.setStyleSheet('QSplitter::handle:vertical { background:#354963; border-top:1px solid #5a708c; border-bottom:1px solid #5a708c; }');lv.addWidget(self.tables_splitter,1)
        self.set_table=QTableWidget(0,3);self.set_table.setHorizontalHeaderLabels(['Référence','Set','Famille']);self.set_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.set_table.horizontalHeader().setStretchLastSection(True);self.set_table.itemSelectionChanged.connect(self.set_selected);self.set_table.setMinimumHeight(70);self.tables_splitter.addWidget(self.set_table)
        self.set_table.setVisible(self.show_sets);self.set_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.set_table.itemDoubleClicked.connect(self.open_containing_set)
        self.set_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);self.set_table.customContextMenuRequested.connect(self.set_context_menu)
        self.part_table=QTableWidget(0,6);self.part_table.verticalHeader().setDefaultSectionSize(72);self.part_table.setHorizontalHeaderLabels(['Référence','Pièce','Couleur','Quantité','Supplémentaire','Aperçu 3D / photo']);self.part_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.part_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.part_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.part_table.horizontalHeader().setStretchLastSection(True);self.part_table.itemSelectionChanged.connect(self.part_selected);self.part_table.itemDoubleClicked.connect(self.open_component);self.part_table.setMinimumHeight(100);self.tables_splitter.addWidget(self.part_table);self.tables_splitter.setSizes(db.setting('relations_table_sizes',[220,440]));self.tables_splitter.handle(1).setToolTip('Glisser pour répartir la hauteur des deux tableaux');self.tables_splitter.handle(1).setCursor(Qt.CursorShape.SplitVCursor)
        self.source_note=QLabel();self.source_note.setWordWrap(True);lv.addWidget(self.source_note)
        right=QWidget();rv=QVBoxLayout(right);self.set_image_title=QLabel('Aperçu de la mini-figure' if item['kind']=='minifig' else 'Aperçu du set');rv.addWidget(self.set_image_title);self.set_image=QLabel();self.set_image.setMinimumHeight(170);self.set_image.setAlignment(Qt.AlignmentFlag.AlignCenter);rv.addWidget(self.set_image)
        scroll=QScrollArea();scroll.setWidgetResizable(True);self.preview=Preview(db,engine);scroll.setWidget(self.preview);rv.addWidget(scroll,1);split.addWidget(right);split.setSizes([750,350])
        row=QHBoxLayout()
        for name,target,all_parts in [('Toutes les pièces → étiquettes','queue',True),('Toutes les pièces → stock','stock',True),('Sélection → étiquettes','queue',False),('Sélection → stock','stock',False)]:
            b=QPushButton(name);b.clicked.connect(lambda checked=False,t=target,a=all_parts:self.add_parts(t,a));row.addWidget(b)
        layout.addLayout(row)
        if item['source']=='BL' and item['kind']=='set':
            b=QPushButton('Ajouter l’inventaire depuis un fichier TXT');b.clicked.connect(self.import_inventory);layout.addWidget(b)
        if item['source']=='BL':
            b=QPushButton('Charger l’inventaire depuis l’API BrickLink');b.clicked.connect(self.fetch_bl);layout.addWidget(b)
        if item['source']=='RB' and item['kind']=='minifig':
            b=QPushButton('Charger les pièces depuis l’API Rebrickable');b.clicked.connect(self.fetch_rb);layout.addWidget(b)
        if item['source']=='ALT' and self.is_set:
            b=QPushButton('Ajouter une pièce à ce set alternatif');b.clicked.connect(self.add_alt);layout.addWidget(b)
        from .documents import enable_header_menu
        enable_header_menu(self.part_table,db,'relations_parts');enable_header_menu(self.set_table,db,'relations_sets')
        self.thumbnails=PartThumbnails(self.part_table,db,engine,lambda:self.parts,5,self)
        self.preview.visual_changed.connect(self.thumbnails.invalidate)
        self.progress_label=QLabel();layout.addWidget(self.progress_label)
        if self.is_set:
            self.load_set(item)
            if item['kind']=='minifig':self.load_containing_sets()
            if item['kind']=='minifig' and not self.parts and item['source']=='RB' and db.setting('api_rb',''):self.fetch_rb()
        else:
            self.sets=db.containing_sets(item)
            self.set_table.setRowCount(len(self.sets))
            for r,s in enumerate(self.sets):
                for c,k in enumerate(['ref','name','category']):self.set_table.setItem(r,c,QTableWidgetItem(s[k]))
            self.preview.set_item(item)
            if self.sets:self.set_table.selectRow(0)
            elif item['source']=='BL':self.source_note.setText('Les fichiers TXT BrickLink n’incluent pas les relations pièce → sets. L’inventaire d’un set peut être chargé depuis l’API dans le catalogue de sets BrickLink.')
            else:self.source_note.setText('Aucun set trouvé dans les inventaires importés.')
    def set_selected(self):
        row=self.set_table.currentRow()
        if 0<=row<len(self.sets):
            if self.item['kind']=='minifig':self.show_set_image(self.sets[row])
            else:self.load_set(self.sets[row])
    def load_containing_sets(self):
        self.sets=self.db.containing_sets(self.item);self.set_table.setRowCount(len(self.sets))
        self.sets_heading.setText('Sets contenant la mini-figure — '+str(len(self.sets))+' résultat(s)')
        for r,item in enumerate(self.sets):
            for c,key in enumerate(('ref','name','category')):self.set_table.setItem(r,c,QTableWidgetItem(str(item.get(key,''))))
        if self.sets:self.set_table.selectRow(0)
        else:self.sets_heading.setText('Sets contenant la mini-figure — '+('relations absentes des fichiers BrickLink fournis' if self.item['source']=='BL' else 'aucun set trouvé dans les inventaires importés'))
    def set_context_menu(self,pos):
        index=self.set_table.indexAt(pos)
        if not index.isValid() or index.row()>=len(self.sets):return
        item=dict(self.sets[index.row()]);self.set_table.selectRow(index.row())
        menu=QMenu(self)
        action=menu.addAction('Afficher la boîte d’origine',lambda:BoxDialog(self.db,self.engine,item,self).exec())
        action.setEnabled(bool(boxes_for_set(self.db,item)));action.setToolTip('Ouvrir la boîte BrickLink du set.' if action.isEnabled() else 'Aucune boîte répertoriée pour ce set ; importer Original Boxes.txt si nécessaire.')
        menu.setToolTipsVisible(True);menu.exec(self.set_table.viewport().mapToGlobal(pos))

    def open_containing_set(self,_):
        row=self.set_table.currentRow()
        if 0<=row<len(self.sets):RelationsDialog(self.db,self.engine,self.sets[row],self).exec()
    def show_set_image(self,item):
        self.set_image_token+=1;token=self.set_image_token
        self.set_image_title.setText(('Aperçu de la mini-figure — ' if item['kind']=='minifig' else 'Aperçu du set — ')+item['ref'])
        self.set_image.clear();self.set_image.setText('Chargement…')
        def work(progress):return self.engine.visuals(item,download=True)[0].get('main')
        def done(image):
            if token!=self.set_image_token:return
            if image:scalable(self.set_image,image,300,170)
            else:self.set_image.setText('Image indisponible')
        async_task(self,work,done,lambda error:self.set_image.setText('Image inaccessible') if token==self.set_image_token else None)
    def load_set(self,item):
        self.thumbnails.reset();self.active_set=item
        self.parts=self.db.components(item)
        if not self.parts and item['kind']=='minifig' and item['source']=='RB':self.parts=self.db.setting('rb_minifig_components_'+item['ref'],[])
        self.source_note.setText('Inventaire Rebrickable associé à la même référence de set — références des pièces Rebrickable.' if item['source']=='BL' and self.parts and self.parts[0]['source']=='RB' else 'Inventaire '+item['source']+' · '+str(len(self.parts))+' lignes')
        if item['source']=='BL' and self.db.setting('bl_manual_inventory_'+str(item['id'])):
            meta=self.db.setting('bl_manual_inventory_'+str(item['id']))
            self.source_note.setText('Inventaire TXT BrickLink · '+str(len(self.parts))+' lignes utilisées · supplémentaires incluses · variantes / équivalents exclus des ajouts automatiques. Importé le '+meta['date'])
        if not self.parts and item['kind']=='minifig':self.source_note.setText('Composition absente des données locales. Importe inventories et inventory_parts ou charge les pièces depuis l’API de cette source.')
        self.part_table.setRowCount(len(self.parts))
        colors={str(c['id']):c['name'] for c in self.db.rows('SELECT * FROM colors')}
        for r,p in enumerate(self.parts):
            for c,k in [(0,'ref'),(1,'name'),(3,'chosen_quantity')]:self.part_table.setItem(r,c,QTableWidgetItem(str(p.get(k,''))))
            self.part_table.setItem(r,4,QTableWidgetItem('Oui' if p.get('is_spare') else 'Non'))
            self.part_table.setItem(r,5,QTableWidgetItem('3D / photo à charger'))
            choice=QComboBox();choice.setMaximumHeight(32);choice.setEditable(True);choice.addItem('Défaut','')
            if p['source']=='RB':
                for key,name in colors.items():choice.addItem(name+' ('+key+')',key)
            value=str(p.get('chosen_color',''));idx=choice.findData(value)
            if idx<0:choice.addItem(value,value);idx=choice.count()-1
            choice.setCurrentIndex(idx);choice.currentIndexChanged.connect(lambda i,row=r,w=choice:self.change_part_color(row,w.currentData() or w.currentText()));self.part_table.setCellWidget(r,2,choice)
        self.part_table.setColumnWidth(1,280);self.part_table.setColumnWidth(5,150)
        self.thumbnails.schedule()
        image_item=self.sets[self.set_table.currentRow()] if self.item['kind']=='minifig' and 0<=self.set_table.currentRow()<len(self.sets) else item
        self.show_set_image(image_item)
        if self.parts:self.part_table.selectRow(0)
    def open_component(self,_):
        r=self.part_table.currentRow()
        if 0<=r<len(self.parts) and self.parts[r]['kind'] in ('set','minifig'):
            RelationsDialog(self.db,self.engine,self.parts[r],self).exec()
    def fetch_rb(self):
        async_task(self,lambda progress:API(self.db).rb_minifig_components(self.item),lambda parts:self.load_set(self.item),lambda e:self.progress_label.setText(e))
    def closeEvent(self,event):
        if self.show_sets:self.db.set_setting('relations_table_sizes',self.tables_splitter.sizes())
        self.set_image_token+=1;self.thumbnails.stop();super().closeEvent(event)
    def done(self,result):
        if self.show_sets:self.db.set_setting('relations_table_sizes',self.tables_splitter.sizes())
        self.set_image_token+=1;self.thumbnails.stop();super().done(result)
    def change_part_color(self,row,value):
        self.parts[row]['chosen_color']=value;self.thumbnails.invalidate(self.parts[row]);self.part_selected()
    def part_selected(self):
        r=self.part_table.currentRow()
        if 0<=r<len(self.parts):self.preview.set_item(self.parts[r])
    def add_parts(self,target,all_parts):
        selected=self.parts if all_parts else [self.parts[x.row()] for x in self.part_table.selectionModel().selectedRows()]
        for p in selected:self.db.add(target,p['id'],str(p.get('chosen_color','')),p.get('chosen_quantity',1))
        self.progress_label.setText(str(len(selected))+' référence(s) ajoutée(s).')
    def import_inventory(self):
        from .set_inventory import choose_inventory
        choose_inventory(self,self.db,self.item,lambda:self.load_set(self.item))

    def fetch_bl(self):
        if not self.is_set:return
        async_task(self,lambda progress:API(self.db).bl_components(self.item),lambda parts:self.load_set(self.item),lambda e:self.progress_label.setText(e))
    def add_alt(self):
        ref,ok=QInputDialog.getText(self,'Pièce du set','Référence exacte dans le catalogue alternatif :')
        if not ok:return
        rows=self.db.rows("SELECT * FROM items WHERE source='ALT' AND kind='part' AND ref=?",(ref,))
        if not rows:QMessageBox.information(self,'Pièce absente','Ajoute d’abord cette pièce dans le catalogue alternatif.');return
        q,ok=QInputDialog.getInt(self,'Quantité','Nombre de pièces',1,1,9999)
        if ok:self.db.add_alt_component(self.item['id'],rows[0]['id'],'',q);self.load_set(self.item)


def help_dialog(parent):
    d=dialog('Aide et raccourcis',parent);layout=QVBoxLayout(d);browser=QTextBrowser();browser.setOpenExternalLinks(True);layout.addWidget(browser)
    path=Path(__file__).resolve().parent.parent/'AIDE.html'
    browser.setHtml(path.read_text(encoding='utf-8') if path.exists() else 'Consulte le fichier LISEZ-MOI.md.');b=QPushButton('Fermer');b.clicked.connect(d.accept);layout.addWidget(b);d.exec()
