"""Bounded, defensive copies of read results, invalidated by SQLite data_version."""
from collections import OrderedDict
from copy import deepcopy
from sys import getsizeof


def memory_size(value,seen=None,budget=None):
    seen=set() if seen is None else seen
    if id(value) in seen:return 0
    seen.add(id(value));size=getsizeof(value)
    if budget is not None and size>budget:return size
    children=(v for pair in value.items() for v in pair) if isinstance(value,dict) else iter(value) if isinstance(value,(list,tuple)) else ()
    for child in children:
        size+=memory_size(child,seen,None if budget is None else budget-size)
        if budget is not None and size>budget:break
    return size


def key(value):
    if isinstance(value,dict):return tuple(sorted((k,key(v)) for k,v in value.items()))
    if isinstance(value,(list,tuple)):return tuple(map(key,value))
    return value


class ReadCache:
    def __init__(self,limit=8*1024*1024,entries=256):
        self.limit=limit;self.entries=entries;self.version=None;self.items=OrderedDict();self.bytes=0
    def clear(self):self.items.clear();self.bytes=0;self.version=None
    def use_version(self,version):
        if version!=self.version:self.clear();self.version=version
    def get(self,identity):
        found=self.items.get(identity)
        if found is None:return False,None
        self.items.move_to_end(identity);return True,deepcopy(found[0])
    def put(self,identity,value):
        cost=memory_size((identity,value),budget=self.limit//2)+256
        if cost>self.limit//2:return
        previous=self.items.pop(identity,None)
        if previous:self.bytes-=previous[1]
        self.items[identity]=(deepcopy(value),cost);self.bytes+=cost
        while self.bytes>self.limit or len(self.items)>self.entries:self.bytes-=self.items.popitem(last=False)[1][1]
