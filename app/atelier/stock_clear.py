"""Clear one physical stock ledger atomically, retaining identities and undo."""
import json
from .i18n import tr


def statistics(db, scope):
    if scope not in ('stock', 'stock_sets'):
        raise ValueError(tr('Destination inconnue'))
    with db.read() as c:
        c.execute('BEGIN')
        row = c.execute('SELECT COUNT(*) AS lines,COALESCE(SUM(quantity),0) AS quantity FROM ' + scope + ' WHERE quantity>0').fetchone()
        return dict(row, revision=c.execute('SELECT version FROM stock_revision WHERE id=1').fetchone()[0],
                    reserved=c.execute('SELECT COALESCE(SUM(reserved),0) FROM project_parts').fetchone()[0] if scope == 'stock' else 0,
                    counted=c.execute('SELECT COALESCE(SUM(quantity),0) FROM storage_contents').fetchone()[0] if scope == 'stock' else 0)


def clear(db, scope, expected_revision=None):
    if scope not in ('stock', 'stock_sets'):
        raise ValueError(tr('Destination inconnue'))
    from .action_history import change
    tables = ('stock', 'stock_sets', 'stock_set_components', 'settings', 'project_parts', 'project_color_reservations', 'storage_contents')
    description = tr('Vidage de Mon stock') if scope == 'stock' else tr('Vidage de Mon stock set')
    with db.connect() as c, change(c, tables, description):
        if expected_revision is not None and c.execute('SELECT version FROM stock_revision WHERE id=1').fetchone()[0] != expected_revision:
            raise ValueError(tr('Le stock a changé pendant la confirmation. Recommence pour vérifier les quantités actuelles.'))
        if scope == 'stock':
            if c.execute('SELECT 1 FROM project_physical_picks LIMIT 1').fetchone():raise ValueError(tr('Retourne les prélèvements avant de vider le stock.'))
            c.execute('UPDATE stock SET quantity=0 WHERE quantity<>0')
            c.execute('UPDATE project_parts SET reserved=0 WHERE reserved>0')
            c.execute('DELETE FROM project_color_reservations')
            c.execute('UPDATE storage_contents SET quantity=0 WHERE quantity>0')
        else:
            c.execute('DELETE FROM stock_set_components')
            c.execute('DELETE FROM stock_sets')
        c.execute('DELETE FROM settings WHERE key GLOB ?', ('label_layout_' + scope + '_[0-9]*',))
        row = c.execute("SELECT value FROM settings WHERE key='build_excluded_entries'").fetchone()
        if row:
            excluded = [x for x in json.loads(row['value']) if (x <= 0 if scope == 'stock' else x >= 0)]
            c.execute("UPDATE settings SET value=? WHERE key='build_excluded_entries'", (json.dumps(excluded),))
        c.execute('DELETE FROM stock_undo')
