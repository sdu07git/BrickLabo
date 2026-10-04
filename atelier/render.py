from __future__ import annotations

from .i18n import tr,tf

import math
import re
import zipfile
from collections import OrderedDict
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from .viewpoint import normalize_camera


_RENDER_SLOTS=threading.BoundedSemaphore(2)

class RenderError(Exception):
    pass


class LDraw:
    """Lecture récursive LDraw et rendu CPU avec tampon de profondeur."""
    def __init__(self,path,user_supplement=None):
        self.mesh_cache=OrderedDict();self.mesh_bytes=0;self.mesh_limit=32*1024*1024;self.mesh_lock=threading.RLock()
        self.path=Path(path)
        self.archive=zipfile.ZipFile(path) if self.path.is_file() else None
        self.names={n.lower():n for n in self.archive.namelist()} if self.archive else {}
        self.palette={}
        supplemental=Path(__file__).resolve().parent.parent/'ressources'/'brickarchitect_ldraw.zip'
        self.supplement=zipfile.ZipFile(supplemental) if supplemental.exists() else None
        self.supplement_names={n.lower():n for n in self.supplement.namelist()} if self.supplement else {}
        self.user_supplement=zipfile.ZipFile(user_supplement) if user_supplement and Path(user_supplement).exists() else None
        self.user_supplement_names={n.lower():n for n in self.user_supplement.namelist()} if self.user_supplement else {}
        cfg=self.read('LDConfig.ldr')
        for line in cfg.splitlines():
            m=re.search(r'!COLOUR\s+(.+?)\s+CODE\s+(\d+)\s+VALUE\s+(#[0-9A-Fa-f]{6})\s+EDGE\s+(#[0-9A-Fa-f]{6}|\d+)',line)
            if m:
                alpha=re.search(r'ALPHA\s+(\d+)',line)
                self.palette[int(m[2])]={'name':m[1].replace('_',' '),'rgb':m[3],'edge':m[4],'alpha':int(alpha[1]) if alpha else 255}

    def read(self,name):
        name=name.replace('\\','/').lower()
        candidates=[name,'ldraw/'+name,'ldraw/parts/'+name,'ldraw/p/'+name,'parts/'+name,'p/'+name]
        # Substitution des primitives courbes par leur variante 48 segments.
        if '/' not in name and name.endswith('.dat') and name!='ldconfig.ldr':
            candidates=['ldraw/p/48/'+name,'p/48/'+name]+candidates
        if self.archive:
            for n in candidates:
                if n in self.names:return self.archive.read(self.names[n]).decode('utf-8',errors='replace')
        else:
            for n in candidates:
                p=self.path/n
                if p.is_file():return p.read_text(encoding='utf-8',errors='replace')
        if self.user_supplement:
            for n in candidates:
                if n in self.user_supplement_names:return self.user_supplement.read(self.user_supplement_names[n]).decode('utf-8',errors='replace')
        if self.supplement:
            for n in candidates:
                if n in self.supplement_names:return self.supplement.read(self.supplement_names[n]).decode('utf-8',errors='replace')
        raise RenderError(tr('Fichier LDraw absent : ')+name)

    def resolve(self,ref):
        # Aucun rapprochement arbitraire entre les motifs RB et BL.
        ref=ref.lower()
        names=[ref if ref.endswith('.dat') else ref+'.dat']
        for n in names:
            try:self.read(n);return n
            except RenderError:pass
        raise RenderError(tr('Pas de modèle LDraw pour ')+ref)

    def clear_mesh_cache(self):
        with self.mesh_lock:self.mesh_cache.clear();self.mesh_bytes=0

    def mesh(self,ref):
        with self.mesh_lock:
            if ref in self.mesh_cache:
                self.mesh_cache.move_to_end(ref);return self.mesh_cache[ref][0]
            result=self.build_mesh(ref)
            cost=sum(points.nbytes+160 for group in result[:3] for points,color in group)+result[3].nbytes
            if cost<=self.mesh_limit:
                self.mesh_cache[ref]=(result,cost);self.mesh_bytes+=cost
                while self.mesh_bytes>self.mesh_limit:
                    _,(_,old)=self.mesh_cache.popitem(last=False);self.mesh_bytes-=old
            return result

    def build_mesh(self,ref):
        triangles=[];edges=[];conditional=[]
        def walk(name,mat,offset,current,stack):
            if name in stack:raise RenderError(tr('Référence LDraw cyclique'))
            text=self.read(name)
            # Si une texture est nécessaire, préférer une photo à un modèle incomplet.
            if '!TEXMAP' in text:raise RenderError(tr('Modèle texturé : utiliser une photo pour préserver le motif'))
            for raw in text.splitlines():
                t=raw.split()
                if not t or t[0] not in ('1','2','3','4','5'):continue
                typ=int(t[0]);color=int(t[1],0) if t[1].startswith('0x') else int(t[1])
                if color==16:color=current
                if typ==1:
                    a=np.array([float(x) for x in t[2:14]])
                    child=a[3:].reshape(3,3)
                    filename=' '.join(t[14:]).replace('\\','/').lower()
                    walk(filename,mat@child,mat@a[:3]+offset,color,stack|{name})
                else:
                    n={2:2,3:3,4:4,5:4}[typ]
                    points=np.array([float(x) for x in t[2:2+3*n]]).reshape(n,3)@mat.T+offset
                    if typ==2:edges.append((points,color))
                    elif typ==5:conditional.append((points,color))
                    elif typ==3:triangles.append((points,color))
                    else:
                        triangles.append((points[[0,1,2]],color));triangles.append((points[[0,2,3]],color))
        walk(self.resolve(ref),np.eye(3),np.zeros(3),16,set())
        if not triangles:raise RenderError(tr('Géométrie vide'))
        xyz=np.concatenate([t[0] for t in triangles])
        bounds=np.ptp(xyz,axis=0)
        return triangles,edges,conditional,bounds

    def render(self,ref,size=(500,330),color='#f3d55b',view='perspective',outlines=True,camera=None,edge_strength=0,edge_settings=None):
        with _RENDER_SLOTS:return self._render(ref,size,color,view,outlines,camera,edge_strength,edge_settings)

    def _render(self,ref,size=(500,330),color='#f3d55b',view='perspective',outlines=True,camera=None,edge_strength=0,edge_settings=None):
        triangles,edges,conditional,bounds=self.mesh(ref)
        width,height=size;ss=2;w=width*ss;h=height*ss
        if view=='top':
            right=np.array([1.,0,0]);up=np.array([0.,0,-1]);depth=np.array([0.,-1,0])
        elif view=='side':
            right=np.array([1.,0,0]);up=np.array([0.,-1,0]);depth=np.array([0.,0,-1])
        else:
            right=np.array([.82,0,-.57]);right/=np.linalg.norm(right)
            depth=np.array([.48,-.72,.5]);depth/=np.linalg.norm(depth)
            up=np.cross(right,depth);up/=np.linalg.norm(up)
            right=np.cross(depth,up)
        if view not in ('top','side') and camera is not None:
            angles=normalize_camera(camera)
            def rotate(vector,axis,degrees):
                if not degrees:return vector
                angle=math.radians(degrees);axis=axis/np.linalg.norm(axis)
                return vector*math.cos(angle)+np.cross(axis,vector)*math.sin(angle)+axis*(axis@vector)*(1-math.cos(angle))
            right,up,depth=[rotate(v,np.array([0.,1.,0.]),angles['yaw']) for v in (right,up,depth)]
            up,depth=[rotate(v,right,angles['pitch']) for v in (up,depth)]
            right,up=[rotate(v,depth,angles['roll']) for v in (right,up)]
        camera=np.stack([right,-up,depth],axis=1)
        pts=np.concatenate([x[0] for x in triangles])@camera
        lo=pts[:,:2].min(axis=0);hi=pts[:,:2].max(axis=0)
        scale=min(w*.86/max(hi[0]-lo[0],1),h*.84/max(hi[1]-lo[1],1))
        mid=(lo+hi)/2
        def project(x):
            p=x@camera
            p[:,:2]=(p[:,:2]-mid)*scale+[w/2,h/2]
            return p
        zbuf=np.full((h,w),-np.inf,dtype=np.float32)
        rgba=np.zeros((h,w,4),dtype=np.uint8)
        rgb=tuple(int(color.lstrip('#')[i:i+2],16) for i in (0,2,4))
        light=np.array([-.35,-.85,-.4]);light/=np.linalg.norm(light)
        for xyz,c in triangles:
            p=project(xyz)
            a,b,d=p
            denom=(b[1]-d[1])*(a[0]-d[0])+(d[0]-b[0])*(a[1]-d[1])
            if abs(denom)<1e-8:continue
            xmin=max(0,int(math.floor(p[:,0].min())));xmax=min(w-1,int(math.ceil(p[:,0].max())))
            ymin=max(0,int(math.floor(p[:,1].min())));ymax=min(h-1,int(math.ceil(p[:,1].max())))
            if xmin>xmax or ymin>ymax:continue
            xx,yy=np.meshgrid(np.arange(xmin,xmax+1)+.5,np.arange(ymin,ymax+1)+.5)
            wa=((b[1]-d[1])*(xx-d[0])+(d[0]-b[0])*(yy-d[1]))/denom
            wb=((d[1]-a[1])*(xx-d[0])+(a[0]-d[0])*(yy-d[1]))/denom
            wc=1-wa-wb
            zz=wa*a[2]+wb*b[2]+wc*d[2]
            chunk=zbuf[ymin:ymax+1,xmin:xmax+1]
            mask=(wa>=-1e-6)&(wb>=-1e-6)&(wc>=-1e-6)&(zz>chunk)
            normal=np.cross(xyz[1]-xyz[0],xyz[2]-xyz[0]);ln=np.linalg.norm(normal)
            if ln:normal/=ln
            # Les fichiers anciens ne sont pas tous BFC : orienter la normale visible.
            if normal@depth<0:normal=-normal
            shade=.78+.22*max(0,float(normal@light))
            if c==16:base=rgb
            elif c in self.palette:
                v=self.palette[c]['rgb'];base=tuple(int(v[i:i+2],16) for i in (1,3,5))
            elif c>=0x2000000:
                v=c&0xffffff;base=((v>>16)&255,(v>>8)&255,v&255)
            else:base=rgb
            rgba[ymin:ymax+1,xmin:xmax+1][mask]=(*[int(v*shade) for v in base],255)
            chunk[mask]=zz[mask]
        if outlines:
            level=max(0,min(2,int(edge_strength)))
            ink=(35,35,35,255) if level==0 else (0,0,0,255)
            radius=1.5 if level==1 else 2
            offsets=[(0,0),(1,0),(0,1)] if level==0 else [(dx,dy) for dx in range(-2,3) for dy in range(-2,3) if dx*dx+dy*dy<=radius*radius]
            custom=edge_settings is not None
            if custom:
                from .edge_style import normalize_style
                settings=normalize_style(edge_settings);opacity=settings['black']/100;radius=settings['width']*ss/2
                reach=math.ceil(radius+.5)
                offsets=[(dx,dy) for dx in range(-reach,reach+1) for dy in range(-reach,reach+1) if dx*dx+dy*dy<(radius+.5)**2]
            visible_edges=list(edges)
            for x,c in conditional:
                p=project(x);v=p[1,:2]-p[0,:2]
                cross1=v[0]*(p[2,1]-p[0,1])-v[1]*(p[2,0]-p[0,0])
                cross2=v[0]*(p[3,1]-p[0,1])-v[1]*(p[3,0]-p[0,0])
                if cross1*cross2>=0:visible_edges.append((x[:2],c))
            for x,c in visible_edges:
                p=project(x)
                count=max(2,int(np.linalg.norm(p[1,:2]-p[0,:2])*1.5))
                samples=p[0]+np.linspace(0,1,count)[:,None]*(p[1]-p[0])
                for dx,dy in offsets:
                    px=np.rint(samples[:,0]).astype(int)+dx;py=np.rint(samples[:,1]).astype(int)+dy
                    valid=(px>=0)&(px<w)&(py>=0)&(py<h)
                    px=px[valid];py=py[valid];pz=samples[:,2][valid]
                    visible=pz>=zbuf[py,px]-.75
                    if not custom:rgba[py[visible],px[visible]]=ink
                    elif opacity>0:
                        coverage=max(0,min(1,radius+.5-math.hypot(dx,dy)))*opacity
                        old=rgba[py[visible],px[visible]].astype(float);alpha=old[:,3]/255
                        combined=coverage+alpha*(1-coverage)
                        old[:,:3]*=(alpha*(1-coverage)/np.maximum(combined,1e-8))[:,None]
                        old[:,3]=combined*255;rgba[py[visible],px[visible]]=np.rint(old).astype(np.uint8)
        return Image.fromarray(rgba).resize(size,Image.Resampling.LANCZOS),bounds
