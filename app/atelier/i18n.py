"""Local UI translations. Catalogue data and reference identifiers stay untouched."""
import json,sqlite3,sys
from pathlib import Path
from contextlib import closing
from .sqlite_file import connect

LANGUAGES={'fr':'Français','en':'English'}
_language='fr'
from .paths import application_root,documentation_directory
ROOT=application_root()
with (ROOT/'ressources'/'langues'/'en.json').open(encoding='utf-8') as stream:ENGLISH=json.load(stream)

def read_language(path=None):
 if path is None:
  executable=Path(sys.executable).resolve()
  root=executable.parent if getattr(sys,'frozen',False) or executable.stem.lower() in ('bricklabo','legoatelier') else ROOT
  path=root/'Donnees'/'atelier.sqlite'
 path=Path(path)
 if not path.is_file():return 'fr'
 try:
  with closing(connect(path,read_only=True,timeout=2)) as connection:
   row=connection.execute("SELECT value FROM settings WHERE key='ui_language'").fetchone()
  value=json.loads(row[0]) if row else 'fr'
  return value if value in LANGUAGES else 'fr'
 except (sqlite3.Error,ValueError,TypeError,OSError):return 'fr'

def set_language(code):
 global _language
 _language=code if code in LANGUAGES else 'fr'

def language():return _language

def tr(source):
 return ENGLISH.get(source,source) if _language=='en' else source

def tf(source,*values):
 return tr(source).format(*values)

def document(name):
 root=documentation_directory()
 path=root/(name+'.en.html' if _language=='en' else name+'.html')
 return path if path.is_file() else root/(name+'.html')

set_language(read_language())

def install_qt_language(app):
 from PySide6.QtCore import QLocale,QTranslator,QLibraryInfo
 QLocale.setDefault(QLocale('en_GB' if _language=='en' else 'fr_FR'))
 translator=QTranslator(app)
 if translator.load('qtbase_'+_language,QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
  app.installTranslator(translator);app._bricklabo_qt_translator=translator


def language_dialog(db,parent):
 from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QComboBox,QDialogButtonBox,QMessageBox
 from PySide6.QtCore import Qt
 dialog=QDialog(parent);dialog.setWindowTitle(tr('Langue de l’interface'));dialog.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint);dialog.resize(500,210)
 layout=QVBoxLayout(dialog);choice=QComboBox()
 for code,name in LANGUAGES.items():choice.addItem(name,code)
 choice.setCurrentIndex(max(0,choice.findData(db.setting('ui_language','fr'))));layout.addWidget(choice)
 info=QLabel(tr('Le changement de langue sera appliqué au prochain démarrage. Les noms et catégories des bases restent inchangés.'));info.setWordWrap(True);layout.addWidget(info)
 buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
 if dialog.exec()==QDialog.DialogCode.Accepted:
  db.set_setting('ui_language',choice.currentData())
  QMessageBox.information(parent,tr('Redémarrage nécessaire'),tr('Langue enregistrée. Ferme puis relance BrickLabo pour traduire toutes les fenêtres.'))
