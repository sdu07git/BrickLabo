"""Export the actual stock ledger as a Rebrickable parts list, never recount sets."""
import csv
import threading
from urllib.parse import quote,urlsplit
from .services import API
from collections import defaultdict
from pathlib import Path
from .fileio import atomic_output,error_message
from .i18n import tr
from .color_links import resolve, candidates, rb_palette, save_choice


def stock_rows(db):
    rb_parts={r['ref']:r for r in db.rows("SELECT ref,name FROM items WHERE source='RB' AND kind='part'")}
    colors=rb_palette();colors.update({str(r['id']):r for r in db.rows('SELECT * FROM colors')})
    bl_colors=db.setting('bl_colors',{})
    part_map=db.setting('export_rb_bl_parts',{});color_map=db.setting('export_rb_bl_colors',{})
    result=[];notes=[];sets=0
    contributions={(r['item_id'],str(r['color'])):int(r['quantity']) for r in db.rows("SELECT c.item_id,c.color,SUM(c.quantity) AS quantity FROM stock_set_components c JOIN stock_sets s ON s.id=c.set_entry_id GROUP BY c.item_id,c.color")}
    stock_keys=set()
    def add(item,color,quantity,trail=()):
        if quantity<=0:return
        identity=(item['source'],item['kind'],item['ref'])
        if identity in trail:
            result.append(dict(source=item['source'],ref=item['ref'],name=item.get('name',''),color=color,quantity=quantity,part='',rb_color='',reason=tr('Composition circulaire'),convertible=False));return
        if item['kind'] in ('minifig','set'):
            parts=db.components(item)
            if not parts and item['kind']=='minifig' and item['source']=='RB':parts=db.setting('rb_minifig_components_'+item['ref'],[])
            if parts:
                for part in parts:add(dict(part),str(part.get('chosen_color','')),quantity*int(part.get('chosen_quantity',1)),trail+(identity,))
                return
            result.append(dict(source=item['source'],ref=item['ref'],name=item.get('name',''),color=color,quantity=quantity,part='',rb_color='',reason=tr('Composition absente : ouvrir la mini-fig et charger ses pièces, puis relancer cet export.'),convertible=False));return
        if item['kind']!='part':
            result.append(dict(source=item['source'],ref=item['ref'],name=item.get('name',''),color=color,quantity=quantity,part='',rb_color='',reason=tr('Type non exportable dans une liste de pièces'),convertible=False));return
        ref=item['ref'];part=''
        if item['source']=='RB':part=ref
        elif item['source']=='BL' and len(part_map.get(ref,[]))==1:part=part_map[ref][0]
        elif ref in rb_parts and rb_parts[ref]['name']==item.get('name'):part=ref
        mapped=''
        if item['source'] in ('RB','BA','ALT') and color in colors:mapped=color
        elif item['source']=='BL':
            mapped=resolve(db.setting,ref,color)
        # BA/ALT may store a display/default color, never infer from RGB alone.
        result.append(dict(source=item['source'],ref=ref,name=item.get('name',''),color=color,quantity=quantity,part=part,rb_color=mapped,reason='',convertible=True))
    for item in db.rows('SELECT i.*,s.color AS stock_color,s.quantity AS stock_quantity,s.id AS stock_entry FROM stock_available s JOIN items i ON i.id=s.item_id WHERE s.quantity>0 ORDER BY i.source,i.ref,s.color'):
        if item['kind']=='set':
            sets+=1
            recorded=db.rows('SELECT item_id,color,quantity FROM stock_set_components WHERE set_entry_id=?',(abs(item['stock_entry']),))
            if not recorded:
                notes.append(tr('Set sans suivi des pièces ajoutées : ')+item['ref']+tr('. Vérifier sa présence dans le tableau des pièces du stock. Ses pièces ne sont pas ajoutées une seconde fois.'))
            else:
                expected=defaultdict(int)
                for part in db.components(item):expected[(part['id'],str(part.get('chosen_color','')))]+=int(part.get('chosen_quantity',1))*int(item['stock_quantity'])
                tracked={(part['item_id'],str(part['color'])):int(part['quantity']) for part in recorded}
                if expected and dict(expected)!=tracked:
                    notes.append(tr('Quantité ou inventaire du set différent du suivi initial : ')+item['ref']+tr('. Vérifier le set et ses pièces avant import.'))
            continue
        key=(item['id'],str(item['stock_color'] or ''));stock_keys.add(key)
        linked=contributions.get(key,0);quantity=int(item['stock_quantity'])
        if linked>quantity:notes.append(tr('Stock inférieur aux pièces suivies des sets : ')+item['source']+' '+item['ref']+' / '+key[1]+tr('. Vérifier les sets incomplets avant import.'))
        add(dict(item),key[1],max(0,quantity-linked))
    for key,quantity in contributions.items():
        if key not in stock_keys and quantity>0:notes.append(tr('Pièce de set absente du stock : identifiant ')+str(key[0])+' / '+key[1]+tr('. Vérifier les sets incomplets avant import.'))
    return result,notes,sets


