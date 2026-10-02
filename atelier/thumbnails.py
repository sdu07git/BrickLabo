from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject,QEvent,QTimer,QSize,Qt
from PySide6.QtGui import QIcon

from .ui_common import async_task,pixmap


class PartThumbnails(QObject):
    """Load visible inventory images in a worker, retaining per-row colors."""
    def __init__(self,table,db,engine,rows,column,parent):
        super().__init__(parent)
        self.table=table;self.db=db;self.engine=engine;self.rows=rows;self.column=column
        self.token=0;self.applied={};self.active=True;self.running=False;self.dirty=False
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(60)
        self.timer.timeout.connect(self.load)
        table.setIconSize(QSize(100,65))
        table.verticalScrollBar().valueChanged.connect(self.schedule)
        table.horizontalHeader().geometriesChanged.connect(self.schedule)
        table.viewport().installEventFilter(self)

    def eventFilter(self,watched,event):
        if event.type() in (QEvent.Type.Show,QEvent.Type.Resize):self.schedule()
        if event.type()==QEvent.Type.Hide:self.suspend()
        return False

    def schedule(self,*_):
        if self.active:self.timer.start()

    def reset(self):
        self.token+=1;self.applied.clear();self.schedule()

    def clear_icons(self):
        for row in list(self.applied):
            cell=self.table.item(row,self.column)
            if cell:cell.setIcon(QIcon())
        self.applied.clear()

    def invalidate(self,item=None):
        self.token+=1
        self.engine.thumbnail_cache.invalidate(item['id'] if item else None)
        for row,key in list(self.applied.items()):
            if item is None or key[0]==item['id']:self.applied.pop(row,None)
        self.schedule()

    def suspend(self):
        self.token+=1;self.timer.stop();self.clear_icons()

    def stop(self):
        self.active=False;self.suspend()

    def state(self,item):
        from .edge_style import style_for_item
        from .viewpoint import camera_for_item
        visual=self.db.visual(item['id'])
        chosen=item.get('chosen_color');color=str(chosen if chosen not in (None,'') else visual['color'])
        from .thumbnail_cache import file_stamp
        from .brickarchitect import model_ref,record_for
        info=record_for(self.db,item['ref']) if item['source']=='BA' else {}
        return (item['id'],color,visual['mode'],visual['image'],visual['color'],
                self.db.setting('default_color','#f3d55b'),self.db.setting('ldraw',''),tuple(camera_for_item(self.db,item).values()),self.db.setting('architect_model_'+str(item['id']),''),self.db.setting('architect_photo_choice_'+str(item['id']),''),self.db.setting('edge_strength',0),file_stamp(visual['image']),file_stamp(self.db.setting('ldraw','')),file_stamp(self.db.path.parent/'brickarchitect_ldraw.zip'),file_stamp(Path(__file__).resolve().parent.parent/'ressources'/'brickarchitect_ldraw.zip'),tuple(sorted(style_for_item(self.db,item).items())),'thumb-v2',item.get('image',''),model_ref(self.db,item),tuple(info.get('BL',[])),tuple(info.get('RB',[])))

    def apply(self,row,key,image,note):
        rows=self.rows()
        if not self.active or row>=len(rows) or self.state(rows[row])!=key:return
        cell=self.table.item(row,self.column)
        if cell is None:return
        if image is not None:
            cell.setIcon(QIcon(pixmap(image)));cell.setText('');cell.setToolTip('Aperçu 3D / photo')
        else:
            cell.setIcon(QIcon());cell.setText('Visuel indisponible');cell.setToolTip(note or 'Aucun modèle 3D ni photo disponible.')
        self.applied[row]=key
        if self.table.rowHeight(row)!=72:self.table.setRowHeight(row,72)

    def load(self):
        if not self.active or not self.table.isVisible() or self.table.isColumnHidden(self.column):return
        if self.running:self.dirty=True;return
        rows=self.rows()
        if not rows:return
        first=max(0,self.table.rowAt(0));last=self.table.rowAt(max(0,self.table.viewport().height()-1))
        if last<first:last=min(len(rows)-1,first+24)
        wanted=set(range(max(0,first-2),min(len(rows),last+3)))
        for row in list(self.applied):
            if row not in wanted:
                cell=self.table.item(row,self.column)
                if cell:cell.setIcon(QIcon());cell.setText('3D / photo à charger')
                self.applied.pop(row,None)
        pending=[]
        for row in sorted(wanted):
            item=dict(rows[row]);key=self.state(item)
            if self.applied.get(row)!=key:pending.append((row,item,key))
        if not pending:return
        self.token+=1;token=self.token;cache=self.engine.thumbnail_cache;generation=cache.generation
        self.running=True;self.dirty=False
        def work(progress):
            for row,item,key in pending:
                if token!=self.token or not self.active:break
                image=cache.get(key);note=''
                if image is None:
                    try:
                        color=key[1]
                        if item['kind']=='part' and key[2]=='3d' and not key[3]:
                            try:
                                if self.engine.renderer():image,_=self.engine.render_3d(item,(100,65),color)
                            except Exception as error:note=str(error)
                        if image is None:image=self.engine.photo(item,download=True,color=color)
                        if image is not None:image=cache.put(key,image,generation)
                    except Exception as error:note=str(error)
                progress((row,key,image,note))
        def delivered(result):
            if token!=self.token or not self.active:return
            self.apply(*result)
        def finished(*_):
            self.running=False
            if self.active:self.schedule()
        async_task(self,work,finished,finished,delivered)
