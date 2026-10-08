"""Bounded image memory and shared in-flight calculations."""
from collections import OrderedDict
from concurrent.futures import Future
import threading

class MemoryCache:
    def __init__(self,limit=64*1024*1024):
        self.limit=limit;self.items=OrderedDict();self.pending={};self.bytes=0;self.lock=threading.RLock();self.generation=0
    def get_or_create(self,key,factory):
        with self.lock:
            if key in self.items:self.items.move_to_end(key);return self.items[key][0]
            pending=self.pending.get(key);generation=self.generation
            future=pending[0] if pending and pending[1]==generation else None;owner=future is None
            if owner:future=Future();self.pending[key]=(future,generation)
        if not owner:return future.result()
        try:
            value=factory();image=value[0] if isinstance(value,tuple) else value;cost=getattr(image,'width',0)*getattr(image,'height',0)*4+128
            with self.lock:
                if generation==self.generation and cost<=self.limit:
                    self.items[key]=(value,cost);self.bytes+=cost
                    while self.bytes>self.limit:self.bytes-=self.items.popitem(last=False)[1][1]
            future.set_result(value);return value
        except BaseException as error:future.set_exception(error);raise
        finally:
            with self.lock:
                if self.pending.get(key)==(future,generation):self.pending.pop(key,None)
    def clear(self):
        with self.lock:self.generation+=1;self.items.clear();self.bytes=0
