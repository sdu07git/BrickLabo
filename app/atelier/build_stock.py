from .windows import show_window
"""Read-only inventory matching against the complete stock ledger."""
from collections import Counter
from functools import lru_cache
import json
import threading
from .i18n import tr
from .result_tables import row_index,fill_table
from .color_links import resolve, candidates, bl_palette, rb_palette

class InventoryReader:
    def __init__(self,c,ignore_colors=False,excluded_entries=None):
        self.c=c;self.ignore_colors=ignore_colors;self.warnings=set();self.excluded_entries=set(excluded_entries or [])
        self.canonical=lru_cache(maxsize=20000)(self.canonical);self.children=lru_cache(maxsize=2500)(self.children)
        self.partmap=self.setting('export_rb_bl_parts',{});self.colormap=self.setting('export_rb_bl_colors',{})
        self.blcolors=bl_palette(self.setting)
        self.colors=rb_palette();self.colors.update({str(r['id']):dict(r) for r in c.execute('SELECT * FROM colors')})
    def setting(self,key,default=None):
        row=self.c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return json.loads(row['value']) if row else default
    def canonical(self,source,ref,color):
        native_source=source;native_ref=ref
        if source=='BL':
            candidates=self.partmap.get(ref,[])
            if len(candidates)==1:native_source='RB';native_ref=candidates[0]
            elif not candidates:
                match=self.c.execute("SELECT 1 FROM items a JOIN items b ON a.ref=b.ref AND a.name=b.name WHERE a.source='BL' AND b.source='RB' AND a.kind='part' AND b.kind='part' AND a.ref=?",(ref,)).fetchone()
                if match:native_source='RB'
        if self.ignore_colors:return native_source,native_ref,'*'
        color=str(color or '')
        if source=='BL':
            mapped=resolve(self.setting,ref,color)
            colour='RB:'+mapped if mapped else 'BL:'+color
        else:colour='RB:'+color if color in self.colors else ''
        if not color or color.startswith('#'):colour=''
        return native_source,native_ref,colour
    def part(self,source,ref,color,qty):
        key=self.canonical(source,ref,str(color));unknown=not key[2]
        return Counter({key:int(qty)}) if int(qty)>0 else Counter(),unknown
    def children(self,source,kind,ref):
        """Return raw rows, never silently lose references absent from items."""
        item=self.c.execute('SELECT id FROM items WHERE source=? AND kind=? AND ref=?',(source,kind,ref)).fetchone()
        rows=[];found=False
        if source=='ALT' and item:
            values=self.setting('alt_components_'+str(item['id']),[]);found=bool(values)
            for value in values:
                p=self.c.execute('SELECT source,kind,ref FROM items WHERE id=?',(value['item_id'],)).fetchone()
                if not p:return (),False
                rows.append((p['source'],p['kind'],p['ref'],str(value['color']),int(value['quantity']),False))
            return tuple(rows),found
        cache=self.c.execute('SELECT parts FROM catalogue_inventory WHERE source=? AND ref=?',(source,ref)).fetchone()
        if cache and not (source=='BL' and item and kind=='set' and self.setting('bl_manual_inventory_'+str(item['id']))):
            values=json.loads(cache['parts'])
            return tuple((p['source'],p.get('kind','part'),p['ref'],str(p['color']),int(p['quantity']),bool(p.get('is_spare'))) for p in values),bool(values)
        if source=='BL':
            if item and kind=='set' and self.setting('bl_manual_inventory_'+str(item['id'])):
                records=self.c.execute('SELECT i.source,i.kind,i.ref,p.color,p.quantity,p.extra FROM bl_manual_inventory p LEFT JOIN items i ON i.id=p.item_id WHERE p.set_id=? AND p.alternate=0 AND p.counterpart=0',(item['id'],)).fetchall()
                for p in records:
                    if p['source'] is None:return (),False
                    rows.append((p['source'],p['kind'],p['ref'],str(p['color']),int(p['quantity']),bool(p['extra'])))
                return tuple(rows),bool(rows)
            cached=self.setting(('bl_minifig_components_' if kind=='minifig' else 'bl_components_')+ref,[])
            if cached:
                return tuple((p['source'],p['kind'],p['ref'],str(p.get('chosen_color','')),int(p.get('chosen_quantity',1)),bool(p.get('is_spare',0))) for p in cached),True
            if kind=='set':
                match=self.c.execute("SELECT ref FROM items WHERE source='RB' AND kind='set' AND ref IN (?,?) ORDER BY ref",(ref,ref+'-1')).fetchone()
                if match:return self.children('RB','set',match['ref'])
            return (),False
        if source!='RB':return (),False
        inv=self.c.execute('SELECT id FROM inventories WHERE set_num=? ORDER BY version DESC,id DESC LIMIT 1',(ref,)).fetchone()
        if not inv and kind=='minifig':
            cached=self.setting('rb_minifig_components_'+ref,[])
            if cached:return tuple((p['source'],p['kind'],p['ref'],str(p.get('chosen_color','')),int(p.get('chosen_quantity',1)),bool(p.get('is_spare',0))) for p in cached),True
        if not inv:return (),False
        iid=inv['id']
        for p in self.c.execute('SELECT part_num,color_id,quantity,is_spare FROM inventory_parts WHERE inventory_id=?',(iid,)):
            rows.append(('RB','part',p['part_num'],str(p['color_id']),int(p['quantity']),bool(p['is_spare'])))
        for p in self.c.execute('SELECT fig_num,quantity FROM inventory_minifigs WHERE inventory_id=?',(iid,)):rows.append(('RB','minifig',p['fig_num'],'',int(p['quantity']),False))
        for p in self.c.execute('SELECT set_num,quantity FROM inventory_sets WHERE inventory_id=?',(iid,)):rows.append(('RB','set',p['set_num'],'',int(p['quantity']),False))
        return tuple(rows),bool(rows)
    def inventory(self,source,kind,ref,trail=(),spares=False):
        identity=(source,kind,ref)
        if identity in trail:return Counter(),False
        rows,complete=self.children(*identity);counts=Counter()
        for src,typ,num,color,qty,extra in rows:
            if qty<=0 or (extra and not spares):continue
            if typ=='part':part,unknown=self.part(src,num,color,qty);counts.update(part);complete=complete and not unknown
            elif typ in ('minifig','set'):
                children,ok=self.inventory(src,typ,num,trail+(identity,),spares);complete=complete and ok
                counts.update({key:amount*qty for key,amount in children.items()})
            else:complete=False
        return counts,complete and bool(counts)
    def stock(self):
        available=Counter();ignored=0;reserved=Counter()
        for entry in self.excluded_entries:
            item=self.c.execute("SELECT i.kind,i.ref FROM stock_available s JOIN items i ON i.id=s.item_id WHERE s.id=?",(entry,)).fetchone()
            if not item or item['kind']!='set':continue
            tracked=self.c.execute('SELECT item_id,color,quantity FROM stock_set_components WHERE set_entry_id=?',(abs(entry),)).fetchall()
            if not tracked:raise ValueError(tr('Impossible d’exclure les pièces de ce set sans suivi de stock : ')+item['ref'])
            for part in tracked:reserved[(part['item_id'],str(part['color']))]+=int(part['quantity'])
        for row in self.c.execute('SELECT i.source,i.kind,i.ref,s.color,s.quantity,s.id AS entry,s.item_id FROM stock_available s JOIN items i ON i.id=s.item_id WHERE s.quantity>0'):
            if row['kind']=='set':
                if not self.c.execute('SELECT 1 FROM stock_set_components WHERE set_entry_id=? LIMIT 1',(abs(row['entry']),)).fetchone():self.warnings.add(tr('Certains sets n’ont pas de suivi de pièces : vérifier leur présence dans le stock des pièces.'))
                continue
            if row['entry'] in self.excluded_entries:continue
            quantity=max(0,int(row['quantity'])-reserved[(row['item_id'],str(row['color']))])
            if not quantity:continue
            if row['kind']=='part':
                counts,unknown=self.part(row['source'],row['ref'],row['color'],quantity)
                if unknown:ignored+=quantity;continue
            elif row['kind']=='minifig':
                counts,ok=self.inventory(row['source'],'minifig',row['ref'],spares=True)
                if not ok:self.warnings.add(tr('Mini-figs avec inventaire absent ou incomplet : seules leurs pièces identifiées sont comptées.'))
                counts=Counter({k:v*quantity for k,v in counts.items() if k[2]})
            else:continue
            available.update(counts)
        if ignored:self.warnings.add(str(ignored)+tr(' pièces de couleur non renseignée ignorées en mode couleurs exactes.'))
        if self.c.execute("SELECT 1 FROM stock_available s JOIN items i ON i.id=s.item_id WHERE i.source='BL' LIMIT 1").fetchone():self.warnings.add(tr('Les correspondances BrickLink enregistrées sont utilisées ; sans correspondance, les références restent distinctes. Utiliser Convertir BrickLink dans l’export du stock si nécessaire.'))
        return available

