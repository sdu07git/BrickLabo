"""Lossless JSON drafts, including tuple keys and manually chosen destinations."""
import json
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QMessageBox,QInputDialog,QDialog
from .i18n import tr
from . import collection_workflows as work
from .collection_dialogs import SessionPicker,safe,show_window
from .storage_draft import group_key


def pack(value):
    if isinstance(value,dict):return {'dict':[[pack(k),pack(v)] for k,v in value.items()]}
    if isinstance(value,tuple):return {'tuple':[pack(v) for v in value]}
    if isinstance(value,list):return [pack(v) for v in value]
    if value is None or type(value) in (str,int,float,bool):return value
    raise ValueError(tr('Format de brouillon incompatible.'))


def unpack(value):
    if isinstance(value,list):return [unpack(v) for v in value]
    if isinstance(value,dict):
        if set(value)=={'dict'}:return {unpack(k):unpack(v) for k,v in value['dict']}
        if set(value)=={'tuple'}:return tuple(unpack(v) for v in value['tuple'])
        raise ValueError(tr('Format de brouillon incompatible.'))
    return value


def capture(dialog):
    if dialog.count_timer.isActive():dialog.rebuild(preserve_targets=True)
    if not dialog.plan:raise ValueError(tr('Prépare une proposition avant de l’enregistrer.'))
    return {'version':1,'config':dict(entries=dialog.entries,from_catalogue=dialog.from_catalogue,
        destination=dialog.destination.currentData(),category=dialog.category.currentData(),grouping=dialog.grouping.currentData(),
        criteria=[key for key,widget in dialog.criteria.items() if widget.isChecked()],
        colors=dialog.colors.isChecked(),shared=dialog.shared.isChecked(),quantities=dialog.quantities.isChecked(),reorganize=dialog.reorganize.isChecked(),
        drawer_counts=dialog.drawer_counts,category_order=dialog.category_order),
        'plan':pack(dialog.plan),'targets':[target.currentData() for target in dialog.targets]}


def save(dialog):
    name,ok=QInputDialog.getText(dialog,tr('Enregistrer le brouillon'),tr('Nom du brouillon'))
    if not ok:return
    def write():
        identity=work.save_session(dialog.db,'storage_draft',name,capture(dialog))
        dialog.summary.setText(tr('Brouillon enregistré. Tu peux le reprendre depuis Reprendre un brouillon.'));return identity
    return safe(dialog,write)


def restore(dialog,body,allow_changed=False):
    if body.get('version')!=1:raise ValueError(tr('Format de brouillon incompatible.'))
    config=body['config'];saved=unpack(body['plan']);targets=body['targets']
    if len(targets)!=len(saved['groups']):raise ValueError(tr('Format de brouillon incompatible.'))
    # Check references before changing any visible controls.
    for identity,item in saved['preview']['items'].items():
        current=dialog.db.get_item(identity)
        if current is None or any(current[key]!=item[key] for key in ('source','kind','ref')):
            raise ValueError(tr('Une référence du brouillon a changé. Prépare une nouvelle proposition.'))
    if dialog.destination.findData(config['destination'])<0:raise ValueError(tr('Un meuble du brouillon n’existe plus.'))
    widgets=[dialog.destination,dialog.category,dialog.grouping,dialog.colors,dialog.shared,dialog.quantities,dialog.reorganize,*dialog.criteria.values()]
    blockers=[QSignalBlocker(widget) for widget in widgets]
    old_indices={key:getattr(dialog,key).currentIndex() for key in ('destination','category','grouping')}
    old_checked={key:getattr(dialog,key).isChecked() for key in ('colors','shared','quantities','reorganize')}
    old_criteria={key:widget.isChecked() for key,widget in dialog.criteria.items()}
    old_attributes={key:getattr(dialog,key) for key in ('entries','from_catalogue','drawer_counts','category_order')}
    old_enabled=[widget.isEnabled() for widget in widgets]
    try:
        dialog.entries=[tuple(entry) for entry in config['entries']] if config['entries'] is not None else None
        dialog.from_catalogue=config['from_catalogue'];dialog.drawer_counts={int(k):v for k,v in config['drawer_counts'].items()};dialog.category_order=config['category_order']
        for key in ('destination','category','grouping'):
            widget=getattr(dialog,key);index=widget.findData(config[key])
            if index<0 and key=='category':widget.addItem(config[key],config[key]);index=widget.count()-1
            if index<0:raise ValueError(tr('Format de brouillon incompatible.'))
            widget.setCurrentIndex(index)
        for key in ('colors','shared','quantities','reorganize'):getattr(dialog,key).setChecked(config[key])
        for key,widget in dialog.criteria.items():widget.setChecked(key in config['criteria'])
        manual=config['grouping']=='manual';dialog.shared.setEnabled(not manual);dialog.quantities.setEnabled(not dialog.from_catalogue)
        for widget in dialog.criteria.values():widget.setEnabled(not manual)
        fresh=dialog.make_plan()
        stale=fresh['fingerprint']!=saved['fingerprint']
        if stale and not allow_changed:raise ValueError(tr('Le stock ou le rangement a changé depuis le brouillon. Reprends-le avec recalcul pour vérifier les nouvelles propositions.'))
        dialog.target_overrides={group_key(group):target for group,target in zip(saved['groups'],targets)}
        dialog.plan=saved
        dialog.rebuild(preserve_targets=True,prepared_plan=fresh if stale else saved)
        if stale:dialog.summary.setText(tr('Brouillon recalculé avec les données actuelles. Vérifie les quantités et les destinations avant d’appliquer.'))
        return stale
    except Exception:
        for key,value in old_indices.items():getattr(dialog,key).setCurrentIndex(value)
        for key,value in old_checked.items():getattr(dialog,key).setChecked(value)
        for key,value in old_criteria.items():dialog.criteria[key].setChecked(value)
        for key,value in old_attributes.items():setattr(dialog,key,value)
        for widget,enabled in zip(widgets,old_enabled):widget.setEnabled(enabled)
        raise
    finally:
        for blocker in blockers:blocker.unblock()


def load(dialog):
    def chosen(identity):
        if dialog.proposal_preview.closed:return False
        def read():
            record=work.session(dialog.db,identity,'storage_draft')
            # An explicit review choice authorizes recomputing, never applying.
            allow=QMessageBox.question(dialog,tr('Reprendre le brouillon'),tr('Recalculer avec le stock actuel si les données ont changé ? La proposition restera à vérifier avant application.'))==QMessageBox.StandardButton.Yes
            restore(dialog,record['data'],allow);return True
        return safe(dialog,read) is True
    return show_window(SessionPicker(dialog.db,'storage_draft',dialog,chosen),dialog)
