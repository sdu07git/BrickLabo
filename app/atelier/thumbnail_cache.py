"""Bounded, disposable previews. Never owns imported images or user data."""
from collections import OrderedDict
import hashlib,json,os,threading,time,uuid
from pathlib import Path
from PIL import Image
import logging
from concurrent.futures import Future
from .fileio import compact_digest,atomic_output,error_message

class ThumbnailCache:
    def __init__(self,folder,ram_limit=32*1024*1024,disk_limit=256*1024*1024):
        self.folder=Path(folder);self.disk_error=False
        try:self.folder.mkdir(parents=True,exist_ok=True)
        except OSError as error:self.warn(error)
        self.ram_limit=ram_limit;self.disk_limit=disk_limit;self.memory=OrderedDict();self.memory_bytes=0;self.lock=threading.RLock();self.generation=0
        self.disk=OrderedDict();self.disk_bytes=0;self.pending={};self.misses=OrderedDict()
        entries=[]
        for p in self.folder.glob('*.png'):
            try:st=p.stat();entries.append((st.st_mtime,p,st.st_size))
            except OSError:pass
        for _,p,size in sorted(entries):self.disk[p]=size;self.disk_bytes+=size
        self.trim()
    def warn(self,error):
        if not self.disk_error:
            logging.getLogger('bricklabo').warning('Miniatures : cache mémoire conservé, écriture disque impossible. %s',error_message(error))
            self.disk_error=True
    def path(self,key):
        digest=compact_digest(json.dumps(key,ensure_ascii=False,default=str))
        return self.folder/(str(key[0])+'-'+digest+'.png')
    def remember(self,key,image):
        size=image.width*image.height*4
        old=self.memory.pop(key,None)
        if old:self.memory_bytes-=old[1]
        if size>self.ram_limit:return
        self.memory[key]=(image,size);self.memory_bytes+=size
        while self.memory_bytes>self.ram_limit:
            _,(_,cost)=self.memory.popitem(last=False);self.memory_bytes-=cost
    def get(self,key):
        with self.lock:
            found=self.memory.get(key)
            if found:
                self.memory.move_to_end(key)
                path=self.path(key)
                if path in self.disk:self.disk.move_to_end(path)
                return found[0]
            if not self.disk_limit:return None
            path=self.path(key)
            try:
                with Image.open(path) as im:image=im.convert('RGBA')
                if image.size!=(100,65):raise ValueError('Invalid thumbnail')
                if path in self.disk:self.disk.move_to_end(path)
                self.remember(key,image);return image
            except (OSError,ValueError):
                try:path.unlink(missing_ok=True)
                except OSError:pass
                return None
    def put(self,key,image,generation=None):
        scale=min(1,100/image.width,65/image.height)
        small=image.resize((max(1,round(image.width*scale)),max(1,round(image.height*scale))),Image.Resampling.LANCZOS).convert('RGBA')
        canvas=Image.new('RGBA',(100,65));canvas.alpha_composite(small,((100-small.width)//2,(65-small.height)//2))
        with self.lock:
            if generation is not None and generation!=self.generation:return canvas
            self.remember(key,canvas);path=self.path(key)
            if not self.disk_limit:return canvas
            if path in self.disk and path.is_file():self.disk.move_to_end(path);return canvas
            try:
                with atomic_output(path) as temp:canvas.save(temp,format='PNG')
                self.disk_bytes-=self.disk.pop(path,0);size=path.stat().st_size;self.disk[path]=size;self.disk_bytes+=size;self.trim()
            except OSError as error:self.warn(error)
        return canvas
    def configure(self,ram_limit,disk_limit):
        with self.lock:
            self.ram_limit=ram_limit;self.disk_limit=disk_limit
            while self.memory_bytes>ram_limit:self.memory_bytes-=self.memory.popitem(last=False)[1][1]
            self.trim()
    def get_or_create(self,key,factory,generation=None):
        image=self.get(key)
        if image is not None:return image
        with self.lock:
            image=self.get(key) if key in self.memory or self.path(key) in self.disk else None
            if image is not None:return image
            if self.misses.get(key,0)>time.monotonic():return None
            if generation is None:generation=self.generation
            pending=self.pending.get(key)
            future=pending[0] if pending and pending[1]==generation else None;owner=future is None
            if owner:future=Future();self.pending[key]=(future,generation)
        if not owner:return future.result()
        try:
            image=factory()
            if image is not None:image=self.put(key,image,generation)
            else:
                with self.lock:
                    if generation==self.generation:
                        self.misses[key]=time.monotonic()+60
                        while len(self.misses)>1024:self.misses.popitem(last=False)
            future.set_result(image);return image
        except BaseException as error:future.set_exception(error);raise
        finally:
            with self.lock:
                if self.pending.get(key)==(future,generation):self.pending.pop(key,None)
    def trim(self):
        with self.lock:
            for p in list(self.disk):
                if self.disk_bytes<=self.disk_limit:break
                try:p.unlink(missing_ok=True);self.disk_bytes-=self.disk.pop(p)
                except OSError:pass
    def invalidate(self,iid=None):
        with self.lock:
            self.generation+=1;self.misses.clear()
            for key in list(self.memory):
                if iid is None or key[0]==iid:self.memory_bytes-=self.memory.pop(key)[1]
            for p in self.folder.glob('*.png' if iid is None else str(iid)+'-*.png'):
                try:p.unlink();self.disk_bytes-=self.disk.pop(p,0)
                except OSError:pass
    def usage(self):
        with self.lock:
            total=0
            for p in self.folder.glob('*.png'):
                try:total+=p.stat().st_size
                except OSError:pass
            return self.memory_bytes,total

def file_stamp(path):
    if not path:return ()
    try:s=Path(path).stat();return (s.st_mtime_ns,s.st_size)
    except OSError:return ()
