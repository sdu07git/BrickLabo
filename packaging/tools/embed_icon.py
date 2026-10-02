"""Rebuild only PE resources; requires lief on the packaging computer."""
import struct,sys
from pathlib import Path
import lief

def embed_icon(executable,icon,destination):
    binary=lief.PE.parse(str(executable));raw=Path(icon).read_bytes()
    reserved,kind,count=struct.unpack_from('<HHH',raw)
    if (reserved,kind)!=(0,1):raise ValueError('Invalid ICO')
    certificate=binary.data_directory(lief.PE.DataDirectory.TYPES.CERTIFICATE_TABLE);certificate.rva=0;certificate.size=0
    resources=binary.resources
    resources.delete_child(3);resources.delete_child(14)
    icons=lief.PE.ResourceDirectory(3);groups=lief.PE.ResourceDirectory(14)
    group=bytearray(struct.pack('<HHH',0,1,count))
    for index in range(count):
        width,height,colors,zero,planes,bpp,size,offset=struct.unpack_from('<BBBBHHII',raw,6+index*16)
        payload=raw[offset:offset+size];assert len(payload)==size
        ident=index+1;node=lief.PE.ResourceDirectory(ident);data=lief.PE.ResourceData(list(payload));data.id=1033;node.add_child(data);icons.add_child(node)
        group.extend(struct.pack('<BBBBHHIH',width,height,colors,zero,planes,bpp,size,ident))
    node=lief.PE.ResourceDirectory(1);data=lief.PE.ResourceData(list(group));data.id=1033;node.add_child(data);groups.add_child(node)
    resources.add_child(icons);resources.add_child(groups)
    config=lief.PE.Builder.config_t();config.resources=True
    builder=lief.PE.Builder(binary,config);builder.build();builder.write(str(destination))
    rebuilt=lief.PE.parse(str(destination));original=lief.PE.parse(str(executable))
    assert original.optional_header.addressof_entrypoint==rebuilt.optional_header.addressof_entrypoint
    assert bytes(original.get_section('.text').content)==bytes(rebuilt.get_section('.text').content)
    assert [(x.name,[e.name for e in x.entries]) for x in original.imports]==[(x.name,[e.name for e in x.entries]) for x in rebuilt.imports]
    assert len(list(rebuilt.resources_manager.icons))==count
    for actual in rebuilt.resources_manager.icons:
        assert bytes(actual.pixels).startswith(b'\x89PNG')
if __name__=='__main__':embed_icon(*sys.argv[1:])
