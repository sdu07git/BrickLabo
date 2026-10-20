"""Internal drawer gestures; only the reviewed proposal can request a swap."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from .storage_panel import DrawerItem,WallView


class ProposalView(WallView):
    def __init__(self,scene,preview):
        super().__init__(scene);self.preview=preview;self.source=None;self.pressed=None;self.revision=None;self.dragging=False;self.hovered=None
        self.setAcceptDrops(False)

    def drawer_at(self,position):
        item=self.itemAt(position)
        while item is not None:
            if isinstance(item,DrawerItem) and self.preview.items.get(item.drawer['id']) is item:return item.drawer['id']
            item=item.parentItem()
        return None

    def eligible(self,identity):
        return not self.preview.closed and self.preview.plan is not None and any(drawer['id']==identity for drawer in self.preview.plan['available'])

    def destination(self,position):
        target=self.drawer_at(position)
        return target if target!=self.source and self.eligible(target) else None

    def highlight(self,identity):
        if identity==self.hovered:return
        for key in (self.hovered,identity):
            item=self.preview.items.get(key)
            if item is not None:item.drag_target=key==identity;item.update()
        self.hovered=identity

    def cancel_gesture(self):
        self.highlight(None);self.source=None;self.pressed=None;self.revision=None;self.dragging=False;self.viewport().unsetCursor()

    def mousePressEvent(self,event):
        self.cancel_gesture()
        if event.button()==Qt.MouseButton.LeftButton:
            identity=self.drawer_at(event.position().toPoint())
            if self.eligible(identity) and identity in (self.preview.snapshot or {}).get('assignments',{}):
                self.source=identity;self.pressed=event.position().toPoint();self.revision=self.preview.revision
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.source is None:return super().mouseMoveEvent(event)
        if not event.buttons()&Qt.MouseButton.LeftButton or self.revision!=self.preview.revision:
            self.cancel_gesture();return super().mouseMoveEvent(event)
        if not self.dragging and (event.position().toPoint()-self.pressed).manhattanLength()<QApplication.startDragDistance():return super().mouseMoveEvent(event)
        self.dragging=True;target=self.destination(event.position().toPoint());self.highlight(target)
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor if target is not None else Qt.CursorShape.ForbiddenCursor);event.accept()

    def mouseReleaseEvent(self,event):
        source=self.source;target=self.destination(event.position().toPoint()) if self.dragging and self.revision==self.preview.revision else None
        valid=event.button()==Qt.MouseButton.LeftButton and source is not None and target is not None
        self.cancel_gesture()
        # Finish the graphics-item release before rebuilding the scene.
        super().mouseReleaseEvent(event)
        if valid:self.preview.drawer_exchange_requested.emit(source,target);event.accept()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape and self.source is not None:self.cancel_gesture();event.accept()
        else:super().keyPressEvent(event)

    def contextMenuEvent(self,event):
        self.cancel_gesture();identity=self.drawer_at(event.pos())
        if identity is not None:self.preview.drawer_menu(identity,event.globalPos());event.accept()
        else:super().contextMenuEvent(event)

    def leaveEvent(self,event):self.highlight(None);super().leaveEvent(event)
    def hideEvent(self,event):self.cancel_gesture();super().hideEvent(event)
    def resizeEvent(self,event):self.cancel_gesture();super().resizeEvent(event)
