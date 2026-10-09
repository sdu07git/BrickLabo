from __future__ import annotations

from .i18n import tr,tf

import io
import math
import os
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def font(size,bold=False,family='Segoe UI'):
    names=[Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/('segoeuib.ttf' if bold else 'segoeui.ttf'),Path('/usr/share/fonts/truetype/dejavu')/('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')]
    if family and family.lower()!='segoe ui':names.insert(0,Path(family))
    for p in names:
        if p.exists():return ImageFont.truetype(str(p),max(1,int(size)))
    return ImageFont.load_default(size=max(1,int(size)))


def default_template():
    return {'width':65,'height':23,'border':.4,'margin':1,'background':'#ffffff','transparent_background':False,'outline':'#68717a','category_colors':{},'layout_schema':2,'layers':[
        {'type':'category','text':'','x':1,'y':.4,'w':63,'h':3.8,'font':2.7,'bold':True,'color':'#ffffff','visible':True,'locked':False,'align':'left'},
        {'type':'main','x':2,'y':4.7,'w':38,'h':15.2,'visible':True,'locked':False},
        {'type':'studs','x':42,'y':4.5,'w':20,'h':3,'font':2.5,'bold':True,'color':'#202020','align':'center','visible':True,'locked':False},
        {'type':'top','x':46,'y':8,'w':12,'h':5,'visible':True,'locked':False},
        {'type':'free','text':'Vue de dessus','x':42,'y':13.1,'w':21,'h':1.8,'font':1.2,'align':'center','color':'#202020','visible':True,'locked':False},
        {'type':'side','x':48,'y':15,'w':8,'h':3.2,'visible':True,'locked':False},
        {'type':'free','text':'Vue de côté','x':42,'y':18.3,'w':21,'h':1.8,'font':1.2,'align':'center','color':'#202020','visible':True,'locked':False},
        {'type':'references','x':1,'y':20.6,'w':63,'h':1.8,'font':1.4,'bold':True,'color':'#202020','align':'center','visible':True,'locked':False},
        {'type':'category_band','x':1,'y':.4,'w':63,'h':3.8,'visible':True,'locked':False},
        {'type':'divider','x':41,'y':4.2,'w':.08,'h':15.8,'visible':True,'locked':False}]}