def compare(required,available,copies=1):
    total=sum(required.values())*copies
    missing=sum(max(0,n*copies-available.get(k,0)) for k,n in required.items())
    return total,missing,(100*(total-missing)/total if total else 0)

def find_builds(db,source='RB',text='',ignore_colors=False,copies=1,minimum=100,cancel=None,progress=lambda _:None,excluded_entries=None):
    cancel=cancel or threading.Event();results=[];excluded=0
    with db.connect() as c:
        c.execute('BEGIN')
        reader=InventoryReader(c,ignore_colors,excluded_entries);available=reader.stock()
        from .search_index import indexed_clause
        from .data import Database
        if db.search_index_available:
            conditions,args=indexed_clause(text);clause="i.kind='set' AND i.catalogue_hidden=0"+(' AND '+' AND '.join(conditions) if conditions else '')
        else:
            clause,args=Database.filter_clause(kind='set',search=text);clause=clause.removeprefix('WHERE ')+' AND i.catalogue_hidden=0'
        if source:clause+=' AND i.source=?';args.append(source)
        sets=c.execute('SELECT i.* FROM items i WHERE '+clause+' ORDER BY i.source,i.ref',args).fetchall()
        for index,item in enumerate(sets):
            if cancel.is_set():break
            if index%50==0:progress(str(index)+' / '+str(len(sets))+tr(' sets analysés…'))
            required,complete=reader.inventory(item['source'],'set',item['ref'])
            if not complete:excluded+=1;continue
            total,missing,percent=compare(required,available,copies)
            if percent+1e-9>=minimum:results.append(dict(item,total=total,missing=missing,percent=percent,copies=copies))
        results.sort(key=lambda r:(r['missing']>0,-r['percent'],r['missing'],r['ref']))
        warnings=sorted(reader.warnings)
    return results,warnings,excluded,cancel.is_set()

