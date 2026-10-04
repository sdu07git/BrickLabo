from __future__ import annotations

from .i18n import tr,tf
from .color_links import bl_palette, rb_palette, resolve, candidates, save_choice, describe

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt,Signal
from PySide6.QtGui import QDesktopServices,QColor
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QLabel,QGroupBox,QPushButton,QComboBox,
                              QFileDialog,QColorDialog,QInputDialog,QMessageBox,QHBoxLayout)

from .render import LDraw,RenderError
from .viewpoint import camera_for_item,save_camera
from .labels import render_label
from .services import Images,API,request,bricklink_photo_links,rebrickable_set_photo,rebrickable_photos
from .ui_common import async_task,scalable,image_dialog


def image_link(url):
    from urllib.parse import urlsplit
    return urlsplit(url).path.lower().endswith(('.png','.gif','.jpg','.jpeg','.webp','.bmp','.tif','.tiff'))


class VisualEngine:
    def __init__(self,db):
        from .thumbnail_cache import ThumbnailCache
        self.thumbnail_cache=ThumbnailCache(db.path.parent/'cache'/'miniatures')
        self.db=db;self.images=Images(db.path.parent/'images');self.ldraw=None;self.ldraw_path='';self.ldraw_stamp=();self.enrichment_attempts=set();self.page_attempts=set()

    def renderer(self):
        path=self.db.setting('ldraw','')
        from .thumbnail_cache import file_stamp
        stamp=(file_stamp(path),file_stamp(self.db.path.parent/'brickarchitect_ldraw.zip'),file_stamp(Path(__file__).resolve().parent.parent/'ressources'/'brickarchitect_ldraw.zip'))
        if path and (path!=self.ldraw_path or stamp!=self.ldraw_stamp):
            self.ldraw=LDraw(path,self.db.path.parent/'brickarchitect_ldraw.zip');self.ldraw_path=path;self.ldraw_stamp=stamp
        if not path:self.ldraw=None;self.ldraw_path='';self.ldraw_stamp=()
        return self.ldraw

    def color_rgb(self,item,chosen=''):
        rgb=self.db.setting('default_color','#f3d55b')
        if chosen.startswith('#'):rgb=chosen
        elif chosen:
            if item['source']=='BL':
                palette=bl_palette(self.db.setting)
                mapped=resolve(self.db.setting,item['ref'],chosen)
                native_rgb=palette.get(chosen,{}).get('rgb')
                code=str((rb_palette().get(mapped,{}).get('rgb') if len(candidates(self.db.setting,chosen))>1 else native_rgb) or rb_palette().get(mapped,{}).get('rgb') or '').lstrip('#')
                if len(code)==6 and all(c in '0123456789abcdefABCDEF' for c in code):rgb='#'+code
            else:
                r=self.db.rows('SELECT rgb FROM colors WHERE id=?',(chosen,))
                if r:rgb='#'+r[0]['rgb']
        return rgb

    def photo(self,item,download=True,color=None,_native=False):
        v=self.db.visual(item['id'])
        if item['source']=='BA':
            from .brickarchitect import native_item
            target={'photo_rb':'RB','photo_bl':'BL'}.get(v['mode'])
            errors=[]
            if v['image']:return self.images.get(v['image'],download)
            for source in ([target] if target else ['RB','BL']):
                native=native_item(self.db,item,source,preview=True)
                if not native:continue
                # Read native image sources while retaining the BrickArchitect item ID.
                try:
                    rgb_image=self.photo({**native,'id':item['id']},download,color)
                    if rgb_image is not None:
                        rgb_image.info['bricklabo_photo_source']={'source':source,'ref':native['ref']}
                        return rgb_image
                except Exception as error:errors.append(str(error))
            if errors:raise ValueError(' ; '.join(errors))
            return None
        chosen=(str(color) if color not in (None,'') else '') if _native else str(color) if color not in (None,'') else v['color']
        if v['image']:return self.images.get(v['image'],download)
        target=item['source'] if _native else {'photo_rb':'RB','photo_bl':'BL'}.get(v['mode'],item['source'])
        if target!=item['source']:
            if item['source']=='RB' and target=='BL':
                image=self.bricklink_fallback(item,download,chosen)
                if image is not None:return image
            raise ValueError(tr('La référence ')+item['ref']+tr(' appartient à ')+item['source']+tr('. Choisis sa photo native ou importe une image de la référence équivalente.'))
        native=self.db.get_item(item['id']) if target=='RB' and item['kind']=='set' else None
        url=self.db.part_image(native or item,chosen);candidates=[url] if url else [];errors=[]
        if target=='RB' and item['kind']=='set':
            import urllib.parse
            import json
            overrides=Path(__file__).resolve().parent.parent/'ressources'/'rebrickable_set_photos.json'
            if overrides.exists():
                known=json.loads(overrides.read_text(encoding='utf-8')).get(item['ref'],'')
                if known:candidates.append(known)
            ref=urllib.parse.quote(item['ref'].lower(),safe='')
            candidates += ['https://cdn.rebrickable.com/media/sets/'+ref+ext for ext in ('.jpg','.png','.jpeg','.webp','.gif')]
        if item['kind']!='box' and not url and download and ((target=='RB' and self.db.setting('api_rb','')) or (target=='BL' and self.db.setting('api_bl',{}).get('token'))):
            try:
                url=API(self.db).enrich(item)
                if url:candidates.append(url)
            except Exception as e:errors.append(str(e))
        if target=='BL':
            import urllib.parse
            ref=urllib.parse.quote(item['ref'],safe='')
            legacy={'set':'S/','minifig':'M/','part':'P/','instructions':'I/','box':'O/'}.get(item['kind'])
            if legacy:
                base='https://img.bricklink.com/ItemImage/'
                large={'set':'SL/','minifig':'ML/','part':'PL/','instructions':'IL/','box':'OL/'}[item['kind']]
                variants=[]
                if chosen.isdigit() and item['kind']=='part':
                    variants=[base+'PN/'+chosen+'/'+ref+ext for ext in ('.png','.gif','.jpg')]
                # Old catalog entries can have only a small GIF/JPEG or a large image.
                variants += [base+legacy+ref+ext for ext in ('.gif','.png','.jpg','.jpeg')]
                variants += [base+large+ref+ext for ext in ('.png','.gif','.jpg')]
                path={'set':'SN/','minifig':'MN/','part':'PN/0/','instructions':'IN/','box':'ON/'}[item['kind']]
                variants += [base+path+ref+ext for ext in ('.png','.gif','.jpg','.webp')]
                candidates=(variants[:3]+candidates+variants[3:]) if chosen.isdigit() and item['kind']=='part' else candidates+variants
        for url in dict.fromkeys(candidates):
            try:
                image=self.images.get(url,download)
                if image is not None and image.width>3 and image.height>3:
                    if target=='RB' and item['kind']=='set' and url!=(native or item).get('image'):
                        self.db.run('UPDATE items SET image=? WHERE id=?',(url,item['id']))
                    return image
            except Exception as e:
                import urllib.error
                errors.append(str(e))
                # Missing files and unsupported encodings may have another format;
                # connectivity/authentication failures are surfaced immediately.
                if isinstance(e,urllib.error.URLError) and (not isinstance(e,urllib.error.HTTPError) or e.code not in (403,404,410)):raise
        if download and target=='RB' and item['kind']=='set' and self.db.setting('api_rb','') and item['id'] not in self.enrichment_attempts:
            self.enrichment_attempts.add(item['id'])
            try:
                refreshed=API(self.db).enrich(item)
                if refreshed:
                    image=self.images.get(refreshed,True)
                    if image is not None and image.width>3 and image.height>3:return image
            except Exception as error:errors.append(str(error))
        if download and target=='RB' and item['kind']=='set' and item['id'] not in self.page_attempts:
            self.page_attempts.add(item['id'])
            try:
                import urllib.parse
                page='https://rebrickable.com/sets/'+urllib.parse.quote(item['ref'],safe='')+'/'
                published=rebrickable_set_photo(request(page,timeout=12).decode('utf-8','replace'),item['ref'],page)
                if published:
                    image=self.images.get(published,True)
                    if image is not None and image.width>3 and image.height>3:
                        self.db.run('UPDATE items SET image=? WHERE id=?',(published,item['id']))
                        return image
            except Exception as error:errors.append(tr('Page Rebrickable : ')+str(error))
        if item['source']=='RB' and target=='RB' and not _native:
            try:
                image=self.bricklink_fallback(item,download,chosen)
                if image is not None:return image
            except Exception as error:errors.append(tr('BrickLink : ')+str(error))
        if errors:raise ValueError(tr('Aucune photo accessible : ')+' ; '.join(dict.fromkeys(errors)))
        return None

    def bricklink_fallback(self,item,download=True,color=None):
        from .cross_source import bricklink_reference
        ref=bricklink_reference(self.db,item,download)
        if not ref:return None
        native={**item,'source':'BL','ref':ref,'image':'','inventory_image':''}
        chosen=str(color if color is not None else self.db.visual(item['id'])['color'])
        links=rb_palette().get(chosen,{}).get('external',{}).get('BL',[])
        native_color=links[0]['id'] if len(links)==1 else ''
        image=self.photo(native,download,native_color,_native=True)
        if image is not None:image.info['bricklabo_photo_source']={'source':'BL','ref':ref}
        return image

    def render_3d(self,item,size,color='',view='perspective',edge_strength=None,edge_settings=None,camera=None):
        renderer=self.renderer()
        if not renderer:raise RenderError(tr('LDraw non importé'))
        rgb=self.color_rgb(item,str(color or self.db.visual(item['id'])['color']))
        camera=camera_for_item(self.db,item) if camera is None else camera
        from .brickarchitect import model_ref
        ref=model_ref(self.db,item)
        from .edge_style import style_for_item
        style=edge_settings if edge_settings is not None else style_for_item(self.db,item)
        options={'edge_strength':edge_strength if edge_strength is not None else style.get('legacy',0)}
        if edge_strength is None and 'legacy' not in style:options['edge_settings']=style
        if view=='perspective' and any(camera.values()):options['camera']=camera
        return renderer.render(ref,size,rgb,view,**options)

    def visuals(self,item,color=None,download=False,template=None):
        from .edge_style import style_for_item
        style=style_for_item(self.db,item,template)
        v=self.db.visual(item['id'])
        chosen=str(color) if color not in (None,'') else v['color']
        rgb=self.color_rgb(item,chosen)
        out={};note=''
        if item['kind']=='set':
            im=self.photo(item,download,chosen)
            return {'main':im},''
        if v['mode']=='3d' and not v['image']:
            try:
                r=self.renderer()
                if r:
                    for view,key,sz in [('perspective','main',(620,420)),('top','top',(240,180)),('side','side',(240,160))]:
                        out[key],out['bounds']=self.render_3d(item,sz,chosen,view,edge_settings=style)
                else:note=tr('LDraw non importé : photo si disponible.')
            except RenderError as e:note=str(e)
        if 'main' not in out:
            try:out['main']=self.photo(item,download,chosen)
            except Exception as e:note=tr('Photo inaccessible : ')+str(e)
        provenance=out.get('main').info.get('bricklabo_photo_source') if out.get('main') is not None else None
        if provenance:
            source={'BL':'BrickLink','RB':'Rebrickable'}[provenance['source']]
            caption=tr('Photo ')+source+' : '+provenance['ref']
            if provenance['ref']!=item['ref']:caption+=tr(' — variante de ')+item['ref']
            note=(note+'\n' if note else '')+caption
        return out,note