def category_outline(category,db,template=None):
    """Stable, unique automatic colors; explicit template choices take precedence."""
    import colorsys,json
    category=category or 'Non classée'
    template=template or db.setting('template',default_template())
    custom=template.get('category_colors',{})
    if category in custom:return custom[category]
    key='automatic_category_colors'
    palette=db.setting(key,{})
    if category in palette:return palette[category]
    # Multiple render workers may request the first palette simultaneously.
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        palette=json.loads(row['value']) if row else {}
        if category in palette:return palette[category]
        reserved={color.lower() for color in palette.values()}
        reserved.update(color.lower() for color in custom.values())
        main=c.execute("SELECT value FROM settings WHERE key='template'").fetchone()
        if main:reserved.update(color.lower() for color in json.loads(main['value']).get('category_colors',{}).values())
        names={r[0] for r in c.execute("SELECT DISTINCT category FROM items WHERE category<>''")}
        names.add(category)
        n=0
        for name in sorted(names):
            if name in palette:continue
            while True:
                # Golden-angle hues spread adjacent assignments across the wheel.
                hue=(.04+n*.618033988749895)%1
                saturation=(.64,.76,.88)[(n//12)%3]
                lightness=(.34,.40,.46)[(n//36)%3]
                n+=1
                rgb=colorsys.hls_to_rgb(hue,lightness,saturation)
                def luminance(values):
                    linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
                    return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
                while luminance(rgb)>.17:
                    lightness*=.95;rgb=colorsys.hls_to_rgb(hue,lightness,saturation)
                color='#'+''.join(f'{round(v*255):02x}' for v in rgb)
                if color not in reserved:break
            palette[name]=color;reserved.add(color)
        c.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(palette,ensure_ascii=False)))
    return palette[category]


def label_text(layer,item,db,bounds=None):
    kind=layer['type']
    if kind=='free':return layer.get('text','Texte')
    if kind=='name':return item['name']
    if kind=='category':return item.get('category') or 'Pièce'
    if kind=='reference':return item['ref']
    if kind=='studs':
        m=re.search(r'(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)(?:\s*[x×]\s*(\d+(?:\.\d+)?))?',item['name'],re.I)
        if not m:return ''
        values=[x for x in m.groups() if x]
        if len(values)==2 and item['name'].lower().startswith('brick '):values.append('1')
        return ' × '.join(values)
    if kind=='dimensions':return ' × '.join(f'{bounds[i]*.04:.1f}'.replace('.',',') for i in (0,2,1))+' cm' if bounds is not None else ''
    if kind=='references':
        parts=[('Rebrickable' if item['source']=='RB' else 'BrickLink' if item['source']=='BL' else 'Réf.')+' '+item['ref']]
        if item['source']=='RB':
            r=db.rows('SELECT DISTINCT design_id FROM elements WHERE part_num=? AND design_id<>\'\' LIMIT 1',(item['ref'],))
            if r:parts.insert(0,'LEGO '+r[0]['design_id'])
        if bounds is not None:parts.append(label_text({'type':'dimensions'},item,db,bounds))
        return '  |  '.join(parts)
    return ''


def individual_template_key(item):
    if item.get('_scope') in ('queue','stock','stock_sets','history') and item.get('entry_id'):
        return 'label_layout_'+item['_scope']+'_'+str(item['entry_id'])
    return 'label_layout_item_'+str(item['id'])


def independent_category(template):
    """Split legacy category fill from its text without changing saved coordinates."""
    import copy
    template=copy.deepcopy(template)
    if template.get('layout_schema',1)<2:
        for layer in list(template['layers']):
            if layer['type']=='category':
                template['layers'].append({k:v for k,v in {**layer,'type':'category_band'}.items() if k in ('type','x','y','w','h','visible','locked')})
        template['layout_schema']=2
    return template


def template_for_item(item,db,base=None):
    import copy
    base=base or db.setting('template',default_template())
    personal=db.setting(individual_template_key(item)) or db.setting('label_layout_item_'+str(item['id']))
    if not personal or personal.get('use_general'):return independent_category(base)
    personal=independent_category(personal)
    # Keep one physical label format for a sheet; scale layouts when global size changes.
    sx=base['width']/personal['width'];sy=base['height']/personal['height']
    for layer in personal['layers']:
        for k in ('x','w'):layer[k]*=sx
        for k in ('y','h'):layer[k]*=sy
    personal['width']=base['width'];personal['height']=base['height']
    return personal


def render_label(item,db,visuals,template=None,dpi=300):
    template=independent_category(template or template_for_item(item,db))
    scale=dpi/25.4
    w=round(template['width']*scale);h=round(template['height']*scale)
    transparent=bool(template.get('transparent_background',False))
    result=Image.new('RGBA',(w,h),(255,255,255,0) if transparent else template.get('background','#ffffff'))
    d=ImageDraw.Draw(result)
    border=category_outline(item.get('category',''),db,template)
    bw=max(1,round(template.get('border',.4)*scale))
    d.rounded_rectangle((bw/2,bw/2,w-1-bw/2,h-1-bw/2),radius=scale,outline=border,width=bw)
    bounds=visuals.get('bounds')
    for layer in reversed(template['layers']):
        if not layer.get('visible',True):continue
        active_item=item;active_visuals=visuals;active_bounds=bounds
        if layer.get('piece'):
            from .label_pieces import signature
            bound=visuals.get('pieces',{}).get(signature(layer['piece']),{});active_item=bound.get('item',dict(layer['piece'],category=''));active_visuals=bound.get('visuals',{});active_bounds=active_visuals.get('bounds')
        x=round(layer['x']*scale);y=round(layer['y']*scale);lw=max(1,round(layer['w']*scale));lh=max(1,round(layer['h']*scale))
        if layer['type']=='divider':
            d.rectangle((x,y,x+lw,y+lh),fill=border);continue
        if layer['type']=='category_band':
            d.rounded_rectangle((max(bw,x-scale*.6),max(bw,y),min(w-bw,x+lw+scale*.6),y+lh),radius=.5*scale,fill=border);continue
        if layer['type'] in ('main','top','side'):
            im=active_visuals.get(layer['type'])
            if im:
                im=im.convert('RGBA')
                if layer.get('auto_crop',layer['type'] in ('top','side')):
                    bbox=im.getchannel('A').getbbox()
                    if bbox:im=im.crop(bbox)
                im=ImageOps.contain(im,(lw,lh),Image.Resampling.LANCZOS)
                zoom=max(.5,min(3,float(layer.get('image_zoom',100))/100))
                if zoom!=1:im=im.resize((max(1,round(im.width*zoom)),max(1,round(im.height*zoom))),Image.Resampling.LANCZOS)
                tile=Image.new('RGBA',(lw,lh));tile.alpha_composite(im,((lw-im.width)//2,(lh-im.height)//2))
                result.alpha_composite(tile,(x,y))
            elif layer['type']=='main':
                d.text((x,y+lh/2),tr('Visuel indisponible'),fill='#6c7480',font=font(1.2*scale))
        else:
            text=label_text(layer,active_item,db,active_bounds)
            if not text:continue
            size=layer.get('font',1.8)*scale
            ft=font(size,layer.get('bold',False),layer.get('family','Segoe UI'))
            while size>scale*.65 and d.textbbox((0,0),text,font=ft)[2]>lw:
                size-=1;ft=font(size,layer.get('bold',False),layer.get('family','Segoe UI'))
            box=d.textbbox((0,0),text,font=ft);tw=box[2]-box[0];th=box[3]-box[1]
            tx=x if layer.get('align','left')=='left' else x+lw-tw if layer.get('align')=='right' else x+(lw-tw)/2
            # Chaque calque texte est rogné à son cadre pour ne pas déborder.
            tile=Image.new('RGBA',(lw,lh));td=ImageDraw.Draw(tile)
            td.text((tx-x,max(0,(lh-th)/2)-box[1]),text,fill=layer.get('color','#202020'),font=ft)
            result.alpha_composite(tile,(x,y))
    return result if transparent else result.convert('RGB')


def page_layout(width,height,page_w=210,page_h=297,margin=8,gap=2):
    cols=max(1,int((page_w-2*margin+gap)//(width+gap)))
    rows=max(1,int((page_h-2*margin+gap)//(height+gap)))
    if width>page_w-2*margin or height>page_h-2*margin:raise ValueError(tr('Étiquette trop grande pour la page A4'))
    return [(margin+c*(width+gap),margin+r*(height+gap)) for r in range(rows) for c in range(cols)]


def export_pdf(images,path,width,height):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.units import mm
    cells=page_layout(width,height)
    c=canvas.Canvas(str(path),pagesize=(210*mm,297*mm))
    for index,im in enumerate(images):
        if index and index%len(cells)==0:c.showPage()
        x,y=cells[index%len(cells)]
        c.drawImage(ImageReader(im),x*mm,(297-y-height)*mm,width=width*mm,height=height*mm,mask='auto')
    c.save()
