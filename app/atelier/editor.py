from __future__ import annotations

from .i18n import tr,tf

import copy
from .edge_controls import EdgeControls
from .edge_style import general_style
from .ui_common import async_task

from PySide6.QtCore import Qt,QRectF,QTimer
from PySide6.QtGui import QColor,QPen,QBrush,QPainter
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QListWidget,QPushButton,
                              QComboBox,QGraphicsView,QGraphicsScene,QGraphicsRectItem,QGraphicsItem,
                              QFormLayout,QDoubleSpinBox,QCheckBox,QLineEdit,QColorDialog,QSlider,
                              QFileDialog,QLabel,QScrollArea,QInputDialog,QMessageBox)

from .labels import default_template,render_label,template_for_item,individual_template_key,category_outline,independent_category
from .ui_common import pixmap


NAMES={'category':tr('Texte de catégorie'),'category_band':tr('Bandeau de catégorie'),'main':tr('Vue principale / photo'),'top':tr('Vue de dessus'),'side':tr('Vue de côté'),
       'reference':tr('Référence'),'references':tr('Références et dimensions'),'name':tr('Nom'),'studs':tr('Dimensions en tenons'),
       'dimensions':tr('Dimensions physiques'),'free':tr('Texte libre'),'divider':tr('Séparateur')}


class LayerHandle(QGraphicsRectItem):
    def __init__(self,editor,index,layer):
        super().__init__(0,0,layer['w']*10,layer['h']*10);self.editor=editor;self.index=index;self.resizing=False
        self.setPos(layer['x']*10,layer['y']*10)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | (QGraphicsItem.GraphicsItemFlag.ItemIsMovable if not layer.get('locked') else QGraphicsItem.GraphicsItemFlag(0)))
        self.setPen(QPen(QColor('#5a9ad1'),.6));self.setBrush(QBrush(QColor(66,133,191,12)))
        self.setZValue(100+len(editor.template['layers'])-index)
    def paint(self,painter,option,widget):
        if self.isSelected():
            painter.setPen(QPen(QColor('#2b8bda'),1.6));painter.drawRect(self.rect())
            painter.fillRect(QRectF(self.rect().width()-6,self.rect().height()-6,6,6),QColor('#2b8bda'))
    def mousePressEvent(self,event):
        self.editor.layer_list.setCurrentRow(self.index)
        self.editor.snapshot()
        self.resizing=not self.editor.template['layers'][self.index].get('locked') and event.pos().x()>self.rect().width()-9 and event.pos().y()>self.rect().height()-9
        if not self.resizing:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.resizing:self.setRect(0,0,max(5,event.pos().x()),max(5,event.pos().y()));event.accept()
        else:super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if not self.resizing:super().mouseReleaseEvent(event)
        l=self.editor.template['layers'][self.index]
        if not l.get('locked'):
            x=self.pos().x()/10;y=self.pos().y()/10
            if self.editor.snap.isChecked():x=round(x*2)/2;y=round(y*2)/2
            l.update(x=x,y=y,w=self.rect().width()/10,h=self.rect().height()/10)
            self.editor.fill_properties();QTimer.singleShot(0,self.editor.refresh_canvas)
        self.resizing=False


