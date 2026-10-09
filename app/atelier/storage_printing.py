"""A4 storage maps: immutable layout, shared thumbnails, vector drawing.

Preview repainting, orientation changes and printing reuse images in memory.
Only an explicit PDF export writes a new file; thumbnail cache rules are shared
with tables and the storage view. No page-sized raster or Windows temp file.
"""
from io import BytesIO
from pathlib import Path
import threading

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPageLayout, QPageSize, QPen
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewWidget
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QComboBox,
    QLabel, QPushButton, QFileDialog, QMessageBox)

from . import storage_wall as store
from .fileio import atomic_output, error_message
from .i18n import tr, tf
from .thumbnails import ThumbnailContext, load_thumbnail
from .ui_common import async_task

IMAGE_BUDGET = 64 * 1024 * 1024


def identity(part):
    return part['id'], str(part['chosen_color'])


def font(painter, size, bold=False):
    value = QFont('Segoe UI'); value.setPixelSize(size)
    value.setBold(bold); painter.setFont(value)


def text(painter, rect, value, size=12, bold=False):
    font(painter, size, bold)
    label = painter.fontMetrics().elidedText(value, Qt.TextElideMode.ElideRight, max(1, int(rect.width()-4)))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)


def draw_cabinet(painter, wall, drawers, parts, images):
    """Logical drawer units in a flat front view, independent of printer DPI."""
    width, height = store.extent(wall); width = width*112-6; height = height*70-6
    painter.setPen(QPen(QColor('#444444'), 1)); painter.setBrush(QColor('white'))
    painter.drawRect(QRectF(0, 0, width, height))
    text(painter, QRectF(8, 2, width-16, 22), wall['name'], 14, True)
    for drawer in drawers:
        painter.save()
        painter.translate((drawer['col']-1)*112+12, (drawer['row']-1)*70+26)
        w, h = drawer['width']*112-6, drawer['height']*70-6
        painter.drawRect(QRectF(0, 0, w, h))
        entries = parts.get(drawer['id'], [])
        label = drawer['name'] or (entries[0]['ref'] if entries else tr('Vide'))
        if len(entries)>1 and not drawer['name']: label += ' +'+str(len(entries)-1)
        text(painter, QRectF(3, 1, w-6, 17), label, 11, True)
        shown = entries[:3]; cell = (w-8)/max(1, len(shown))
        for index, part in enumerate(shown):
            image = QImage.fromData(images.get(identity(part), b''))
            area = QRectF(4+index*cell+2, 20, cell-4, min(28, h-40)-4)
            if not image.isNull():
                scale = min(area.width()/image.width(), area.height()/image.height())
                painter.drawImage(QRectF(area.center().x()-image.width()*scale/2,
                    area.center().y()-image.height()*scale/2, image.width()*scale, image.height()*scale), image)
            text(painter, QRectF(4+index*cell, area.bottom()+1, cell, 8), part['ref'], 8)
        text(painter, QRectF(3, h-10, w-6, 8), tf('Col. {} · Tir. {}', drawer['col'], drawer['row']), 8)
        painter.restore()


