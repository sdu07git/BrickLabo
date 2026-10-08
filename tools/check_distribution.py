"""Validate the embedded icon and the exact packaged Python dependencies."""
import argparse
from email.parser import Parser
import json
from pathlib import Path
import re
import struct


def pe_resources(data):
    def u16(offset):return struct.unpack_from('<H',data,offset)[0]
    def u32(offset):return struct.unpack_from('<I',data,offset)[0]
    if data[:2]!=b'MZ':raise ValueError('Invalid DOS header')
    pe=u32(0x3c);optional=pe+24
    if data[pe:pe+4]!=b'PE\0\0' or u16(pe+4)!=0x8664 or u16(optional)!=0x20b:
        raise ValueError('Expected an AMD64 PE32+ executable')
    sections=[]
    for i in range(u16(pe+6)):
        p=optional+u16(pe+20)+i*40
        size,va,raw_size,raw=struct.unpack_from('<IIII',data,p+8)
        sections.append((va,max(size,raw_size),raw))
    def offset(rva):
        for va,size,raw in sections:
            if va<=rva<va+size:return raw+rva-va
        raise ValueError('Invalid resource RVA')
    base=offset(u32(optional+112+2*8));resources={}
    def walk(relative,keys=()):
        p=base+relative
        for i in range(u16(p+12)+u16(p+14)):
            name,target=struct.unpack_from('<II',data,p+16+i*8)
            if name&0x80000000:
                n=base+(name&0x7fffffff);key=data[n+2:n+2+2*u16(n)].decode('utf-16le')
            else:key=name
            branch=keys+(key,)
            if target&0x80000000:walk(target&0x7fffffff,branch)
            else:
                rva,size=struct.unpack_from('<II',data,base+target);start=offset(rva)
                resources[branch]=data[start:start+size]
    walk(0)
    return resources


def check_icon(executable,icon):
    resources=pe_resources(Path(executable).read_bytes());ico=Path(icon).read_bytes()
    reserved,kind,count=struct.unpack_from('<HHH',ico)
    if (reserved,kind)!=(0,1):raise ValueError('Invalid ICO header')
    groups=[(key,value) for key,value in resources.items() if key[0]==14]
    if len(groups)!=1 or groups[0][0][1]!=101:raise ValueError('Missing launcher icon group 101')
    key,group=groups[0]
    if struct.unpack_from('<HHH',group)!=(0,1,count):raise ValueError('ICO/group mismatch')
    sizes=[]
    for i in range(count):
        source=struct.unpack_from('<BBBBHHII',ico,6+i*16)
        embedded=struct.unpack_from('<BBBBHHIH',group,6+i*14)
        payload=resources.get((3,embedded[7],key[2]))
        if source[:7]!=embedded[:7] or payload!=ico[source[7]:source[7]+source[6]]:
            raise ValueError('Icon payload differs from the packaged ICO')
        if len(payload)<40 or struct.unpack_from('<I',payload)[0]!=40 or struct.unpack_from('<H',payload,14)[0]!=32:
            raise ValueError('Expected a classic 32-bit Windows icon bitmap')
        sizes.append(source[0] or 256)
    if not {16,32,48,256}.issubset(sizes):raise ValueError('Missing Windows icon sizes')
    manifests=[value for key,value in resources.items() if key[0]==24]
    if not any(b'longPathAware' in value for value in manifests):raise ValueError('Missing long-path manifest')
    return {'resource_id':101,'sizes':sizes,'format':'32-bit DIB','payloads_match':True}


def canonical(name):return re.sub(r'[-_.]+','-',name).lower()


def satisfies(version,constraint):
    def digits(value):
        parts=tuple(int(p) for p in value.strip().split('.'))
        return parts+(0,)*(4-len(parts))
    value=digits(version)
    for term in constraint.split(','):
        if not term.strip():continue
        match=re.fullmatch(r'\s*(==|>=|<=|>|<)\s*([0-9.]+)\s*',term)
        if not match:raise ValueError('Unsupported version constraint: '+term)
        op,wanted=match.groups();other=digits(wanted)
        if not {'==':value==other,'>=':value>=other,'<=':value<=other,'>':value>other,'<':value<other}[op]:return False
    return True


def check_runtime(root):
    root=Path(root);manifest=json.loads((root/'app/COMPOSANTS.json').read_text(encoding='utf-8'))
    match=re.search(r'Python ([0-9.]+)',manifest['runtime'])
    if not match:raise ValueError('Missing Python version')
    python=match[1];expected={}
    for line in (root/'app/requirements.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.startswith('#'):continue
        name,version=line.split('==');expected[canonical(name)]=version.strip()
    metadata={}
    for path in (root/'app/lib').glob('*.dist-info/METADATA'):
        entry=Parser().parsestr(path.read_text(encoding='utf-8'))
        metadata[canonical(entry['Name'])]=entry
    installed={name:entry['Version'] for name,entry in metadata.items()}
    if installed!=expected:raise ValueError('Packaged versions differ from requirements: '+str(installed))
    for name,entry in metadata.items():
        if not satisfies(python,entry.get('Requires-Python','')):raise ValueError(name+' does not support Python '+python)
        for requirement in entry.get_all('Requires-Dist',[]):
            value,_,marker=requirement.partition(';')
            if marker:
                if 'extra' in marker:continue
                condition=re.fullmatch(r'\s*python_version\s*(==|>=|<=|>|<)\s*[\"\']([0-9.]+)[\"\']\s*',marker)
                if not condition:raise ValueError('Unsupported dependency marker: '+marker)
                if not satisfies('.'.join(python.split('.')[:2]),''.join(condition.groups())):continue
            dependency=re.fullmatch(r'\s*([\w.-]+)\s*(?:\(([^)]+)\)|([^()]*))\s*',value)
            if not dependency:raise ValueError('Invalid dependency: '+value)
            target=canonical(dependency[1]);constraint=(dependency[2] or dependency[3] or '').strip()
            if target not in installed or not satisfies(installed[target],constraint):raise ValueError('Unsatisfied dependency: '+requirement)
    return {'python':python,'versions':installed,'mandatory_dependencies_satisfied':True}


def check(root):
    root=Path(root)
    return {'icon':check_icon(root/'BrickLabo.exe',root/'ressources/BrickLabo.ico'),'runtime':check_runtime(root)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path)
    print(json.dumps(check(parser.parse_args().root),indent=2))