class LabelEditor(QDialog):
    def __init__(self,db,engine,item,parent=None,individual=False):
        super().__init__(parent);self.db=db;self.engine=engine;self.item=item or {'id':0,'ref':'3001','name':'Brick 2 x 4','category':'Brick','source':'RB','kind':'part','image':''}
        self.individual=individual;self.template_key=individual_template_key(self.item) if individual else 'template'
        self.template=template_for_item(self.item,db) if individual else independent_category(db.setting('template',default_template()));self.updating=False;self.undo_stack=[];self.redo_stack=[]
        try:self.visuals,_=engine.visuals(self.item,download=False,template=self.template)
        except Exception:self.visuals={}
        self.setWindowTitle(tr('Disposition de cette étiquette — ')+self.item['ref'] if individual else tr('Éditeur d’étiquettes'));self.setWindowFlags(self.windowFlags()|Qt.WindowType.WindowMaximizeButtonHint|Qt.WindowType.WindowMinimizeButtonHint);self.resize(1250,790)
        outer=QVBoxLayout(self);toolbar=QHBoxLayout();outer.addLayout(toolbar)
        for name,func in [(tr('Ajouter une pièce'),self.add_piece),(tr('Modèle de base'),self.reset),(tr('Charger…'),self.load),(tr('Enregistrer sous…'),self.save_as),(tr('Annuler'),self.undo),(tr('Rétablir'),self.redo)]:
            b=QPushButton(name);b.clicked.connect(func);toolbar.addWidget(b)
        toolbar.addStretch()
        split=QSplitter();outer.addWidget(split,1)
        left=QWidget();lv=QVBoxLayout(left);lv.addWidget(QLabel(tr('Calques — premier plan en haut')));self.layer_list=QListWidget();lv.addWidget(self.layer_list,1)
        self.types=QComboBox()
        for k,n in NAMES.items():self.types.addItem(n,k)
        lv.addWidget(self.types)
        for name,func in [(tr('Ajouter une information'),self.add_layer),(tr('Ajouter un texte libre'),self.add_free),(tr('Dupliquer'),self.duplicate),(tr('Monter le calque'),lambda:self.move_layer(-1)),(tr('Descendre le calque'),lambda:self.move_layer(1)),(tr('Supprimer'),self.remove_layer)]:
            b=QPushButton(name);b.clicked.connect(func);lv.addWidget(b)
        split.addWidget(left)
        center=QWidget();cv=QVBoxLayout(center);self.scene=QGraphicsScene();self.view=QGraphicsView(self.scene);self.view.setRenderHint(QPainter.RenderHint.Antialiasing);cv.addWidget(self.view,1)
        zoomrow=QHBoxLayout();self.snap=QCheckBox(tr('Grille / aimantation 0,5 mm'));zoomrow.addWidget(self.snap);zoomrow.addWidget(QLabel(tr('Zoom')));self.zoom=QSlider(Qt.Orientation.Horizontal);self.zoom.setRange(25,250);self.zoom.setValue(100);self.zoom.valueChanged.connect(self.zoom_changed);zoomrow.addWidget(self.zoom);cv.addLayout(zoomrow)
        self.small=QLabel();self.small.setAlignment(Qt.AlignmentFlag.AlignCenter);cv.addWidget(self.small);split.addWidget(center)
        right=QWidget();form=QFormLayout(right);self.props={}
        for key,label in [('x',tr('Position X (mm)')),('y',tr('Position Y (mm)')),('w',tr('Largeur (mm)')),('h',tr('Hauteur (mm)')),('font',tr('Taille du texte (mm)'))]:
            spin=QDoubleSpinBox();spin.setRange(-1000 if key in ('x','y') else .1,1000);spin.setDecimals(2);spin.setSingleStep(.5);self.props[key]=spin;form.addRow(label,spin);spin.valueChanged.connect(self.property_changed)
        self.auto_crop=QCheckBox(tr('Réduire les marges autour de la pièce'));form.addRow(self.auto_crop);self.auto_crop.toggled.connect(self.property_changed)
        image_row=QWidget();image_layout=QHBoxLayout(image_row);image_layout.setContentsMargins(0,0,0,0);self.image_zoom=QSlider(Qt.Orientation.Horizontal);self.image_zoom.setRange(50,300);self.image_zoom_value=QDoubleSpinBox();self.image_zoom_value.setRange(50,300);self.image_zoom_value.setDecimals(0);self.image_zoom_value.setSuffix(' %');image_layout.addWidget(self.image_zoom);image_layout.addWidget(self.image_zoom_value);form.addRow(tr('Zoom de cette vue'),image_row)
        self.image_zoom.valueChanged.connect(self.image_zoom_value.setValue);self.image_zoom_value.valueChanged.connect(lambda value:self.image_zoom.setValue(round(value)));self.image_zoom_value.valueChanged.connect(self.property_changed)
        self.image_zoom.setToolTip(tr('Au-delà de 100 %, les bords de la vue peuvent être coupés par sa zone. Agrandis Largeur / Hauteur pour garder la pièce entière.'))
        self.family=QLineEdit('Segoe UI');form.addRow(tr('Police ou chemin .ttf'),self.family);self.family.editingFinished.connect(self.property_changed)
        self.free=QLineEdit();form.addRow(tr('Texte libre'),self.free);self.free.editingFinished.connect(self.property_changed)
        self.align=QComboBox();self.align.addItems(['left','center','right']);form.addRow(tr('Alignement'),self.align);self.align.currentIndexChanged.connect(self.property_changed)
        self.bold=QCheckBox();self.visible=QCheckBox();self.locked=QCheckBox()
        for label,w in [(tr('Gras'),self.bold),(tr('Visible'),self.visible),(tr('Verrouillé'),self.locked)]:form.addRow(label,w);w.toggled.connect(self.property_changed)
        b=QPushButton(tr('Couleur du texte…'));b.clicked.connect(self.text_color);form.addRow(b)
        self.width=QDoubleSpinBox();self.height=QDoubleSpinBox();self.border=QDoubleSpinBox();self.margin=QDoubleSpinBox()
        for key,label,w in [('width',tr('Largeur totale (mm)'),self.width),('height',tr('Hauteur totale (mm)'),self.height),('border',tr('Contour (mm)'),self.border),('margin',tr('Repère de marge (mm)'),self.margin)]:
            w.setRange(.1,300);w.setDecimals(2);w.setValue(self.template[key]);w.valueChanged.connect(self.format_changed);form.addRow(label,w)
            if individual and key in ('width','height'):w.setEnabled(False)
        for name,func in [(tr('Contour de cette catégorie…'),self.category_color),(tr('Fond…'),lambda:self.format_color('background')),(tr('Contour par défaut…'),lambda:self.format_color('outline'))]:
            b=QPushButton(name);b.clicked.connect(func);form.addRow(b)
        self.edge_controls=None;self.edge_revision=0;self.edge_running=False;self.edge_closed=False
        self.edge_timer=QTimer(self);self.edge_timer.setSingleShot(True);self.edge_timer.setInterval(140);self.edge_timer.timeout.connect(self.render_edge_preview)
        self.edge_status=QLabel();self.edge_status.setWordWrap(True)
        if individual:
            form.addRow(QLabel(tr('Arêtes 3D de cette étiquette')))
            self.edge_controls=EdgeControls(self.template.get('edge_settings') or general_style(db),inherit=True);self.edge_controls.set_settings(self.template.get('edge_settings') or general_style(db),self.template.get('edge_settings') is None);self.edge_controls.changed.connect(self.edge_changed);form.addRow(self.edge_controls);form.addRow(self.edge_status)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(right);split.addWidget(scroll);split.setSizes([220,650,320])
        bottom=QHBoxLayout();bottom.addWidget(QLabel(tr('Déplace un champ ; tire son coin inférieur droit pour le redimensionner.')),1)
        apply=QPushButton(tr('Appliquer'));apply.clicked.connect(self.apply);bottom.addWidget(apply);close=QPushButton(tr('Fermer'));close.clicked.connect(self.reject);bottom.addWidget(close);outer.addLayout(bottom)
        self.layer_list.currentRowChanged.connect(self.fill_properties)
        from .label_pieces import bindings
        self.piece_revision=repr(bindings(self.template));self.reload_layers()

    def snapshot(self):
        self.undo_stack.append(copy.deepcopy(self.template));self.redo_stack.clear()
    def current(self):
        index=self.layer_list.currentRow();return self.template['layers'][index] if 0<=index<len(self.template['layers']) else None
    def reload_layers(self):
        row=self.layer_list.currentRow();self.updating=True;self.layer_list.clear()
        for l in self.template['layers']:self.layer_list.addItem(NAMES.get(l['type'],l['type'])+(' — '+l.get('text','') if l['type']=='free' else '')+(' — '+l['piece'].get('ref','') if l.get('piece') else ''))
        self.updating=False;self.layer_list.setCurrentRow(max(0,min(row,self.layer_list.count()-1)));self.fill_properties();self.refresh_canvas()
    def fill_properties(self,*_):
        if self.updating:return
        l=self.current()
        if not l:return
        self.updating=True
        for k,w in self.props.items():w.setValue(l.get(k,1.8))
        self.free.setText(l.get('text',''));self.family.setText(l.get('family','Segoe UI'));self.align.setCurrentText(l.get('align','left'))
        image_layer=l['type'] in ('main','top','side');self.auto_crop.setEnabled(image_layer);self.image_zoom.setEnabled(image_layer);self.image_zoom_value.setEnabled(image_layer)
        self.auto_crop.setChecked(l.get('auto_crop',l['type'] in ('top','side')));self.image_zoom_value.setValue(l.get('image_zoom',100))
        self.bold.setChecked(l.get('bold',False));self.visible.setChecked(l.get('visible',True));self.locked.setChecked(l.get('locked',False));self.updating=False
        for handle in getattr(self,'handles',[]):handle.setSelected(handle.index==self.layer_list.currentRow())
    def property_changed(self,*_):
        if self.updating:return
        l=self.current()
        if not l:return
        self.snapshot();l.update({k:w.value() for k,w in self.props.items()});l.update(text=self.free.text(),family=self.family.text(),align=self.align.currentText(),bold=self.bold.isChecked(),visible=self.visible.isChecked(),locked=self.locked.isChecked());
        if l['type'] in ('main','top','side'):l.update(auto_crop=self.auto_crop.isChecked(),image_zoom=self.image_zoom_value.value())
        self.refresh_canvas()
    def format_changed(self,*_):
        if self.updating:return
        self.snapshot()
        for k,w in [('width',self.width),('height',self.height),('border',self.border),('margin',self.margin)]:self.template[k]=w.value()
        self.refresh_canvas()
    def refresh_canvas(self):
        from .label_pieces import bindings
        revision=repr(bindings(self.template))
        if revision!=self.piece_revision:self.piece_revision=revision;self.schedule_edge_preview()
        im=render_label(self.item,self.db,self.visuals,self.template,dpi=254);self.scene.clear();self.scene.addPixmap(pixmap(im));self.scene.setSceneRect(0,0,im.width,im.height);self.handles=[]
        margin=self.template.get('margin',1)*10
        guide=self.scene.addRect(margin,margin,max(0,im.width-2*margin),max(0,im.height-2*margin),QPen(QColor('#aab2bc'),.5,Qt.PenStyle.DashLine));guide.setZValue(50)
        for i,l in enumerate(self.template['layers']):
            if l.get('visible',True):handle=LayerHandle(self,i,l);self.scene.addItem(handle);self.handles.append(handle)
        for handle in self.handles:handle.setSelected(handle.index==self.layer_list.currentRow())
        self.small.setPixmap(pixmap(im).scaledToWidth(300,Qt.TransformationMode.SmoothTransformation))
    def zoom_changed(self,value):self.view.resetTransform();self.view.scale(value/100,value/100)
    def add_piece(self):
        from .label_pieces import pick_piece,add_piece_layers
        selected=pick_piece(self.db,self.engine,self)
        if selected:self.snapshot();add_piece_layers(self.template,*selected);self.reload_layers()

    def add_layer(self):
        self.snapshot();self.template['layers'].insert(0,{'type':self.types.currentData(),'text':tr('Texte'),'x':2,'y':6,'w':25,'h':4,'font':2,'visible':True,'locked':False,'color':'#202020','align':'left'});self.reload_layers();self.layer_list.setCurrentRow(0)
    def add_free(self):self.types.setCurrentIndex(self.types.findData('free'));self.add_layer()
    def duplicate(self):
        l=self.current()
        if l:self.snapshot();self.template['layers'].insert(self.layer_list.currentRow(),copy.deepcopy(l));self.reload_layers()
    def move_layer(self,step):
        i=self.layer_list.currentRow();j=i+step
        if 0<=j<len(self.template['layers']):self.snapshot();layers=self.template['layers'];layers[i],layers[j]=layers[j],layers[i];self.reload_layers();self.layer_list.setCurrentRow(j)
    def remove_layer(self):
        i=self.layer_list.currentRow()
        if i>=0:self.snapshot();self.template['layers'].pop(i);self.reload_layers()
    def text_color(self):
        l=self.current()
        if not l:return
        c=QColorDialog.getColor(QColor(l.get('color','#202020')),self)
        if c.isValid():self.snapshot();l['color']=c.name();self.refresh_canvas()
    def category_color(self):
        c=QColorDialog.getColor(QColor(category_outline(self.item.get('category',''),self.db,self.template)),self)
        if c.isValid():self.snapshot();self.template['category_colors'][self.item['category']]=c.name();self.refresh_canvas()
    def format_color(self,key):
        c=QColorDialog.getColor(QColor(self.template[key]),self)
        if c.isValid():self.snapshot();self.template[key]=c.name();self.refresh_canvas()
    def reset(self):self.snapshot();self.template=default_template();self.sync_format();self.reload_layers()
    def sync_format(self):
        self.updating=True
        for k,w in [('width',self.width),('height',self.height),('border',self.border),('margin',self.margin)]:w.setValue(self.template[k])
        self.updating=False
        if self.edge_controls:
            self.edge_controls.set_settings(self.template.get('edge_settings') or general_style(self.db),self.template.get('edge_settings') is None);self.schedule_edge_preview()
    def undo(self):
        if self.undo_stack:self.redo_stack.append(copy.deepcopy(self.template));self.template=self.undo_stack.pop();self.sync_format();self.reload_layers()
    def redo(self):
        if self.redo_stack:self.undo_stack.append(copy.deepcopy(self.template));self.template=self.redo_stack.pop();self.sync_format();self.reload_layers()
    def save_as(self):
        import json
        path,_=QFileDialog.getSaveFileName(self,tr('Enregistrer le modèle'),'modele-etiquette.json',tr('Modèle (*.json)'))
        if path:
            from .fileio import atomic_output,error_message
            try:
                with atomic_output(path) as temp:temp.write_text(json.dumps(self.template,ensure_ascii=False,indent=2),encoding='utf-8')
            except OSError as error:QMessageBox.warning(self,tr('Export impossible'),error_message(error))
    def load(self):
        import json
        path,_=QFileDialog.getOpenFileName(self,tr('Charger un modèle'),'',tr('Modèle (*.json)'))
        if path:
            try:
                with open(path,encoding='utf-8') as f:t=json.load(f)
                if not all(k in t for k in ('width','height','layers','category_colors','outline','background')):raise ValueError(tr('Modèle invalide'))
                self.snapshot();self.template=independent_category(t);self.sync_format();self.reload_layers()
            except Exception as e:QMessageBox.warning(self,tr('Modèle'),str(e))
    def edge_changed(self):
        if self.updating:return
        self.snapshot();self.template['edge_settings']=self.edge_controls.settings()
        if self.edge_controls.inherit.isChecked():self.edge_controls.set_settings(general_style(self.db),True)
        self.schedule_edge_preview()
    def schedule_edge_preview(self):
        self.edge_revision+=1;self.edge_status.setText(tr('Actualisation des arêtes…'));self.edge_timer.start()
    def render_edge_preview(self):
        if self.edge_closed or self.edge_running:return
        revision=self.edge_revision;template=copy.deepcopy(self.template);item=dict(self.item);self.edge_running=True
        def work(progress):return self.engine.visuals(item,item.get('chosen_color'),False,template=template)
        def finish(result=None,error=None):
            self.edge_running=False
            if self.edge_closed:return
            if revision==self.edge_revision:
                if result:self.visuals,note=result;self.edge_status.setText(note);self.refresh_canvas()
                else:self.edge_status.setText(tr('Aperçu indisponible : ')+str(error))
            else:self.edge_timer.start()
        async_task(self,work,lambda result:finish(result),lambda error:finish(error=error))
    def done(self,result):self.edge_closed=True;self.edge_revision+=1;self.edge_timer.stop();super().done(result)
    def apply(self):self.db.set_setting(self.template_key,self.template);self.accept()