class LabelPreview(QLabel):
    double_clicked=Signal()
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.double_clicked.emit();event.accept()
        else:super().mouseDoubleClickEvent(event)


class Preview(QWidget):
    visual_changed=Signal(object)
    def __init__(self,db,engine,parent=None):
        super().__init__(parent);self.db=db;self.engine=engine;self.item=None;self.token=0;self.image=None;self.label_image=None;self.updating=False;self.color_requests=set();self.architect_requests=set()
        layout=QVBoxLayout(self);layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)
        self.title=QLabel(tr('Aperçu'));layout.addWidget(self.title)
        self.photo=QLabel(tr('Sélectionne une ligne'));self.photo.setMinimumHeight(170);self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.photo)
        self.expand=QPushButton(tr('Agrandir l’aperçu'));self.expand.clicked.connect(self.enlarge);layout.addWidget(self.expand)
        self.camera_button=QPushButton(tr('Modifier l’angle du rendu 3D…'));self.camera_button.clicked.connect(self.edit_camera);layout.addWidget(self.camera_button)
        self.edit_one=QPushButton(tr('Modifier cette étiquette'));self.edit_one.clicked.connect(self.edit_individual);layout.addWidget(self.edit_one)
        self.reset_one=QPushButton(tr('Réinitialiser la disposition'));self.reset_one.clicked.connect(self.reset_individual);self.reset_one.setToolTip(tr('Supprime la disposition et les arêtes personnalisées de cette étiquette pour suivre le modèle général.'));layout.addWidget(self.reset_one)
        self.label_title=QLabel(tr('Aperçu de l’étiquette'));layout.addWidget(self.label_title)
        self.label_preview=LabelPreview();self.label_preview.double_clicked.connect(self.enlarge_label);self.label_preview.setToolTip(tr('Double-clic : agrandir l’étiquette'));self.label_preview.setMinimumHeight(100);self.label_preview.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.label_preview)
        self.mode=QComboBox();self.mode.addItem(tr('Rendu 3D LDraw'),'3d');self.mode.addItem(tr('Photo Rebrickable'),'photo_rb');self.mode.addItem(tr('Photo BrickLink'),'photo_bl');self.mode.addItem(tr('Image locale'),'local')
        self.mode_title=QLabel(tr('Source du visuel'));layout.addWidget(self.mode_title);layout.addWidget(self.mode)
        self.model_title=QLabel(tr('Modèle LDraw / variante'));layout.addWidget(self.model_title)
        self.model_choice=QComboBox();self.model_choice.currentIndexChanged.connect(self.model_changed);layout.addWidget(self.model_choice)
        self.photo_variant_title=QLabel(tr('Référence de la photo'));layout.addWidget(self.photo_variant_title)
        self.photo_variant=QComboBox();self.photo_variant.currentIndexChanged.connect(self.photo_variant_changed);layout.addWidget(self.photo_variant)
        self.gallery_box=QGroupBox(tr('Photos'));self.gallery_box.setMinimumHeight(155);gallery_layout=QVBoxLayout(self.gallery_box);self.gallery=QComboBox();gallery_layout.addWidget(self.gallery)
        self.find_rb_photos_button=QPushButton(tr('Rechercher les photos Rebrickable'));self.find_rb_photos_button.clicked.connect(self.find_rb_photos);gallery_layout.addWidget(self.find_rb_photos_button)
        self.find_photos_button=QPushButton(tr('Rechercher les photos BrickLink'));self.find_photos_button.clicked.connect(self.find_photos);gallery_layout.addWidget(self.find_photos_button)
        row=QHBoxLayout();b=QPushButton(tr('Ajouter un lien image'));b.clicked.connect(self.add_photo);row.addWidget(b);self.remove_photo_button=QPushButton(tr('Supprimer ce lien image'));self.remove_photo_button.clicked.connect(self.remove_photo);row.addWidget(self.remove_photo_button);gallery_layout.addLayout(row);layout.addWidget(self.gallery_box)
        self.gallery.currentIndexChanged.connect(self.choose_photo)
        self.color=QComboBox();self.color.addItem(tr('Couleur 3D par défaut'),'');self.color.addItem(tr('Choisir une couleur…'),'custom');self.color_title=QLabel(tr('Couleur du rendu 3D / palette'));layout.addWidget(self.color_title);layout.addWidget(self.color)
        self.color_link=QPushButton(tr('Correspondances des couleurs…'));self.color_link.clicked.connect(self.choose_color_link);layout.addWidget(self.color_link)
        self.available=QComboBox();self.available_title=QLabel(tr('Couleurs disponibles dans les inventaires'));layout.addWidget(self.available_title);layout.addWidget(self.available)
        self.load_colors=QPushButton(tr('Charger via l’API BrickLink (facultatif)'));self.load_colors.clicked.connect(self.fetch_colors);layout.addWidget(self.load_colors)
        self.local=QPushButton(tr('Importer une image locale'));self.local.clicked.connect(self.import_local);layout.addWidget(self.local)
        self.links=QWidget();self.links_layout=QVBoxLayout(self.links);self.links_layout.setContentsMargins(0,0,0,0);layout.addWidget(self.links)
        addlink=QPushButton(tr('Ajouter un lien de site'));addlink.clicked.connect(self.add_link);layout.addWidget(addlink)
        self.notice=QPushButton(tr('Notices et documents du set'));self.notice.clicked.connect(self.documents);layout.addWidget(self.notice)
        self.inventory_button=QPushButton(tr('Ajouter l’inventaire depuis un fichier TXT'));self.inventory_button.clicked.connect(self.import_inventory);layout.addWidget(self.inventory_button)
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note);layout.addStretch()
        self.mode.currentIndexChanged.connect(self.settings_changed);self.color.currentIndexChanged.connect(self.color_changed);self.available.currentIndexChanged.connect(self.available_changed)

    def choose_color_link(self):
        if not self.item:return
        chosen=str(self.item.get('chosen_color') or self.db.visual(self.item['id'])['color'] or '')
        if self.item['source']=='RB':
            palette=rb_palette()
            if chosen not in palette:
                labels=[k+' — '+v['name'] for k,v in palette.items()]
                label,ok=QInputDialog.getItem(self,tr('Correspondances'),tr('Couleur Rebrickable'),labels,0,False)
                if not ok:return
                chosen=label.split(' — ')[0]
            QMessageBox.information(self,tr('Correspondances'),describe(chosen));return
        palette=bl_palette(self.db.setting)
        if chosen not in palette:
            labels=[k+' — '+v['name'] for k,v in sorted(palette.items(),key=lambda x:x[1]['name'])]
            label,ok=QInputDialog.getItem(self,tr('Correspondances'),tr('Couleur BrickLink'),labels,0,False)
            if not ok:return
            chosen=label.split(' — ')[0]
        options=candidates(self.db.setting,chosen)
        if len(options)<2:
            QMessageBox.information(self,tr('Correspondances'),describe(options[0]) if options else tr('Aucune correspondance connue.'));return
        current=resolve(self.db.setting,self.item['ref'],chosen)
        labels=[tr('Non résolue — conserver le code BrickLink')]+[describe(k) for k in options]
        label,ok=QInputDialog.getItem(self,tr('Correspondance pour cette pièce'),self.item['ref']+' / BrickLink '+chosen,labels,options.index(current)+1 if current in options else 0,False)
        if ok:
            index=labels.index(label);save_choice(self.db,self.item['ref'],chosen,options[index-1] if index else '')
            self.visual_changed.emit(self.item);self.refresh()

    def import_inventory(self):
        if not self.item:return
        from .set_inventory import choose_inventory
        selected=dict(self.item)
        choose_inventory(self,self.db,selected,lambda:self.note.setText(tr('Inventaire enregistré pour ')+selected['ref']+tr(' — double-clic sur le set pour voir les pièces.')))

    def set_item(self,item):
        previous=self.item
        self.item=item;self.token+=1
        if not item or not previous or previous['id']!=item['id']:
            self.image=None;self.label_image=None;self.photo.clear();self.label_preview.clear();self.note.clear()
            self.photo.setText(tr('Chargement du visuel…') if item else tr('Sélectionne une ligne'))
        if not item:return
        v=self.db.visual(item['id']);photos=[url for url in v['links'] if image_link(url)]
        if photos:
            self.store_photos(item,photos)
            updates={'links':[url for url in v['links'] if url not in photos]}
            if not v['image']:updates.update(image=photos[-1],mode='photo_bl' if item['source']=='BL' else 'photo_rb' if item['source']=='RB' else 'local')
            self.db.save_visual(item['id'],**updates)
        self.title.setText(item['ref']+' — '+item['name']);self.title.setWordWrap(True)
        is_set=item['kind']=='set'
        self.color_link.setVisible(item['kind']=='part' and item['source'] in ('BL','RB'))
        for w in [self.label_title,self.label_preview,self.mode,self.mode_title,self.color,self.color_title,self.available,self.available_title,self.edit_one,self.reset_one]:w.setVisible(not is_set)
        self.find_rb_photos_button.setVisible(item['source'] in ('RB','BA') and not is_set and item['kind']=='part')
        self.inventory_button.setVisible(is_set and item['source']=='BL');self.notice.setVisible(is_set);self.gallery_box.setVisible(True);self.gallery_box.setTitle(tr('Photo du set') if is_set else tr('Photos de la pièce'));self.find_photos_button.setVisible(item['source'] in ('RB','BL','BA') and not is_set);self.load_colors.setVisible(item['source']=='BL' and not is_set and all(self.db.setting('api_bl',{}).get(k) for k in ('consumer_key','consumer_secret','token','token_secret')))
        self.color.setToolTip(tr('La palette permet de choisir un rendu. Elle ne garantit pas que cette pièce existe dans la couleur choisie.'))
        self.available_title.setText(tr('Couleurs connues BrickLink') if item['source']=='BL' else tr('Couleurs disponibles dans les inventaires'))
        v=self.db.visual(item['id']);self.camera_button.setVisible(not is_set);self.camera_button.setEnabled(v['mode']=='3d' and not v['image']);self.updating=True
        self.mode.setCurrentIndex(max(0,self.mode.findData(v['mode'])))
        self.model_choice.clear();self.model_title.setVisible(item['source']=='BA');self.model_choice.setVisible(item['source']=='BA')
        if item['source']=='BA':
            from .brickarchitect import record_for,model_ref
            models=record_for(self.db,item['ref']).get('models',[])
            for model in models:
                status=record_for(self.db,item['ref']).get('model_status',{}).get(model,'')
                suffix={'unofficial':tr(' · Non officiel'),'official':' · Officiel','unavailable':' · Indisponible'}.get(status,'')
                self.model_choice.addItem(model+suffix,model)
            if not models:self.model_choice.addItem(tr('Aucun modèle indiqué — photo si disponible'),'')
            self.model_choice.setCurrentIndex(max(0,self.model_choice.findData(model_ref(self.db,item))))
            self.model_choice.setEnabled(bool(models))
        self.photo_variant.clear();self.photo_variant_title.setVisible(item['source']=='BA');self.photo_variant.setVisible(item['source']=='BA')
        if item['source']=='BA':
            info=record_for(self.db,item['ref'])
            self.photo_variant.addItem(tr('Automatique — référence indiquée sous l’aperçu'),'')
            for source,label in [('RB','Rebrickable'),('BL','BrickLink')]:
                for ref in info.get(source,[]):self.photo_variant.addItem(label+' — '+ref,source+':'+ref)
            self.photo_variant.setCurrentIndex(max(0,self.photo_variant.findData(self.db.setting('architect_photo_choice_'+str(item['id']),''))))
        while self.color.count()>2:self.color.removeItem(2)
        for c in self.db.rows('SELECT name,rgb FROM colors ORDER BY name'):
            code=str(c['rgb']).lstrip('#')
            if len(code)==6:self.color.addItem(c['name']+' — rendu 3D','#'+code)
        if item['source']=='BL':
            for key,c in sorted(bl_palette(self.db.setting).items(),key=lambda pair:pair[1].get('name','')):
                # Without RGB, a catalog color still selects its native photo color ID.
                self.color.addItem(c.get('name',tr('Couleur ')+key)+' — palette BrickLink',key)
        if v['color']:
            self.color.addItem(tr('Couleur enregistrée : ')+v['color'],v['color']);self.color.setCurrentIndex(self.color.count()-1)
        else:self.color.setCurrentIndex(0)
        self.reload_available_colors()
        self.reload_gallery()
        self.updating=False
        while self.links_layout.count():
            w=self.links_layout.takeAt(0).widget()
            if w:
                w.setEnabled(False);w.hide();w.deleteLater()
        ref=item['ref']
        import urllib.parse
        rb='https://rebrickable.com/'+({'set':'sets','minifig':'minifigs'}.get(item['kind'],'parts'))+'/'+urllib.parse.quote(ref,safe='')+'/'
        typ={'part':'P','set':'S','minifig':'M'}.get(item['kind'],'P')
        bl='https://www.bricklink.com/v2/catalog/catalogitem.page?'+typ+'='+urllib.parse.quote(ref,safe='')
        native=[('Rebrickable',rb),('BrickLink',bl)] if item['source']=='RB' else [('BrickLink',bl),('Rebrickable',rb)] if item['source']=='BL' else []
        if item['source']=='BA':
            from .brickarchitect import record_for
            info=record_for(self.db,item['ref']);native=[('BrickArchitect',info.get('url','https://brickarchitect.com/parts/'+ref))]
            native += [('Rebrickable '+r,'https://rebrickable.com/parts/'+urllib.parse.quote(r,safe='')+'/') for r in info.get('RB',[])]
            native += [('BrickLink '+r,'https://www.bricklink.com/v2/catalog/catalogitem.page?P='+urllib.parse.quote(r,safe='')) for r in info.get('BL',[])]
        if is_set:native.append((tr('LEGO — notices'),'https://www.lego.com/fr-fr/service/buildinginstructions/'+ref.split('-')[0]))
        for name,url in native:
            b=QPushButton(name);b.setToolTip(url);b.clicked.connect(lambda checked=False,u=url:QDesktopServices.openUrl(QUrl(u)));self.links_layout.addWidget(b)
        for url in v['links']:
            row=QWidget();buttons=QHBoxLayout(row);buttons.setContentsMargins(0,0,0,0)
            host=urllib.parse.urlsplit(url).netloc
            b=QPushButton(host if len(host)<=22 else host[:19]+'…');b.setToolTip(url);b.clicked.connect(lambda checked=False,u=url:QDesktopServices.openUrl(QUrl(u)));buttons.addWidget(b,1)
            b=QPushButton(tr('Image'));b.setToolTip(tr('Utiliser ce lien comme image'));b.clicked.connect(lambda checked=False,u=url:self.use_link_photo(u));buttons.addWidget(b)
            b=QPushButton(tr('Supprimer'));b.clicked.connect(lambda checked=False,u=url:self.remove_link(u));buttons.addWidget(b);self.links_layout.addWidget(row)
        self.refresh()
        if item['source']=='BA':self.enrich_architect(item)
        credentials=self.db.setting('api_bl',{})
        if item['source']=='BL' and not is_set and all(credentials.get(k) for k in ('consumer_key','consumer_secret','token','token_secret')) and self.db.setting('bl_available_colors_'+item['kind']+'_'+item['ref']) is None:self.fetch_colors()

    def enrich_architect(self,item):
        from .brickarchitect import record_for,enrich_record
        if record_for(self.db,item['ref']).get('checked') or item['id'] in self.architect_requests:return
        self.architect_requests.add(item['id']);owner=dict(item)
        def done(info):
            self.engine.ldraw=None;self.engine.ldraw_path=''
            if self.item and self.item['id']==owner['id']:
                self.set_item({**self.item,**self.db.get_item(owner['id'])});self.visual_changed.emit(self.item)
        def failed(error):
            if self.item and self.item['id']==owner['id']:self.note.setText(tr('Fiche Brick Architect non vérifiée : ')+error+tr('. Le modèle local et les réglages existants sont conservés.'))
        async_task(self,lambda progress:enrich_record(self.db,owner),done,failed)

    def model_changed(self):
        if self.updating or not self.item or self.item['source']!='BA':return
        model=self.model_choice.currentData()
        if not model:return
        self.db.set_setting('architect_model_'+str(self.item['id']),model)
        self.db.save_visual(self.item['id'],mode='3d',image='')
        self.updating=True;self.mode.setCurrentIndex(self.mode.findData('3d'));self.updating=False
        self.camera_button.setEnabled(True);self.visual_changed.emit(self.item);self.refresh()

    def reload_available_colors(self):
        if not self.item:return
        self.available.blockSignals(True);self.available.clear();self.available.addItem(tr('Choisir une couleur disponible'),'')
        colors=self.db.available_colors(self.item)
        for color in colors:
            self.available.addItem(color['name']+' ('+str(color['id'])+')',str(color['id']))
            if color.get('element_codes'):self.available.setItemData(self.available.count()-1,tr('Codes élément LEGO : ')+', '.join(color['element_codes']),Qt.ItemDataRole.ToolTipRole)
        if self.item['source']=='BL' and self.item['kind']=='part':
            has_codes=bool(self.db.rows('SELECT 1 FROM bl_codes WHERE item_ref=? LIMIT 1',(self.item['ref'],)))
            self.available_title.setText(tr('Couleurs BrickLink renseignées (fichiers / cache)') if has_codes else tr('Couleurs connues BrickLink'))
            self.available.setToolTip(tr('Les codes élément LEGO renseignent certaines couleurs de cette pièce. Leur absence ne signifie pas que la pièce n’existe pas dans une couleur.'))
        if self.item['source']=='BL' and not colors:self.available.setItemText(0,tr('Disponibilité non renseignée dans les fichiers'))
        self.available.setEnabled(bool(colors))
        self.available.blockSignals(False)

    def fetch_colors(self):
        if not self.item or self.item['source']!='BL':return
        item=dict(self.item);iid=item['id']
        if iid in self.color_requests:return
        self.color_requests.add(iid);self.note.setText(tr('Chargement des couleurs connues BrickLink…'))
        def done(colors):
            self.color_requests.discard(iid)
            if not self.item or self.item['id']!=iid:return
            self.reload_available_colors();self.note.setText(str(len(colors))+tr(' couleur(s) connue(s) BrickLink enregistrée(s).'))
            if self.db.visual(iid)['color'] or item.get('chosen_color'):
                self.visual_changed.emit(self.item);self.refresh()
        def failed(error):
            self.color_requests.discard(iid)
            if self.item and self.item['id']==iid:self.note.setText(tr('Couleurs BrickLink : ')+error+tr('. Configure les quatre identifiants dans Clés API pour les charger ; les couleurs déjà en cache restent disponibles.'))
        async_task(self,lambda progress:API(self.db).bl_available_colors(item),done,failed)

    def refresh(self):
        if not self.item:return
        self.token+=1;item=dict(self.item);token=self.token
        def work(progress):
            visual,note=self.engine.visuals(item,item.get('chosen_color'),True)
            label=render_label(item,self.db,visual) if item['kind']!='set' else None
            return visual,label,note
        def done(result):
            if token!=self.token:return
            visual,label,note=result;self.image=visual.get('main');self.label_image=label
            if self.image:scalable(self.photo,self.image,310,210)
            else:self.photo.clear();self.photo.setText(tr('Visuel indisponible'))
            if label:scalable(self.label_preview,label,310,115)
            self.note.setText(note)
        def failed(error):
            if token!=self.token:return
            self.image=None;self.label_image=None;self.photo.clear();self.photo.setText(tr('Visuel indisponible'));self.label_preview.clear();self.note.setText(error)
        async_task(self,work,done,failed)

    def edit_camera(self):
        if not self.item:return
        from .camera import CameraDialog
        d=CameraDialog(self.db,self.engine,self.item,self)
        if d.exec():
            save_camera(self.db,self.item,d.camera(),d.all_models.isChecked())
            self.visual_changed.emit(None if d.all_models.isChecked() else self.item);self.refresh()

    def settings_changed(self):
        if self.updating or not self.item:return
        if self.mode.currentData()=='local':self.import_local();return
        self.db.save_visual(self.item['id'],mode=self.mode.currentData(),image='');self.camera_button.setEnabled(self.mode.currentData()=='3d');self.token+=1;self.visual_changed.emit(self.item);self.refresh()

    def color_changed(self):
        if self.updating or not self.item:return
        value=self.color.currentData()
        if value=='custom':
            c=QColorDialog.getColor(QColor(self.db.setting('default_color','#f3d55b')),self,tr('Couleur du rendu'))
            if not c.isValid():return
            value=c.name()
        self.save_color(value or '');self.refresh()

    def available_changed(self):
        if self.updating or not self.item or not self.available.currentData():return
        self.save_color(self.available.currentData());self.refresh()

    def save_color(self,value):
        self.db.save_visual(self.item['id'],color=value)
        if self.item.get('_scope') in ('stock','queue') and 'entry_id' in self.item:
            scope=self.item['_scope']
            try:self.db.run(f'UPDATE {scope} SET color=? WHERE id=?',(value,self.item['entry_id']))
            except Exception as e:QMessageBox.warning(self,tr('Couleur'),str(e));return
        if 'chosen_color' in self.item:self.item['chosen_color']=value
        self.token+=1;self.visual_changed.emit(self.item)

    def import_local(self):
        if not self.item:return
        path,_=QFileDialog.getOpenFileName(self,tr('Image locale'),'',tr('Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tif *.tiff)'))
        if not path:return
        try:
            dest=self.engine.images.preserve(path);self.db.save_visual(self.item['id'],mode='local',image=dest)
            self.camera_button.setEnabled(False);self.updating=True;self.mode.setCurrentIndex(self.mode.findData('local'));self.updating=False;self.token+=1;self.visual_changed.emit(self.item);self.refresh()
        except Exception as e:QMessageBox.warning(self,tr('Image'),str(e))

    def add_link(self):
        if not self.item:return
        url,ok=QInputDialog.getText(self,tr('Ajouter un lien'),tr('Adresse HTTPS :'))
        url=url.strip()
        if ok and url.startswith(('https://','http://')):
            if image_link(url):self.use_link_photo(url);return
            v=self.db.visual(self.item['id'])
            if url not in v['links']:v['links'].append(url)
            self.db.save_visual(self.item['id'],links=v['links']);self.set_item(self.item)

    def remove_link(self,url):
        if not self.item:return
        v=self.db.visual(self.item['id']);self.db.save_visual(self.item['id'],links=[link for link in v['links'] if link!=url]);self.set_item(self.item)

    def use_link_photo(self,url):
        if not self.item:return
        v=self.db.visual(self.item['id']);mode='photo_bl' if self.item['source']=='BL' else 'photo_rb' if self.item['source']=='RB' else 'local'
        self.db.save_visual(self.item['id'],links=[link for link in v['links'] if link!=url],mode=mode,image=url)
        self.store_photos(self.item,[url]);self.set_item(self.item);self.visual_changed.emit(self.item)

    def remove_photo(self):
        if not self.item:return
        url=self.gallery.currentData()
        if not url:return
        key='photo_choices_'+str(self.item['id']);self.db.set_setting(key,[link for link in self.db.setting(key,[]) if link!=url])
        if self.db.visual(self.item['id'])['image']==url:self.db.save_visual(self.item['id'],image='')
        self.set_item(self.item);self.visual_changed.emit(self.item)

    def enlarge(self):
        if self.image:image_dialog(tr('Aperçu — ')+self.item['ref'],self.image,self)

    def reload_gallery(self):
        self.gallery.blockSignals(True);self.gallery.clear();self.gallery.addItem(tr('Photo principale / automatique'),'')
        if self.item:
            urls=self.db.setting('photo_choices_'+str(self.item['id']),[])
            selected=self.db.visual(self.item['id'])['image']
            for i,url in enumerate(urls):self.gallery.addItem(tr('Photo ')+str(i+1)+' — '+Path(__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(url).path).name,url)
            self.gallery.setCurrentIndex(max(0,self.gallery.findData(selected)))
        self.gallery.blockSignals(False)
        self.remove_photo_button.setEnabled(bool(self.gallery.currentData()))
    def store_photos(self,item,urls):
        key='photo_choices_'+str(item['id']);known=self.db.setting(key,[])
        for url in urls:
            if url not in known:known.append(url)
        self.db.set_setting(key,known)
        if self.item and self.item['id']==item['id']:self.reload_gallery()
    def photo_variant_changed(self):
        if self.updating or not self.item or self.item['source']!='BA':return
        choice=self.photo_variant.currentData() or ''
        self.db.set_setting('architect_photo_choice_'+str(self.item['id']),choice)
        mode={'RB':'photo_rb','BL':'photo_bl'}.get(choice.partition(':')[0],'3d')
        self.db.save_visual(self.item['id'],mode=mode,image='')
        self.updating=True;self.mode.setCurrentIndex(self.mode.findData(mode));self.reload_gallery();self.updating=False
        self.camera_button.setEnabled(mode=='3d')
        self.token+=1;self.visual_changed.emit(self.item);self.refresh()

    def find_rb_photos(self):
        if not self.item or self.item['source'] not in ('RB','BA') or self.item['kind']!='part':return
        owner=dict(self.item);item=dict(owner)
        if item['source']=='BA':
            from .brickarchitect import native_item
            item=native_item(self.db,item,'RB',preview=True)
            if not item:self.note.setText(tr('Aucune correspondance Rebrickable unique pour cette variante. Ajoute un lien image direct.'));return
        self.note.setText(tr('Recherche des photos Rebrickable…'));self.find_rb_photos_button.setEnabled(False)
        def done(result):
            urls,errors=result;self.store_photos(owner,urls)
            self.find_rb_photos_button.setEnabled(True)
            if self.item and self.item['id']==owner['id']:
                message=str(len(urls))+tr(' photo(s) Rebrickable répertoriée(s).')
                if errors:message+=' Certaines sources sont inaccessibles : '+' ; '.join(errors)
                if not urls:message+=tr(' Ajoute un lien image direct ou importe une image locale.')
                self.note.setText(message)
        def fail(error):
            self.find_rb_photos_button.setEnabled(True)
            if self.item and self.item['id']==owner['id']:self.note.setText(tr('Recherche Rebrickable impossible : ')+error)
        async_task(self,lambda progress:rebrickable_photos(self.db,item),done,fail)

    def find_photos(self):
        if not self.item or self.item['source'] not in ('RB','BL','BA'):return
        owner=dict(self.item);item=dict(owner)
        if item['source']=='BA':
            from .brickarchitect import native_item
            item=native_item(self.db,item,'BL',preview=True)
            if not item:self.note.setText(tr('Aucune correspondance BrickLink unique pour la variante choisie.'));return
        self.note.setText(tr('Recherche des photos BrickLink…'))
        def work(progress):
            import urllib.parse
            typ={'set':'S','minifig':'M','part':'P'}.get(item['kind'],'P')
            page='https://www.bricklink.com/v2/catalog/catalogitem.page?'+typ+'='+urllib.parse.quote(item['ref'],safe='')
            urls=[];errors=[]
            if item.get('image'):urls.append(item['image'])
            if item['source']=='RB':
                from .cross_source import bricklink_reference
                ref=bricklink_reference(self.db,item,True)
                if not ref:raise ValueError(tr('Aucune correspondance BrickLink unique vérifiée. Ajoute un lien image direct.'));
                item.update(source='BL',ref=ref,image='')
                page='https://www.bricklink.com/v2/catalog/catalogitem.page?'+typ+'='+urllib.parse.quote(ref,safe='')
            if self.db.setting('api_bl',{}).get('token'):
                try:
                    url=API(self.db).bl_image(item)
                    if url:urls.append('https:'+url if url.startswith('//') else url)
                except Exception as e:errors.append(str(e))
            try:urls+=bricklink_photo_links(request(page,timeout=15).decode('utf-8','replace'),item)
            except Exception as e:errors.append(str(e))
            return list(dict.fromkeys(urls)),errors
        def done(result):
            urls,errors=result;self.store_photos(owner,urls)
            if self.item and self.item['id']==owner['id']:self.note.setText(str(len(urls))+tr(' photo(s) trouvée(s). ')+(' ; '.join(errors) if errors else '')+(tr(' Ajoute le lien photo si les images supplémentaires sont chargées dynamiquement.') if len(urls)<2 else ''))
        async_task(self,work,done,lambda e:self.note.setText(e) if self.item and self.item['id']==owner['id'] else None)
    def add_photo(self):
        if not self.item:return
        url,ok=QInputDialog.getText(self,tr('Photo supplémentaire'),tr('Lien direct vers une image (PNG, GIF, JPEG, WebP…) :'))
        url=url.strip()
        if ok and url.startswith(('http://','https://')):
            self.use_link_photo(url)
    def choose_photo(self):
        if self.updating or not self.item:return
        url=self.gallery.currentData() or ''
        mode='photo_bl' if self.item['source']=='BL' else 'photo_rb' if self.item['source']=='RB' else 'local'
        self.db.save_visual(self.item['id'],mode=mode,image=url);self.camera_button.setEnabled(False);self.updating=True;self.mode.setCurrentIndex(self.mode.findData(mode));self.updating=False;self.remove_photo_button.setEnabled(bool(url))
        self.token+=1;self.visual_changed.emit(self.item);self.refresh()

    def enlarge_label(self):
        if self.label_image:image_dialog(tr('Étiquette — ')+self.item['ref'],self.label_image,self)

    def edit_individual(self):
        if not self.item:return
        from .editor import LabelEditor
        if LabelEditor(self.db,self.engine,self.item,self,individual=True).exec():
            self.token+=1;self.refresh();self.visual_changed.emit(self.item)
    def reset_individual(self):
        if not self.item:return
        from .labels import individual_template_key
        self.db.set_setting(individual_template_key(self.item),{'use_general':True})
        self.token+=1;self.refresh();self.visual_changed.emit(self.item)

    def documents(self):
        from .dialogs import DocumentsDialog
        DocumentsDialog(self.db,self.item,self).exec()