def resolve_bricklink(db,refs,cancel,progress):
    api=API(db);part_map=dict(db.setting('export_rb_bl_parts',{}));color_map={}
    def pages(path):
        while path:
            if cancel.is_set():return
            data=api.rb(path)
            yield data.get('results',[])
            path=data.get('next')
            if path:
                parsed=urlsplit(path)
                if parsed.scheme!='https' or parsed.netloc!='rebrickable.com' or not parsed.path.startswith('/api/v3/lego/'):
                    raise ValueError(tr('Pagination Rebrickable invalide'))
                if cancel.wait(1.1):return
    progress(tr('Correspondances des couleurs BrickLink…'))
    for page in pages('colors/?page_size=1000'):
        for color in page:
            external=color.get('external_ids',{}).get('BrickLink',{})
            ids=external.get('ext_ids',[]) if isinstance(external,dict) else external
            for bid in ids or []:color_map.setdefault(str(bid),[]).append(str(color['id']))
    if cancel.is_set():return part_map,color_map
    db.set_setting('export_rb_bl_colors',color_map)
    for index,ref in enumerate(sorted(set(refs))):
        if cancel.wait(1.1):break
        progress(tr('Correspondance BrickLink : ')+ref+' ('+str(index+1)+'/'+str(len(set(refs)))+')')
        matches=[]
        for page in pages('parts/?bricklink_id='+quote(ref,safe='')+'&page_size=1000'):
            matches.extend(str(part['part_num']) for part in page)
        if cancel.is_set():break
        part_map[ref]=sorted(set(matches));db.set_setting('export_rb_bl_parts',part_map)
    return part_map,color_map


def stock_sets(db):
    known={r['ref'] for r in db.rows("SELECT ref FROM items WHERE source='RB' AND kind='set'")}
    rows=[]
    for item in db.rows("SELECT i.*,SUM(s.quantity) AS stock_quantity FROM stock_available s JOIN items i ON i.id=s.item_id WHERE i.kind='set' GROUP BY i.id ORDER BY i.source,i.ref"):
        ref=item['ref'];mapped=''
        if item['source']=='RB':mapped=ref
        elif item['source']=='BL':
            if ref in known:mapped=ref
            elif ref+'-1' in known:mapped=ref+'-1'
        rows.append(dict(source=item['source'],ref=ref,name=item['name'],quantity=int(item['stock_quantity']),set_num=mapped))
    return rows,known


def validate_sets(rows,known):
    grouped=defaultdict(int);issues=[]
    for row in rows:
        ref=row.get('set_num','').strip()
        if ref not in known:issues.append(row)
        elif row['quantity']>0:grouped[ref]+=row['quantity']
    return sorted(grouped.items()),issues


def write_sets_csv(path,rows):
    with atomic_output(path) as temp:
        with temp.open('w',encoding='utf-8',newline='') as out:
            writer=csv.writer(out);writer.writerow(['Set','Quantity']);writer.writerows(rows)


def validate_rows(rows,known_parts,known_colors):
    grouped=defaultdict(int);issues=[]
    for row in rows:
        part=str(row.get('part','')).strip();color=str(row.get('rb_color','')).strip();reason=row.get('reason','')
        if not row.get('convertible',True):reason=reason or tr('Type non exportable')
        elif not part or part not in known_parts:reason=tr('Référence Rebrickable absente ou inconnue du catalogue local')
        elif not color or color not in known_colors:reason=tr('Couleur Rebrickable absente ou inconnue du catalogue local')
        else:reason=''
        if reason:issues.append(dict(row,reason=reason))
        else:grouped[(part,color)]+=int(row['quantity'])
    return [(p,c,q) for (p,c),q in sorted(grouped.items()) if q>0],issues


