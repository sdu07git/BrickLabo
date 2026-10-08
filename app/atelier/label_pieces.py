"""Persistent catalogue bindings for additional models on a label."""
import json
from .fileio import compact_digest
from .i18n import tr

def signature(piece):return compact_digest(json.dumps(piece,sort_keys=True,ensure_ascii=False))

def find_item(db,piece):
    rows=db.rows('SELECT * FROM items WHERE source=? AND kind=? AND ref=?',(piece.get('source'),piece.get('kind','part'),piece.get('ref')))
    return rows[0] if rows else None

def bindings(template):
    return {signature(layer['piece']):layer['piece'] for layer in template.get('layers',[]) if layer.get('visible',True) and isinstance(layer.get('piece'),dict)}

def enrich(engine,template,output,download=False):
    pieces={}
    for key,piece in bindings(template).items():
        item=find_item(engine.db,piece)
        if item:
            try:visuals,note=engine.visuals(item,piece.get('color',''),download,template=template,mode=piece.get('mode'),_composition=False)
            except Exception as error:visuals={};note=str(error)
            pieces[key]={'item':item,'visuals':visuals,'note':note}
        else:pieces[key]={'item':{'ref':piece.get('ref',''),'name':piece.get('name',''),'source':piece.get('source',''),'kind':piece.get('kind','part'),'category':''},'visuals':{},'note':tr('Référence absente du catalogue local')}
    output['pieces']=pieces
    return output

def add_piece_layers(template,item,color='',mode='3d'):
    piece={k:item.get(k,'') for k in ('source','kind','ref','name')};piece.update(color=str(color),mode=mode)
    width=template['width'];height=template['height']
    layers=[{'type':'main','piece':piece,'x':width*.52,'y':height*.22,'w':width*.30,'h':height*.55,'visible':True,'locked':False},
            {'type':'reference','piece':dict(piece),'x':width*.52,'y':height*.79,'w':width*.30,'h':height*.12,'font':1.5,'color':'#202020','align':'center','visible':True,'locked':False}]
    template['layers'][0:0]=layers
    return layers

def pick_piece(db,engine,parent):
    from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,QPushButton,QMessageBox
    from .catalogue import Catalogue
    dialog=QDialog(parent);dialog.setWindowTitle(tr('Ajouter une autre pièce à l’étiquette'));dialog.resize(1000,700);layout=QVBoxLayout(dialog)
    catalogue=Catalogue(db,kind=('part','minifig'),parent=dialog);catalogue.engine=engine;catalogue.load_thumbnails();layout.addWidget(catalogue,1)
    selected=[None];catalogue.selected.connect(lambda item:selected.__setitem__(0,item))
    row=QHBoxLayout();layout.addLayout(row);row.addWidget(QLabel(tr('Couleur (code source ou #RRGGBB)')));color=QLineEdit();row.addWidget(color);mode=QComboBox();mode.addItem(tr('Rendu 3D'),'3d');mode.addItem(tr('Photo'),'photo');row.addWidget(mode)
    add=QPushButton(tr('Ajouter la pièce'));row.addWidget(add)
    def accept():
        if not selected[0]:QMessageBox.information(dialog,tr('Sélection'),tr('Sélectionne une pièce.'));return
        dialog.accept()
    add.clicked.connect(accept);close=QPushButton(tr('Annuler'));close.clicked.connect(dialog.reject);row.addWidget(close)
    return (selected[0],color.text().strip(),mode.currentData()) if dialog.exec() else None
