"""Rebuildable query accelerators, independent of ownership and action history."""


def prepare(c):
    from .search_index import DOCUMENT
    c.executescript('''
        CREATE INDEX IF NOT EXISTS idx_catalogue_ref ON items(source,kind,catalogue_hidden,ref COLLATE NOCASE,id);
        CREATE INDEX IF NOT EXISTS idx_catalogue_name ON items(source,kind,catalogue_hidden,name COLLATE NOCASE,id);
        CREATE INDEX IF NOT EXISTS idx_catalogue_category ON items(source,kind,catalogue_hidden,category COLLATE NOCASE,id);
        CREATE INDEX IF NOT EXISTS idx_themes_parent ON themes(parent_id,id);
        CREATE INDEX IF NOT EXISTS idx_project_allocated_entry ON project_set_allocations(set_entry_id,project_id);
        CREATE INDEX IF NOT EXISTS idx_project_pick_stock ON project_pick_rows(item_id,color);
        CREATE INDEX IF NOT EXISTS idx_project_color_pick_stock ON project_color_pick_rows(item_id,stock_color);
        CREATE INDEX IF NOT EXISTS idx_set_components_item ON stock_set_components(item_id,color,set_entry_id);
        CREATE TABLE IF NOT EXISTS item_decorations(
            item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
            printed INTEGER NOT NULL,sticker INTEGER NOT NULL,
            catalogue_text TEXT,storage_text TEXT);
    ''')
    if 'category_id' in {r[1] for r in c.execute('PRAGMA table_info(items)')}:
        c.execute('CREATE INDEX IF NOT EXISTS idx_catalogue_theme ON items(source,kind,category_id)')
    fields={r[1] for r in c.execute('PRAGMA table_info(item_decorations)')}
    for column in ('catalogue_text','storage_text'):
        if column not in fields:c.execute('ALTER TABLE item_decorations ADD COLUMN '+column+' TEXT')
    storage="norm(COALESCE({p}ref||' '||{p}name||' '||{p}category,''))"
    c.execute('''INSERT INTO item_decorations(item_id,printed,sticker,catalogue_text,storage_text)
            SELECT id,CASE WHEN kind='part' THEN part_has_print(ref,name) ELSE 0 END,
                CASE WHEN kind='part' THEN part_has_sticker(ref,name) ELSE 0 END,'''+DOCUMENT.format(p='')+','+storage.format(p='')+'''
            FROM items WHERE NOT EXISTS(SELECT 1 FROM item_decorations d WHERE d.item_id=items.id)''')
    c.execute('UPDATE item_decorations SET catalogue_text=(SELECT '+DOCUMENT.format(p='i.')+' FROM items i WHERE i.id=item_id),storage_text=(SELECT '+storage.format(p='i.')+' FROM items i WHERE i.id=item_id) WHERE catalogue_text IS NULL OR storage_text IS NULL')
    triggers={
        'item_decorations_insert':'''CREATE TRIGGER item_decorations_insert AFTER INSERT ON items BEGIN
            INSERT INTO item_decorations VALUES(new.id,
                CASE WHEN new.kind='part' THEN part_has_print(new.ref,new.name) ELSE 0 END,
                CASE WHEN new.kind='part' THEN part_has_sticker(new.ref,new.name) ELSE 0 END,'''+DOCUMENT.format(p='new.')+','+storage.format(p='new.')+'''); END''',
        'item_decorations_update':'''CREATE TRIGGER item_decorations_update AFTER UPDATE OF ref,name,kind,search,category ON items
            WHEN old.ref IS NOT new.ref OR old.name IS NOT new.name OR old.kind IS NOT new.kind OR old.search IS NOT new.search OR old.category IS NOT new.category BEGIN
            INSERT INTO item_decorations VALUES(new.id,
                CASE WHEN new.kind='part' THEN part_has_print(new.ref,new.name) ELSE 0 END,
                CASE WHEN new.kind='part' THEN part_has_sticker(new.ref,new.name) ELSE 0 END,'''+DOCUMENT.format(p='new.')+','+storage.format(p='new.')+''')
            ON CONFLICT(item_id) DO UPDATE SET printed=excluded.printed,sticker=excluded.sticker,catalogue_text=excluded.catalogue_text,storage_text=excluded.storage_text; END''',
        'item_decorations_delete':'''CREATE TRIGGER item_decorations_delete AFTER DELETE ON items BEGIN
            DELETE FROM item_decorations WHERE item_id=old.id; END'''}
    for name,sql in triggers.items():
        old=c.execute('SELECT sql FROM sqlite_master WHERE name=?',(name,)).fetchone()
        if not old or old[0]!=sql:c.execute('DROP TRIGGER IF EXISTS '+name);c.execute(sql)
