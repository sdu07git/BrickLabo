"""Import of manually downloaded BrickLink tab-separated set inventories."""

from .i18n import tr,tf
import csv,io,re,json,time
from pathlib import Path
from .data import normalize

HEADER={'Type','Item No','Item Name','Qty','Color ID','Extra?','Alternate?','Match ID','Counterpart?'}
KINDS={'P':'part','M':'minifig','S':'set','I':'instructions','O':'box','G':'gear','B':'book'}

def read_inventory(path,set_ref):
 path=Path(path)
 match=re.fullmatch(r'S-(.+)\.txt',path.name,re.I)
 if match and match.group(1).casefold()!=set_ref.casefold():raise ValueError(tr('Ce fichier concerne le set ')+match.group(1)+', pas '+set_ref+'.')
 raw=path.read_bytes()
 try:text=raw.decode('utf-8-sig')
 except UnicodeDecodeError:text=raw.decode('cp1252')
 reader=csv.DictReader((line for line in io.StringIO(text) if line.strip()),delimiter='\t')
 if not HEADER.issubset(reader.fieldnames or []):raise ValueError(tr('Inventaire BrickLink TXT non reconnu. Les colonnes Type, Item No, Qty et Color ID sont nécessaires.'))
 rows=[]
 for number,row in enumerate(reader,2):
  try:
   typ=row['Type'].strip().upper();ref=row['Item No'].strip();name=row['Item Name'].strip()
   quantity=int(row['Qty']);color=int(row['Color ID']);match_id=int(row['Match ID'])
   flags=[row[k].strip().upper() for k in ('Extra?','Alternate?','Counterpart?')]
   if typ not in KINDS or not ref or not name or quantity<1 or color<0 or match_id<0 or any(flag not in ('N','Y') for flag in flags):raise ValueError()
  except (ValueError,TypeError,KeyError):raise ValueError(tr('Ligne ')+str(number)+tr(' invalide. Aucun inventaire n’a été modifié.'))
  rows.append((typ,ref,name,quantity,str(color),*(int(flag=='Y') for flag in flags),match_id))
 if not rows:raise ValueError(tr('Inventaire vide.'))
 return rows

def import_inventory(db,item,path,progress=lambda value:None):
 if item.get('source')!='BL' or item.get('kind')!='set':raise ValueError(tr('Sélectionner un set BrickLink.'))
 rows=read_inventory(path,item['ref']);progress(tr('Enregistrement de l’inventaire…'))
 with db.connect() as c:
  current=c.execute("SELECT id FROM items WHERE id=? AND source='BL' AND kind='set'",(item['id'],)).fetchone()
  if not current:raise ValueError(tr('Le set sélectionné n’existe plus.'))
  c.execute('DELETE FROM bl_manual_inventory WHERE set_id=?',(item['id'],))
  for ordinal,(typ,ref,name,quantity,color,extra,alternate,counterpart,match_id) in enumerate(rows):
   kind=KINDS[typ]
   c.execute('INSERT INTO items(source,kind,ref,name,category,search) VALUES(?,?,?,?,?,?) ON CONFLICT(source,kind,ref) DO NOTHING',('BL',kind,ref,name,'Non classée',normalize(ref+' '+name)))
   part_id=c.execute("SELECT id FROM items WHERE source='BL' AND kind=? AND ref=?",(kind,ref)).fetchone()['id']
   c.execute('INSERT INTO bl_manual_inventory VALUES(?,?,?,?,?,?,?,?,?)',(item['id'],ordinal,part_id,color,quantity,extra,alternate,counterpart,match_id))
  # An imported manual inventory supersedes cached API components, without deleting them.
  meta={'file':Path(path).name,'date':time.strftime('%Y-%m-%d %H:%M'),'rows':len(rows),'extras':sum(row[5] for row in rows),'alternates':sum(row[6] for row in rows),'counterparts':sum(row[7] for row in rows)}
  c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('bl_manual_inventory_'+str(item['id']),json.dumps(meta,ensure_ascii=False)))
 return meta

def components(db,item):
 return db.rows("SELECT i.*,p.color AS chosen_color,p.quantity AS chosen_quantity,p.extra AS is_spare,p.match_id FROM bl_manual_inventory p JOIN items i ON i.id=p.item_id WHERE p.set_id=? AND p.alternate=0 AND p.counterpart=0 AND i.kind IN ('part','minifig','set') ORDER BY p.ordinal",(item['id'],))

def choose_inventory(parent,db,item,done):
 from PySide6.QtWidgets import QFileDialog,QMessageBox
 from .ui_common import async_task
 path,_=QFileDialog.getOpenFileName(parent,tr('Importer l’inventaire du set ')+item['ref'],'',tr('Inventaire BrickLink (*.txt)'))
 if not path:return
 try:rows=read_inventory(path,item['ref'])
 except Exception as error:QMessageBox.warning(parent,tr('Inventaire BrickLink'),str(error));return
 text=tf('Importer {1} lignes pour le set {3} ?\nL’inventaire précédent de ce set sera remplacé. Les quantités déjà présentes dans Mon stock resteront inchangées.\nLes variantes et équivalents sont conservés mais exclus des ajouts automatiques ; les pièces supplémentaires sont incluses.', None, len(rows), None, item['ref'], None)
 if QMessageBox.question(parent,tr('Inventaire BrickLink'),text)!=QMessageBox.StandardButton.Yes:return
 def success(meta):
  done();QMessageBox.information(parent,tr('Inventaire enregistré'),str(meta['rows'])+tr(' lignes enregistrées dans Donnees. Le fichier TXT peut être supprimé. Aucun accès API requis.'))
 # Capture the selected set now, so selecting another row during import cannot redirect it.
 async_task(parent,lambda progress:import_inventory(db,dict(item),path,progress),success,lambda error:QMessageBox.warning(parent,tr('Inventaire BrickLink'),error))
