"""Brief button help after two seconds of uninterrupted mouse hover."""
import json
import logging
import re
import textwrap
import weakref
from functools import lru_cache

from PySide6.QtCore import QObject,QEvent,QTimer,Qt,QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication,QAbstractButton,QDialogButtonBox,QFormLayout,QLabel,QToolTip,QWidget
from shiboken6 import isValid

from .i18n import ENGLISH,language
from .paths import resources_directory

HOVER_DELAY_MS=2000


def _caption(value):
    return ' '.join(str(value).replace('&&','\0').replace('&','').replace('\0','&').replace('...','…').split())


@lru_cache(maxsize=1)
def descriptions():
    try:
        data=json.loads((resources_directory()/'button_help.json').read_text(encoding='utf-8'))
        if not isinstance(data,dict) or not all(isinstance(data.get(section),dict) for section in ('buttons','contexts')):raise ValueError('Invalid button help')
        if not all(isinstance(value,dict) and all(isinstance(value.get(lang),str) for lang in ('fr','en')) for section in ('buttons','contexts') for value in data[section].values()):raise ValueError('Invalid button help text')
    except (OSError,ValueError) as error:
        logging.getLogger('bricklabo').warning('Button help could not be loaded; basic help retained: %s',error)
        data={'buttons':{},'contexts':{}}
    for section in ('buttons','contexts'):
        data[section]={_caption(key):value for key,value in data[section].items()}
    return data


def _parents(button):
    parent=button.parentWidget();window=button.window()
    while parent is not None:
        yield parent
        if parent is window:break
        parent=parent.parentWidget()


def _label(button):
    label=button.text() or button.accessibleName()
    if label:return _caption(label)
    parent=button.parentWidget();layout=parent.layout() if parent else None
    if isinstance(layout,QFormLayout):
        field=layout.labelForField(button)
        if isinstance(field,QLabel):return _caption(field.text())
    return ''


@lru_cache(maxsize=1)
def _canonical_captions():
    result={_caption(key):_caption(key) for key in descriptions()['buttons']}
    # Match captions as displayed, regardless of the language at module import.
    for french,english in ENGLISH.items():
        result.setdefault(_caption(english),_caption(french))
    return result


def button_description(button):
    """Explicit tips retain priority; generated help follows changing captions."""
    lang=language();generated=button.property('bricklaboGeneratedHelp')
    explicit=button.toolTip()
    if explicit and explicit!=generated:
        if _label(button) in (_caption('Annuler la dernière action'),_caption(ENGLISH.get('Annuler la dernière action',''))):
            intro='Annule cette dernière opération : ' if lang=='fr' else 'Undoes this last operation: '
            return intro+explicit
        if re.match(r'https?://',explicit):
            return ('Ouvre cette page dans le navigateur.' if lang=='fr' else 'Opens this page in your browser.')+'\n'+explicit
        return explicit
    data=descriptions();caption=_label(button);canonical=_canonical_captions().get(caption,caption)
    for parent in _parents(button):
        for cls in type(parent).__mro__:
            value=data['contexts'].get(_caption(cls.__name__+'|'+canonical))
            if value:return value[lang]
    value=data['buttons'].get(canonical)
    if value:return value[lang]
    for parent in _parents(button):
        if isinstance(parent,QDialogButtonBox):
            role=parent.buttonRole(button)
            key={QDialogButtonBox.ButtonRole.AcceptRole:'Valider',QDialogButtonBox.ButtonRole.RejectRole:'Annuler',QDialogButtonBox.ButtonRole.ApplyRole:'Appliquer',QDialogButtonBox.ButtonRole.ResetRole:'Valeurs par défaut',QDialogButtonBox.ButtonRole.HelpRole:'Aide',QDialogButtonBox.ButtonRole.YesRole:'Oui',QDialogButtonBox.ButtonRole.NoRole:'Non'}.get(role)
            value=data['buttons'].get(key)
            if value:return value[lang]
    for parent in _parents(button):
        name=type(parent).__name__
        if name in ('CategoryTags','TagBar'):
            return ('Modifie le filtre de cette catégorie.' if lang=='fr' else 'Changes the filter for this category.')
        if name=='BackupDialog':
            return ('Inclut cette famille de données dans la sauvegarde séparée.' if lang=='fr' else 'Includes this data family in the selective backup.')
    if caption.endswith('×'):
        return ('Retire ce filtre de la recherche.' if lang=='fr' else 'Removes this search filter.')
    if caption:
        return ('Exécute la commande « '+caption+' » dans cette fenêtre.' if lang=='fr' else 'Runs the “'+caption+'” command in this window.')
    return ('Ouvre les options de ce bouton.' if lang=='fr' else 'Opens this button’s options.')


def _assign_help(button):
    text=button_description(button)
    generated=button.property('bricklaboGeneratedHelp')
    if not button.toolTip() or button.toolTip()==generated:
        button.setProperty('bricklaboGeneratedHelp',text);button.setToolTip(text)
    return text


class ButtonHelp(QObject):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.target=None;self.showing=False
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setTimerType(Qt.TimerType.PreciseTimer);self.timer.setInterval(HOVER_DELAY_MS);self.timer.timeout.connect(self.show_help)

    def current(self):
        target=self.target() if self.target else None
        return target if target is not None and isValid(target) else None

    def cancel(self):
        self.timer.stop();self.target=None
        if self.showing:QToolTip.hideText();self.showing=False

    def start(self,button):
        self.cancel();_assign_help(button);self.target=weakref.ref(button);self.timer.start()

    def show_help(self):
        button=self.current()
        if button is None or not button.isVisible():self.cancel();return
        hovered=self.app.widgetAt(QCursor.pos())
        while hovered is not None and hovered is not button:hovered=hovered.parentWidget()
        if hovered is not button:self.cancel();return
        text=_assign_help(button)
        # Wrap explanations to short lines without changing their stored tooltips.
        text='\n'.join(textwrap.fill(line,60,break_long_words=False,break_on_hyphens=False) for line in text.splitlines())
        QToolTip.showText(QCursor.pos()+QPoint(12,18),text,button,button.rect(),10000);self.showing=True

    def eventFilter(self,watched,event):
        kind=event.type()
        if isinstance(watched,QAbstractButton):
            # Polish can occur inside Qt's C++ constructors, before a button is safe to inspect.
            if kind==QEvent.Type.Show:_assign_help(watched)
            elif kind==QEvent.Type.Enter:self.start(watched)
            elif kind==QEvent.Type.ToolTip:
                # Native Qt tips may otherwise appear early, especially after another tip.
                return True
            elif kind in (QEvent.Type.Leave,QEvent.Type.MouseButtonPress,QEvent.Type.Hide,QEvent.Type.Close,QEvent.Type.DeferredDelete):
                if watched is self.current():self.cancel()
        elif kind in (QEvent.Type.Hide,QEvent.Type.Close,QEvent.Type.WindowDeactivate,QEvent.Type.DeferredDelete):
            button=self.current()
            if button is not None and isinstance(watched,QWidget) and (watched is button.window() or watched.isAncestorOf(button)):self.cancel()
        return False


def install_button_help(app=None):
    app=app or QApplication.instance()
    if app is None:return None
    manager=getattr(app,'_bricklabo_button_help',None)
    if manager is None:
        manager=ButtonHelp(app);app._bricklabo_button_help=manager;app.installEventFilter(manager)
        for widget in app.allWidgets():
            if isinstance(widget,QAbstractButton):_assign_help(widget)
    return manager