def build_details(db,item,ignore_colors=False,copies=1,excluded_entries=None):
    with db.connect() as c:
        c.execute('BEGIN');reader=InventoryReader(c,ignore_colors,excluded_entries);available=reader.stock();required,complete=reader.inventory(item['source'],'set',item['ref'])
        rows=[]
        for (source,ref,color),quantity in sorted(required.items()):
            need=quantity*copies;have=available.get((source,ref,color),0)
            name=c.execute("SELECT name FROM items WHERE source=? AND kind='part' AND ref=?",(source,ref)).fetchone()
            rows.append((source,ref,name['name'] if name else '',color,need,have,max(0,need-have)))
        return rows,complete

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,QSpinBox,QCheckBox,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QFileDialog,QMessageBox,QMenu
from .ui_common import async_task

class BuildStockDialog(QDialog):
    def __init__(self,db,engine=None,parent=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.results=[];self.closed=False;self.busy=False;self.cancel=threading.Event();self.detail_token=0;self.last_excluded=[];self.last_ignore=False;self.last_copies=1;self.detail_rows=[];self.detail_item=None
        self.setWindowTitle(tr('Sets réalisables avec Mon stock'));self.resize(1120,780);self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)
        layout=QVBoxLayout(self)
        note=QLabel(tr('Calcul local sur les inventaires disponibles. Les pièces des sets en stock sont déjà comptées : on ne les ajoute pas une seconde fois. Chaque résultat est évalué séparément ; cela ne garantit pas de construire tous les résultats simultanément. Aucun stock n’est retiré.'));note.setWordWrap(True);layout.addWidget(note)
        bar=QHBoxLayout();self.source=QComboBox()
        for label,code in [('Rebrickable','RB'),('BrickLink','BL'),(tr('Alternatifs'),'ALT'),(tr('Toutes les sources'),'')]:self.source.addItem(label,code)
        bar.addWidget(self.source);self.search=QLineEdit();self.search.setPlaceholderText(tr('Référence ou mots du nom / thème'));bar.addWidget(self.search,1)
        self.ignore=QCheckBox(tr('Ignorer les couleurs'));bar.addWidget(self.ignore);layout.addLayout(bar)
        bar=QHBoxLayout();bar.addWidget(QLabel(tr('Pièces possédées au minimum (%)')));self.minimum=QSpinBox();self.minimum.setRange(0,100);self.minimum.setValue(100);bar.addWidget(self.minimum)
        bar.addWidget(QLabel(tr('Exemplaires à construire')));self.copies=QSpinBox();self.copies.setRange(1,999);bar.addWidget(self.copies)
        self.run=QPushButton(tr('Rechercher les sets réalisables'));self.run.clicked.connect(self.start);bar.addWidget(self.run)
        self.stop=QPushButton(tr('Arrêter'));self.stop.setEnabled(False);self.stop.clicked.connect(self.cancel.set);bar.addWidget(self.stop);layout.addLayout(bar)
        options=QHBoxLayout();self.stock_filter=QPushButton(tr('Choisir le stock utilisable…'));self.stock_filter.clicked.connect(self.choose_stock);options.addWidget(self.stock_filter)
        self.mocs=QPushButton(tr('MOC avec les pièces disponibles…'));self.mocs.clicked.connect(self.find_mocs);options.addWidget(self.mocs);global_search=QPushButton(tr('MOC par mot clé / créateur'));global_search.clicked.connect(self.global_search);options.addWidget(global_search);layout.addLayout(options)
        self.status=QLabel(tr('Choisis les critères puis lance la recherche. À 100 %, seuls les sets complets sont affichés.'));self.status.setWordWrap(True);layout.addWidget(self.status)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Set'),tr('Année'),tr('Possédé %'),tr('Pièces requises'),tr('Manquantes'),tr('Aperçu du set')]);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);self.table.horizontalHeader().setStretchLastSection(False);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(self.table,1)
        for column,width in enumerate((70,110,330,65,90,120,100,140)):self.table.setColumnWidth(column,width)
        self.set_thumbnails=None
        if self.engine:
            from .thumbnails import PartThumbnails
            self.set_thumbnails=PartThumbnails(self.table,self.db,self.engine,self.visible_sets,7,self)
            self.table.horizontalHeader().sortIndicatorChanged.connect(lambda *_:self.set_thumbnails.reset())
        self.table.itemSelectionChanged.connect(self.detail);self.table.itemDoubleClicked.connect(self.open_set)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)
        self.detail_status=QLabel(tr('Sélectionne un résultat pour voir les pièces nécessaires.'));layout.addWidget(self.detail_status)
        self.parts=QTableWidget(0,8);self.parts.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Pièce'),tr('Couleur'),tr('Requis'),tr('Possédé'),tr('Manquant'),tr('Aperçu 3D / photo')]);self.parts.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive);self.parts.horizontalHeader().setStretchLastSection(False);self.parts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(self.parts,1)
        self.parts.setColumnWidth(2,350)
        self.parts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.parts.itemDoubleClicked.connect(self.open_part)
        self.part_visuals=[];self.thumbnails=None
        if self.engine:
            from .thumbnails import PartThumbnails
            self.thumbnails=PartThumbnails(self.parts,self.db,self.engine,self.visible_parts,7,self,force_3d=True)
            self.parts.horizontalHeader().sortIndicatorChanged.connect(lambda *_:self.thumbnails.reset())
        self.parts.setColumnWidth(7,125)
        exports=QHBoxLayout()
        self.export_missing=QPushButton(tr('Exporter les pièces manquantes (CSV)'))
        self.export_owned=QPushButton(tr('Exporter les pièces en stock (CSV)'))
        self.export_missing.clicked.connect(lambda:self.export_parts('missing'))
        self.export_owned.clicked.connect(lambda:self.export_parts('owned'))
        for button in (self.export_missing,self.export_owned):button.setEnabled(False);exports.addWidget(button)
        layout.addLayout(exports)
        self.warnings=QLabel();self.warnings.setWordWrap(True);layout.addWidget(self.warnings)
        close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);layout.addWidget(close)
    def choose_stock(self):
        from .stock_filter import StockFilterDialog
        def saved(result):
            if not result:return
            if self.set_thumbnails:self.set_thumbnails.suspend()
            self.detail_token+=1;self.clear_details();self.parts.setRowCount(0);self.table.setRowCount(0);self.results=[]
            self.status.setText(tr('Stock utilisable modifié : relance la recherche.'))
        show_window(StockFilterDialog(self.db,self),self,saved)

    def global_search(self):
        from .moc_search import MocSearchDialog
        show_window(MocSearchDialog(self.db,self.engine,self,keyword=self.search.text().strip()),self)

    def visible_sets(self):
        return [self.results[index] if 0<=index<len(self.results) else None for index in (row_index(self.table,i) for i in range(self.table.rowCount()))]

    def find_mocs(self):
        from .stock_mocs import StockMocsDialog
        show_window(StockMocsDialog(self.db,self.engine,self.db.setting('build_excluded_entries',[]),self),self)

    def context_menu(self,pos):
        index=self.table.indexAt(pos)
        if not index.isValid() or not 0<=index.row()<len(self.results):return
        item=dict(self.results[row_index(self.table,index.row())])
        self.table.selectRow(index.row())
        menu=QMenu(self)
        menu.addAction(tr('Voir les constructions alternatives'),lambda:self.show_alternates(item))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def show_alternates(self,item):
        from .alternates import AlternatesDialog
        show_window(AlternatesDialog(self.db,self.engine,item,self),self)

    def start(self):
        if self.busy:return
        revision=self.db.stock_revision()
        if self.set_thumbnails:self.set_thumbnails.suspend()
        self.clear_details();self.busy=True;self.cancel.clear();self.detail_token+=1;self.parts.setRowCount(0);self.table.setRowCount(0);self.results=[]
        source=self.source.currentData();text=self.search.text();ignore=self.ignore.isChecked();copies=self.copies.value();minimum=self.minimum.value();excluded_stock=list(self.db.setting('build_excluded_entries',[]))
        for widget in (self.run,self.source,self.search,self.ignore,self.copies,self.minimum,self.stock_filter,self.mocs):widget.setEnabled(False)
        self.stop.setEnabled(True);self.status.setText(tr('Analyse du stock et des inventaires…'));self.warnings.clear()
        def finish():
            self.busy=False;self.stop.setEnabled(False)
            for widget in (self.run,self.source,self.search,self.ignore,self.copies,self.minimum,self.stock_filter,self.mocs):widget.setEnabled(True)
        def done(data):
            if self.closed:return
            if revision!=self.db.stock_revision():finish();self.stock_changed();return
            self.results,warnings,excluded,cancelled=data;self.last_ignore=ignore;self.last_copies=copies;self.last_excluded=excluded_stock
            fill_table(self.table,[[round(row[key],1) if key=='percent' else row.get(key,'') for key in ('source','ref','name','year','percent','total','missing')]+[tr('Chargement…') if self.engine else tr('Aperçu indisponible')] for row in self.results])
            if self.set_thumbnails:self.set_thumbnails.reset()
            self.status.setText((tr('Recherche arrêtée — résultats partiels. ') if cancelled else '')+str(len(self.results))+tr(' résultats ; ')+str(excluded)+tr(' sets exclus : inventaire absent, incomplet ou couleur non définie.'))
            self.warnings.setText('\n'.join(warnings));finish()
            if self.results:self.table.selectRow(0)
        def fail(error):
            if not self.closed:self.status.setText(error);finish()
        async_task(self,lambda progress:find_builds(self.db,source,text,ignore,copies,minimum,self.cancel,progress,excluded_stock),done,fail,lambda msg:self.status.setText(str(msg)) if not self.closed else None)
    def detail(self):
        self.clear_details();self.detail_token+=1;token=self.detail_token;index=row_index(self.table);self.parts.setRowCount(0)
        if not 0<=index<len(self.results):return
        item=dict(self.results[index]);ignore=self.last_ignore;copies=self.last_copies;self.detail_status.setText(tr('Chargement des pièces…'))
        def done(data):
            if self.closed or token!=self.detail_token:return
            rows,complete=data;self.detail_rows=list(rows);self.detail_item=item;self.detail_ignore=ignore;self.detail_copies=copies;self.parts.setRowCount(len(rows))
            self.export_missing.setEnabled(True);self.export_owned.setEnabled(True)
            self.part_visuals=[self.part_visual(row) for row in rows]
            fill_table(self.parts,[tuple(row)+(tr('Chargement…') if self.part_visuals[i] else tr('Aperçu indisponible'),) for i,row in enumerate(rows)])
            if self.thumbnails:self.thumbnails.reset()
            self.detail_status.setText(item['ref']+' — '+tr('Pièces pour ')+str(copies)+tr(' exemplaire(s). Couleurs : ')+(tr('ignorées') if ignore else tr('exactes'))+(tr(' — inventaire incomplet') if not complete else ''))
        async_task(self,lambda progress:build_details(self.db,item,ignore,copies,self.last_excluded),done,lambda error:self.detail_status.setText(error) if not self.closed and token==self.detail_token else None)
    def part_visual(self,row):
        source,ref,name,color,*_=row
        found=self.db.rows("SELECT * FROM items WHERE source=? AND kind='part' AND ref=?",(source,ref))
        if not found:return None
        item=dict(found[0]);namespace,_,code=color.partition(':');chosen=''
        if namespace==source:chosen=code
        elif source=='BL' and namespace=='RB':
            matches=[k for k in bl_palette(self.db.setting) if resolve(self.db.setting,ref,k)==code]
            if len(matches)==1:chosen=matches[0]
        item['chosen_color']=chosen;return item
    def visible_parts(self):
        return [self.part_visuals[index] if 0<=index<len(self.part_visuals) else None for index in (row_index(self.parts,i) for i in range(self.parts.rowCount()))]

    def clear_details(self):
        self.detail_rows=[];self.detail_item=None;self.part_visuals=[]
        if self.thumbnails:self.thumbnails.reset()
        self.export_missing.setEnabled(False);self.export_owned.setEnabled(False)
    def open_part(self,cell):
        index=row_index(self.parts,cell.row())
        if not self.engine or not 0<=index<len(self.detail_rows):return
        source,ref,name,color,*_=self.detail_rows[index]
        matches=self.db.rows("SELECT * FROM items WHERE source=? AND kind='part' AND ref=?",(source,ref))
        if not matches:
            QMessageBox.information(self,tr('Aperçu'),tr('Référence absente du catalogue : ')+source+' '+ref);return
        item=matches[0];chosen=''
        namespace,_,code=color.partition(':')
        if namespace==source:chosen=code
        elif source=='BL' and namespace=='RB':
            candidates=[k for k in bl_palette(self.db.setting) if resolve(self.db.setting,item['ref'],k)==code]
            if len(candidates)==1:chosen=candidates[0]
        from .ui_common import dialog,scalable
        preview=dialog(tr('Aperçu — ')+source+' '+ref,self);layout=QVBoxLayout(preview)
        caption=QLabel(name+' — '+color);caption.setWordWrap(True);layout.addWidget(caption)
        visual=QLabel(tr('Chargement…'));visual.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(visual,1)
        note=QLabel();note.setWordWrap(True);layout.addWidget(note)
        close=QPushButton(tr('Fermer'));close.clicked.connect(preview.accept);layout.addWidget(close)
        alive=[True];preview.finished.connect(lambda *_:alive.__setitem__(0,False))
        def loaded(result):
            if not alive[0]:return
            images,message=result;im=images.get('main')
            if im is None:visual.setText(tr('Aperçu indisponible'))
            else:scalable(visual,im,780,480)
            if not chosen:message=tr('Couleur non imposée à l’aperçu.')+' '+message
            note.setText(message)
        def failed(error):
            if alive[0]:visual.setText(tr('Aperçu indisponible'));note.setText(error)
        show_window(preview,self)
        async_task(preview,lambda progress:self.engine.visuals(item,chosen,True),loaded,failed)
    def export_parts(self,mode):
        if not self.detail_item:return
        filename='manquantes.csv' if mode=='missing' else 'en_stock.csv'
        path,_=QFileDialog.getSaveFileName(self,tr('Exporter les pièces'),filename,'CSV (*.csv)')
        if not path:return
        try:
            export_build_parts(path,self.detail_item,self.detail_rows,mode,self.detail_copies,self.detail_ignore)
        except Exception as error:
            from .fileio import error_message
            QMessageBox.warning(self,tr('Export impossible'),error_message(error));return
        QMessageBox.information(self,tr('Export terminé'),path)
    def open_set(self,*_):
        index=row_index(self.table)
        if self.engine and 0<=index<len(self.results):
            from .dialogs import RelationsDialog
            show_window(RelationsDialog(self.db,self.engine,self.results[index],self),self)
    def done(self,result):
        if self.set_thumbnails:self.set_thumbnails.stop()
        if self.thumbnails:self.thumbnails.stop()
        self.closed=True;self.cancel.set();self.detail_token+=1;super().done(result)
    def stock_changed(self):
        if self.busy:self.cancel.set()
        self.detail_token+=1;self.clear_details();self.parts.setRowCount(0)
        self.status.setText(tr('Le stock a changé : relance la recherche pour actualiser les résultats.'))
        self.table.setRowCount(0);self.results=[]


def export_build_parts(path,item,rows,mode,copies=1,ignore_colors=False):
    """Export the displayed snapshot; owned quantity is stock usable for this set."""
    import csv
    from .fileio import atomic_output
    if mode not in ('missing','owned'):raise ValueError('Mode inconnu')
    with atomic_output(path) as temporary:
        with temporary.open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream,delimiter=';')
            writer.writerow(['source_set','reference_set','exemplaires','couleurs_ignorees','source_piece','reference_piece','nom_piece','source_couleur','code_couleur','quantite_requise','quantite_stock_totale','quantite_disponible_pour_set','quantite_manquante','quantite_exportee'])
            for source,ref,name,color,need,have,missing in rows:
                available=min(need,have);amount=missing if mode=='missing' else available
                if amount<=0:continue
                namespace,_,code=color.partition(':')
                if color=='*':namespace='';code='*'
                writer.writerow([item['source'],item['ref'],copies,int(ignore_colors),source,ref,name,namespace,code,need,have,available,missing,amount])
