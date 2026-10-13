"""Editable general colour with an explicit factory reset before applying."""
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDialogButtonBox

from .i18n import tr
from .render import DEFAULT_PART_COLOR


class DefaultColorDialog(QColorDialog):
    def __init__(self, color, parent=None):
        super().__init__(QColor(color), parent)
        self.setWindowTitle(tr('Couleur par défaut des pièces en 3D'))
        # The native Windows picker cannot accommodate an application reset button.
        self.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        self.buttons = self.findChild(QDialogButtonBox)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr('Appliquer'))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('Annuler'))
        self.defaults = self.buttons.addButton(tr('Valeurs par défaut'), QDialogButtonBox.ButtonRole.ResetRole)
        self.defaults.clicked.connect(lambda: self.setCurrentColor(QColor(DEFAULT_PART_COLOR)))