class StoragePrintPreview(QDialog):
    def __init__(self, db, engine, selected_wall, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Aperçu avant impression — meubles A4')); self.resize(1050, 800)
        self.db, self.engine, self.selected_wall = db, engine, selected_wall
        self.snapshot = store.print_snapshot(db)
        self.parts = {}; self.drawers = {}
        for part in self.snapshot['parts']: self.parts.setdefault(part['drawer_id'], []).append(part)
        for drawer in self.snapshot['drawers']: self.drawers.setdefault(drawer['wall_id'], []).append(drawer)
        self.images = {}; self.completed = set(); self.image_bytes = 0; self.limited = False
        self.running = False; self.pending = False; self.closed = False; self.cancel = threading.Event()
        self.printer = self.make_printer()
        layout = QVBoxLayout(self); options = QHBoxLayout(); layout.addLayout(options)
        self.scope = QComboBox()
        for label, value in [(tr('Meuble sélectionné'), 'selected'),
                (tr('Tous les meubles — une page par meuble'), 'all'),
                (tr('Tous les meubles — vue d’ensemble'), 'overview')]: self.scope.addItem(label, value)
        self.scope.setCurrentIndex(1); options.addWidget(self.scope, 1)
        self.orientation = QComboBox(); self.orientation.addItems([tr('Portrait'), tr('Paysage')]); options.addWidget(self.orientation)
        self.progress_label = QLabel(); self.progress_label.setWordWrap(True); layout.addWidget(self.progress_label)
        self.view = QPrintPreviewWidget(self.printer, self)
        self.view.paintRequested.connect(self.paint_pages); layout.addWidget(self.view, 1)
        toolbar = QHBoxLayout(); layout.addLayout(toolbar)
        previous = QPushButton(tr('Page précédente')); previous.clicked.connect(lambda:self.view.setCurrentPage(max(1, self.view.currentPage()-1))); toolbar.addWidget(previous)
        following = QPushButton(tr('Page suivante')); following.clicked.connect(lambda:self.view.setCurrentPage(min(self.view.pageCount(), self.view.currentPage()+1))); toolbar.addWidget(following)
        fit = QPushButton(tr('Page entière')); fit.clicked.connect(self.view.fitInView); toolbar.addWidget(fit); toolbar.addStretch()
        self.pdf_button = QPushButton(tr('Exporter en PDF…')); self.pdf_button.clicked.connect(self.choose_pdf); toolbar.addWidget(self.pdf_button)
        self.print_button = QPushButton(tr('Choisir l’imprimante et imprimer…')); self.print_button.clicked.connect(self.print_dialog); toolbar.addWidget(self.print_button)
        close = QPushButton(tr('Fermer')); close.clicked.connect(self.reject); toolbar.addWidget(close)
        note = QLabel(tr('Vue de face sur A4, jusqu’à trois miniatures par tiroir. Les numéros indiquent la colonne et le tiroir. L’aperçu conserve la disposition au moment de son ouverture.')); note.setWordWrap(True); layout.addWidget(note)
        self.scope.currentIndexChanged.connect(self.prepare_images)
        self.orientation.currentIndexChanged.connect(self.update_preview)
        self.prepare_images()

    def make_printer(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4)); printer.setFullPage(True)
        return printer

    def pages(self):
        walls = self.snapshot['walls']
        if self.scope.currentData()=='selected': return [[wall] for wall in walls if wall['id']==self.selected_wall]
        if self.scope.currentData()=='overview': return [walls] if walls else []
        return [[wall] for wall in walls]

    def wanted_parts(self):
        result = {}
        for page in self.pages():
            for wall in page:
                for drawer in self.drawers.get(wall['id'], []):
                    for part in self.parts.get(drawer['id'], [])[:3]: result.setdefault(identity(part), part)
        return result

    def enable_output(self, enabled):
        self.pdf_button.setEnabled(enabled); self.print_button.setEnabled(enabled)

    def prepare_images(self, *_):
        if self.closed: return
        self.enable_output(False)
        if self.running:
            self.cancel.set(); self.pending = True; return
        self.pending = False; self.cancel = threading.Event(); cancelled = self.cancel
        wanted = self.wanted_parts(); missing = [(key, part) for key, part in wanted.items() if key not in self.completed]
        if not self.engine:
            self.completed.update(wanted); self.images_ready(); return
        if not missing or self.limited:
            self.images_ready(); return
        self.running = True; self.progress_label.setText(tr('Chargement des miniatures pour l’impression…'))
        engine = self.engine; settings = ThumbnailContext(self.db); generation = engine.thumbnail_cache.generation
        remaining = IMAGE_BUDGET-self.image_bytes
        def work(progress):
            budget = remaining
            for key, part in missing:
                if cancelled.is_set(): break
                data = b''
                try:
                    image, _ = load_thumbnail(engine, part, settings.state(part), generation)
                    if image is not None:
                        output = BytesIO(); image.save(output, format='PNG'); data = output.getvalue()
                except Exception: pass
                if cancelled.is_set(): break
                if len(data)>budget:
                    progress((key, None)); break
                budget -= len(data)
                progress((key, data))
        def delivered(result):
            if self.closed or cancelled.is_set(): return
            key, data = result; self.completed.add(key)
            if data and self.image_bytes+len(data)<=IMAGE_BUDGET:
                self.images[key] = data; self.image_bytes += len(data)
            elif data is None or data:
                self.limited = True; cancelled.set()
        def finished(*_):
            self.running = False
            if self.closed: return
            if self.pending: self.prepare_images()
            else: self.images_ready()
        async_task(self, work, finished, finished, delivered)

    def images_ready(self):
        wanted = self.wanted_parts(); loaded = sum(key in self.images for key in wanted)
        self.progress_label.setText(tf('{} / {} miniatures chargées. Les visuels indisponibles sont remplacés par leur référence.', loaded, len(wanted)))
        if self.limited: self.progress_label.setText(self.progress_label.text()+' '+tr('Limite mémoire atteinte : les références restantes sont imprimées sans miniature.'))
        self.enable_output(bool(self.pages())); self.update_preview()

    def update_preview(self, *_):
        if self.closed: return
        self.printer.setPageOrientation(QPageLayout.Orientation.Landscape if self.orientation.currentIndex() else QPageLayout.Orientation.Portrait)
        self.printer.setPrintRange(QPrinter.PrintRange.AllPages); self.printer.setFromTo(0, 0)
        self.view.updatePreview(); self.view.fitInView()

    def paint_pages(self, printer):
        pages = self.pages()
        if not pages: return False
        first, last = 1, len(pages)
        if printer.printRange()==QPrinter.PrintRange.PageRange:
            first = max(1, printer.fromPage() or 1); last = min(last, printer.toPage() or last)
        if first>last: return False
        layout = printer.pageLayout(); layout.setUnits(QPageLayout.Unit.Millimeter)
        page = layout.fullRect(QPageLayout.Unit.Millimeter); margins = layout.minimumMargins()
        left, right = max(10, margins.left()+1), max(10, margins.right()+1)
        top, bottom = max(8, margins.top()+1), max(10, margins.bottom()+1)
        available_width, available_height = page.width()-left-right, page.height()-top-bottom-22
        if min(available_width, available_height)<=0: return False
        px = printer.resolution()/25.4
        painter = QPainter()
        if not painter.begin(printer): return False
        try:
            for index in range(first-1, last):
                if index>first-1 and not printer.newPage(): return False
                painter.save(); painter.scale(px, px)
                painter.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
                painter.fillRect(QRectF(0, 0, page.width(), page.height()), QColor('white'))
                painter.setPen(QColor('#333333'))
                text(painter, QRectF(left, top, available_width, 7), tr('BrickLabo — Mon rangement'), 5, True)
                selected = pages[index]; overview = self.scope.currentData()=='overview'
                positions = {wall['id']: (wall['x']*112, wall['y']*70) if overview else (0, 0) for wall in selected}
                bounds = QRectF()
                for wall in selected:
                    x, y = positions[wall['id']]; w, h = store.extent(wall)
                    bounds = bounds.united(QRectF(x, y, w*112-6, h*70-6))
                scale = min(available_width/bounds.width(), available_height/bounds.height())
                painter.save(); painter.translate(left+(available_width-bounds.width()*scale)/2, top+12+(available_height-bounds.height()*scale)/2)
                painter.scale(scale, scale); painter.translate(-bounds.x(), -bounds.y())
                for wall in selected:
                    painter.save(); painter.translate(*positions[wall['id']])
                    draw_cabinet(painter, wall, self.drawers.get(wall['id'], []), self.parts, self.images)
                    painter.restore()
                painter.restore()
                text(painter, QRectF(left, page.height()-bottom-5, available_width, 5), tf('Page {} / {} · Colonne / Tiroir', index+1, len(pages)), 3)
                painter.restore()
            return True
        finally: painter.end()

    def export_pdf(self, destination):
        if self.running or self.pending: raise ValueError(tr('Attends la fin du chargement des miniatures.'))
        printer = self.make_printer(); printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setPageOrientation(self.printer.pageLayout().orientation())
        with atomic_output(destination) as path:
            printer.setOutputFileName(str(path))
            if not self.paint_pages(printer) or not path.exists() or path.stat().st_size<100:
                raise OSError(tr('L’impression n’a pas pu être terminée.'))

    def choose_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('Exporter les meubles en PDF'), str(Path.home()/'BrickLabo_rangement.pdf'), 'PDF (*.pdf)')
        if not path: return
        if not path.lower().endswith('.pdf'): path += '.pdf'
        try: self.export_pdf(path)
        except (OSError, ValueError) as error: QMessageBox.warning(self, tr('Export impossible'), error_message(error)); return
        self.progress_label.setText(tf('PDF enregistré : {}', path))

    def print_dialog(self):
        if self.running or self.pending: return
        dialog = QPrintDialog(self.printer, self)
        dialog.setOption(QPrintDialog.PrintDialogOption.PrintPageRange, True); dialog.setMinMax(1, len(self.pages()))
        if dialog.exec()!=QDialog.DialogCode.Accepted: return
        self.printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        self.printer.setPageOrientation(QPageLayout.Orientation.Landscape if self.orientation.currentIndex() else QPageLayout.Orientation.Portrait)
        self.printer.setFullPage(True)
        if not self.paint_pages(self.printer): QMessageBox.warning(self, tr('Impression impossible'), tr('L’impression n’a pas pu être terminée.'))

    def done(self, result):
        self.closed = True; self.cancel.set()
        super().done(result)
