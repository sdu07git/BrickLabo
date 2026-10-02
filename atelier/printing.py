from __future__ import annotations

from PySide6.QtCore import QRectF,Qt
from PySide6.QtGui import QPainter,QPageSize,QPageLayout
from PySide6.QtPrintSupport import QPrinter,QPrintDialog,QPrintPreviewWidget
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QComboBox,QMessageBox

from .labels import page_layout
from .ui_common import pixmap,dialog


class PrintPreview(QDialog):
    def __init__(self,images,width,height,parent=None,printed=None):
        super().__init__(parent);self.setWindowTitle('Aperçu avant impression — étiquettes')
        self.setWindowFlags(self.windowFlags()|Qt.WindowType.WindowMaximizeButtonHint|Qt.WindowType.WindowMinimizeButtonHint)
        self.resize(1000,760);self.images=[pixmap(x).toImage() for x in images];self.width=width;self.height=height;self.printed=printed
        self.printer=QPrinter(QPrinter.PrinterMode.HighResolution)
        self.printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        self.printer.setPageOrientation(QPageLayout.Orientation.Portrait)
        self.printer.setFullPage(True)
        layout=QVBoxLayout(self);toolbar=QHBoxLayout();layout.addLayout(toolbar)
        self.view=QPrintPreviewWidget(self.printer,self);self.view.paintRequested.connect(self.paint_pages);layout.addWidget(self.view,1)
        previous=QPushButton('Page précédente');previous.clicked.connect(lambda:self.view.setCurrentPage(max(1,self.view.currentPage()-1)));toolbar.addWidget(previous)
        next_page=QPushButton('Page suivante');next_page.clicked.connect(lambda:self.view.setCurrentPage(min(self.view.pageCount(),self.view.currentPage()+1)));toolbar.addWidget(next_page)
        zoom=QComboBox();zoom.addItems(['Page entière','Largeur de page','100 %']);zoom.currentIndexChanged.connect(lambda i:self.view.fitInView() if i==0 else self.view.fitToWidth() if i==1 else self.view.setZoomFactor(1));toolbar.addWidget(zoom)
        toolbar.addStretch();b=QPushButton('Choisir l’imprimante et imprimer…');b.setProperty('primary',True);b.clicked.connect(self.print_dialog);toolbar.addWidget(b)
        close=QPushButton('Fermer');close.clicked.connect(self.accept);toolbar.addWidget(close)
        self.view.updatePreview()

    def paint_pages(self,printer):
        page=printer.pageLayout().fullRect(QPageLayout.Unit.Millimeter)
        try:cells=page_layout(self.width,self.height,page.width(),page.height())
        except ValueError as e:QMessageBox.warning(self,'Format de papier',str(e));return False
        dpi=printer.resolution();px=dpi/25.4
        painter=QPainter()
        if not painter.begin(printer):return False
        try:
            per_page=len(cells);pages=(len(self.images)+per_page-1)//per_page
            first=max(1,printer.fromPage() or 1);last=min(pages,printer.toPage() or pages)
            for pg in range(first-1,last):
                if pg>first-1:printer.newPage()
                for index in range(pg*per_page,min((pg+1)*per_page,len(self.images))):
                    x,y=cells[index%per_page]
                    painter.drawImage(QRectF(x*px,y*px,self.width*px,self.height*px),self.images[index])
        finally:painter.end()
        return True

    def print_dialog(self):
        chooser=QPrintDialog(self.printer,self)
        chooser.setWindowTitle('Imprimer les étiquettes')
        chooser.setOption(QPrintDialog.PrintDialogOption.PrintPageRange,True)
        chooser.setMinMax(1,self.view.pageCount())
        if chooser.exec()==QDialog.DialogCode.Accepted:
            submitted=self.paint_pages(self.printer)
            if submitted and self.printed:self.printed()