def write_csv(path,rows):
    with atomic_output(path) as temp:
        with temp.open('w',encoding='utf-8',newline='') as out:
            writer=csv.writer(out);writer.writerow(['Part','Color','Quantity']);writer.writerows(rows)


from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QPushButton,QFileDialog,QMessageBox,QCheckBox,QPlainTextEdit,QTabWidget,QComboBox
from .ui_common import async_task


class StockExportDialog(QDialog):
    def __init__(self,db,parent=None):
        super().__init__(parent);self.db=db;self.rows=[];self.notes=[];self.closed=False;self.parts=set();self.colors=set();self.sets=[];self.known_sets=set();self.cancel=threading.Event()
        self.setWindowTitle(tr('Exporter tout mon stock vers Rebrickable'));self.resize(1100,720)
        self.setWindowFlags(self.windowFlags()|Qt.WindowType.WindowMaximizeButtonHint)
        layout=QVBoxLayout(self)
        info=QLabel(tr('Export de tout le stock, indépendamment des filtres et sélections. Deux CSV : sets possédés et pièces en vrac. Les pièces suivies des sets sont soustraites du CSV des pièces pour éviter de les compter deux fois. Les mini-figs sont décomposées si leur inventaire est disponible. Corrige les colonnes Réf. RB et Couleur RB si nécessaire ; les autres colonnes restent inchangées.'));info.setWordWrap(True);layout.addWidget(info)
        self.status=QLabel(tr('Analyse du stock…'));self.status.setWordWrap(True);layout.addWidget(self.status)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Nom'),tr('Couleur'),tr('Quantité'),tr('Réf. RB'),tr('Couleur RB'),tr('État')]);self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch);self.table.horizontalHeader().setSectionResizeMode(7,QHeaderView.ResizeMode.Stretch);self.tabs=QTabWidget();self.tabs.addTab(self.table,tr('Pièces en vrac'));layout.addWidget(self.tabs,1)
        self.set_table=QTableWidget(0,6);self.set_table.setHorizontalHeaderLabels([tr('Source'),tr('Référence'),tr('Nom'),tr('Quantité'),tr('Réf. RB'),tr('État')]);self.set_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch);self.tabs.addTab(self.set_table,tr('Sets possédés'))
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setMaximumHeight(100);layout.addWidget(self.details)
        self.partial=QCheckBox(tr('Autoriser un export partiel et accepter les points à vérifier du rapport'));layout.addWidget(self.partial)
        row=QHBoxLayout();self.convert=QPushButton(tr('Convertir BrickLink (API RB)'));self.convert.clicked.connect(self.convert_bl);self.convert.setEnabled(False);row.addWidget(self.convert);self.check=QPushButton(tr('Vérifier les corrections'));self.check.clicked.connect(self.review);row.addWidget(self.check)
        self.export=QPushButton(tr('Enregistrer les deux CSV'));self.export.clicked.connect(self.save);row.addWidget(self.export)
        link=QPushButton(tr('Ouvrir Rebrickable'));link.clicked.connect(lambda:QDesktopServices.openUrl(QUrl('https://rebrickable.com/')));row.addWidget(link)
        close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);row.addWidget(close);layout.addLayout(row)
        self.check.setEnabled(False);self.export.setEnabled(False)
        instructions=QLabel(tr('Sur Rebrickable : importer stock_sets.csv dans My Set Lists et stock_pieces.csv dans My Parts Lists, dans deux listes dédiées. Activer les deux listes pour les calculs. Ne pas conserver en parallèle une autre copie des mêmes sets ou pièces. Pour actualiser, remplacer le contenu des listes dédiées, sans ajouter le même stock plusieurs fois.'));instructions.setWordWrap(True);layout.addWidget(instructions)
        def work(progress):
            rows,notes,sets=stock_rows(db)
            return rows,notes,sets,stock_sets(db),{r['ref'] for r in db.rows("SELECT ref FROM items WHERE source='RB' AND kind='part'")},{str(r['id']) for r in db.rows('SELECT id FROM colors')}
        def done(result):
            if self.closed:return
            self.rows,self.notes,self.set_count,set_data,self.parts,self.colors=result;self.sets,self.known_sets=set_data;self.table.setRowCount(len(self.rows))
            for i,data in enumerate(self.rows):
                for c,key in enumerate(('source','ref','name','color','quantity','part','rb_color','reason')):
                    cell=QTableWidgetItem(str(data[key]));editable=c in (5,6) and data['convertible']
                    if not editable:cell.setFlags(cell.flags()&~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(i,c,cell)
            self.colors.update(rb_palette())
            for i,data in enumerate(self.rows):
                options=candidates(db.setting,data['color']) if data['source']=='BL' else []
                if len(options)>1:
                    combo=QComboBox();combo.addItem(tr('Choisir la correspondance…'),'')
                    for code in options:combo.addItem(code+' — '+rb_palette().get(code,{}).get('name',''),code)
                    combo.setCurrentIndex(max(0,combo.findData(data['rb_color'])))
                    self.table.setCellWidget(i,6,combo)
            self.set_table.setRowCount(len(self.sets))
            for i,row in enumerate(self.sets):
                for c,key in enumerate(('source','ref','name','quantity','set_num','status')):
                    cell=QTableWidgetItem(str(row.get(key,'')))
                    if c!=4:cell.setFlags(cell.flags()&~Qt.ItemFlag.ItemIsEditable)
                    self.set_table.setItem(i,c,cell)
            self.parts.update(p for values in db.setting('export_rb_bl_parts',{}).values() for p in values);self.colors.update(str(c) for values in db.setting('export_rb_bl_colors',{}).values() for c in values)
            self.convert.setEnabled(any(r['source']=='BL' and r['convertible'] for r in self.rows));self.check.setEnabled(True);self.export.setEnabled(bool(self.rows or self.sets));self.review()
        def fail(error):
            if not self.closed:self.status.setText(error)
        async_task(self,work,done,fail)
    def convert_bl(self):
        if not self.db.setting('api_rb',''):
            QMessageBox.warning(self,tr('Clé API'),tr('Renseigne ta clé Rebrickable dans les réglages API pour convertir les références et couleurs BrickLink.'));return
        self.review();refs={r['ref'] for r in self.rows if r['source']=='BL' and r['convertible'] and not r['part']}
        self.convert.setEnabled(False);self.export.setEnabled(False);self.check.setEnabled(False);self.table.setEnabled(False)
        def finish():
            self.convert.setEnabled(True);self.export.setEnabled(True);self.check.setEnabled(True);self.table.setEnabled(True)
        def done(result):
            if self.closed:return
            parts,colors=result;self.parts.update(p for values in parts.values() for p in values);self.colors.update(str(c) for values in colors.values() for c in values)
            for i,row in enumerate(self.rows):
                if row['source']!='BL' or not row['convertible']:continue
                part_options=parts.get(row['ref'],[]);mapped=resolve(self.db.setting,row['ref'],row['color']);palette=candidates(self.db.setting,row['color'])
                if not row['part'] and len(part_options)==1:self.table.item(i,5).setText(part_options[0])
                if not row['rb_color'] and mapped:self.table.item(i,6).setText(mapped)
                self.table.item(i,5).setToolTip(tr('Correspondances proposées : ')+', '.join(part_options))
                self.table.item(i,6).setToolTip(tr('Correspondances proposées : ')+', '.join(str(c) for c in palette))
            finish();self.review()
            if any(len(parts.get(r['ref'],[]))>1 for r in self.rows if r['source']=='BL'):
                self.details.appendPlainText(tr('Plusieurs correspondances pour certaines pièces : survoler la cellule Réf. RB pour voir les propositions, puis saisir la bonne référence.'))
        def fail(error):
            if self.closed:return
            finish();self.status.setText(error)
        async_task(self,lambda progress:resolve_bricklink(self.db,refs,self.cancel,progress),done,fail,lambda text:self.status.setText(str(text)) if not self.closed else None)
    def review(self):
        for i,row in enumerate(self.rows):
            row['part']=self.table.item(i,5).text().strip();combo=self.table.cellWidget(i,6)
            row['rb_color']=combo.currentData() if combo else self.table.item(i,6).text().strip()
            if combo:save_choice(self.db,row['ref'],row['color'],row['rb_color'])
            _,issues=validate_rows([row],self.parts,self.colors);self.table.item(i,7).setText(issues[0]['reason'] if issues else tr('Prêt'));self.table.item(i,7).setToolTip(issues[0]['reason'] if issues else tr('Prêt'))
        valid,issues=validate_rows(self.rows,self.parts,self.colors)
        for i,row in enumerate(self.sets):
            row['set_num']=self.set_table.item(i,4).text().strip()
            self.set_table.item(i,5).setText(tr('Prêt') if row['set_num'] in self.known_sets else tr('Référence Rebrickable à corriger'))
        valid_sets,set_issues=validate_sets(self.sets,self.known_sets)
        self.status.setText(str(len(valid))+tr(' lignes regroupées exportables, ')+str(sum(x[2] for x in valid))+tr(' pièces ; ')+str(len(issues))+tr(' lignes de pièces à corriger ; ')+str(sum(q for _,q in valid_sets))+tr(' sets exportables ; ')+str(len(set_issues))+tr(' sets à corriger.'))
        self.details.setPlainText('\n'.join(self.notes))
        return valid,issues,valid_sets,set_issues
    def save(self):
        valid,issues,sets,set_issues=self.review()
        if (issues or set_issues or self.notes) and not self.partial.isChecked():
            QMessageBox.warning(self,tr('Export à vérifier'),tr('Corrige les lignes signalées et vérifie le suivi des sets. Pour continuer malgré ces points, autorise explicitement un export partiel. Le rapport décrit les exclusions et les risques de doublons.'));return
        if not valid and not sets:QMessageBox.warning(self,tr('Export'),tr('Aucune ligne exportable.'));return
        folder=QFileDialog.getExistingDirectory(self,tr('Dossier des deux CSV Rebrickable'),str(self.db.path.parent))
        if not folder:return
        folder=Path(folder);pieces=folder/'stock_pieces.csv';set_path=folder/'stock_sets.csv';report=folder/'stock_rapport.txt'
        if any(p.exists() for p in (pieces,set_path,report)):
            if QMessageBox.question(self,tr('Remplacer les exports'),tr('Remplacer les fichiers stock_pieces.csv, stock_sets.csv et stock_rapport.txt présents dans ce dossier ?'))!=QMessageBox.StandardButton.Yes:return
        report_text=tr('Exporter les sets vers My Set Lists et les pièces vers My Parts Lists. Les pièces attribuées aux sets ont été retirées du CSV des pièces. Ne pas importer plusieurs fois les mêmes listes.')+'\n\n'
        report_text+='\n'.join(self.notes)+'\n'
        if set_issues:report_text+=tr('ATTENTION : des sets sont exclus ; leurs pièces suivies sont également exclues du CSV des pièces. Corriger les références des sets puis refaire un export complet.')+'\n'
        report_text+='\n'.join(f"SET EXCLU : {r['source']} {r['ref']} | quantité {r['quantity']}" for r in set_issues)+'\n'
        report_text+='\n'.join(f"PIÈCE EXCLUE : {r['source']} {r['ref']} | couleur {r['color']} | quantité {r['quantity']} | {r['reason']}" for r in issues)
        written=[]
        try:
            with atomic_output(report) as temp:temp.write_text(report_text,encoding='utf-8')
            written.append(report);write_csv(pieces,valid);written.append(pieces);write_sets_csv(set_path,sets);written.append(set_path)
        except Exception as error:
            QMessageBox.warning(self,tr('Export impossible'),error_message(error)+'\n'+tr('Fichiers déjà enregistrés : ')+', '.join(p.name for p in written)+tr('\nNe pas importer ce lot incomplet ; recommencer dans un dossier accessible.'));return
        QMessageBox.information(self,tr('Export terminé'),str(pieces)+'\n'+str(set_path)+'\n'+str(report)+'\n'+str(sum(r[2] for r in valid))+tr(' pièces en vrac et ')+str(sum(q for _,q in sets))+tr(' sets exportés. Le stock BrickLabo est inchangé.'))
    def done(self,result):self.closed=True;self.cancel.set();super().done(result)
