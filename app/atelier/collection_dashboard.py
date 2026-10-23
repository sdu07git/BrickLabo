"""Collection overview with explicit distinctions between ownership and locations."""
from .i18n import tr,tf


def snapshot(db):
    with db.read() as c:
        c.execute('BEGIN')
        def value(sql):return c.execute(sql).fetchone()[0] or 0
        metrics={
            'loose_units':value('SELECT SUM(quantity) FROM stock'),
            'loose_references':value('SELECT COUNT(DISTINCT item_id) FROM stock WHERE quantity>0'),
            'owned_sets':value('SELECT SUM(quantity) FROM stock_sets'),
            'reserved_loose':value('SELECT SUM(reserved) FROM project_stock_reservations'),
            'allocated_sets':value('SELECT SUM(copies) FROM project_set_allocations'),
            'located_units':value('SELECT SUM(quantity) FROM storage_contents'),
            'unknown_locations':value('SELECT COUNT(*) FROM storage_contents WHERE quantity IS NULL'),
            'picked_units':value('SELECT SUM(quantity) FROM project_physical_picks'),
            'unlocated_picks':value('SELECT SUM(quantity) FROM project_physical_picks WHERE drawer_id IS NULL'),
            'remaining_to_store':value('''SELECT SUM(MAX(0,s.quantity-COALESCE((SELECT SUM(p.quantity) FROM storage_contents p WHERE p.item_id=s.item_id AND p.color=s.color),0)-COALESCE((SELECT SUM(p.quantity) FROM project_physical_picks p WHERE p.item_id=s.item_id AND p.color=s.color),0))) FROM stock s'''),
            'cabinets':value('SELECT COUNT(*) FROM storage_walls'),
            'drawers':value('SELECT COUNT(*) FROM storage_drawers'),
            'active_projects':value("SELECT COUNT(*) FROM construction_projects WHERE status<>'completed'"),
        }
        sources=[]
        for source in ('RB','BL','ALT'):
            row=dict(c.execute("SELECT COUNT(*) AS sets,MAX(imported_at) AS last_import FROM items WHERE source=? AND kind='set' AND catalogue_hidden=0",(source,)).fetchone())
            if source=='RB':present=c.execute("SELECT COUNT(*) FROM items i WHERE source='RB' AND kind='set' AND catalogue_hidden=0 AND EXISTS(SELECT 1 FROM inventories v WHERE v.set_num=i.ref)").fetchone()[0]
            elif source=='BL':present=c.execute("SELECT COUNT(*) FROM items i WHERE source='BL' AND kind='set' AND catalogue_hidden=0 AND (EXISTS(SELECT 1 FROM bl_manual_inventory b WHERE b.set_id=i.id) OR EXISTS(SELECT 1 FROM settings s WHERE s.key='bl_inventory_'+i.ref))").fetchone()[0]
            else:present=c.execute("SELECT COUNT(*) FROM items i WHERE source='ALT' AND kind='set' AND catalogue_hidden=0 AND EXISTS(SELECT 1 FROM settings s WHERE s.key='alt_components_'||i.id)").fetchone()[0]
            sources.append(dict(row,source=source,inventories_present=present,without_local_inventory=max(0,row['sets']-present)))
        imports=[dict(r) for r in c.execute('SELECT * FROM imports ORDER BY date DESC LIMIT 20')]
        from .projects import list_projects
        # Keep this read snapshot short; the project breakdown is fetched after it.
    projects=list_projects(db)
    return dict(metrics=metrics,sources=sources,imports=imports,projects=projects,backup=db.setting('automatic_backup_status',{}))


def panel(db,parent=None):
    from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPushButton,QTabWidget
    from .collection_dialogs import table
    from .result_tables import fill_table
    from .ui_common import async_task
    widget=QWidget(parent);layout=QVBoxLayout(widget);heading=QLabel(tr('Tableau de bord de ma collection'));layout.addWidget(heading)
    metrics=QLabel();metrics.setWordWrap(True);layout.addWidget(metrics)
    tabs=QTabWidget();layout.addWidget(tabs,1)
    sources=table([tr('Source'),tr('Sets au catalogue'),tr('Inventaires locaux présents'),tr('Sans inventaire local'),tr('Dernière entrée au catalogue')]);tabs.addTab(sources,tr('Couverture des données'))
    projects=table([tr('Projet'),tr('Nécessaire'),tr('Réservée'),tr('Manquante')]);tabs.addTab(projects,tr('Mes projets'))
    imports=table([tr('Fichier'),tr('Date'),tr('Lignes')]);tabs.addTab(imports,tr('Imports récents'))
    note=QLabel(tr('Un inventaire présent peut encore être incomplet. Les quantités en tiroir sont une localisation du vrac, pas un stock supplémentaire. Les liens sans quantité restent à compter.'));note.setWordWrap(True);layout.addWidget(note)
    status=QLabel();status.setWordWrap(True);layout.addWidget(status);button=QPushButton(tr('Actualiser le tableau de bord'));layout.addWidget(button);busy=[False]
    def refresh():
        if busy[0]:return
        busy[0]=True;button.setEnabled(False)
        def done(result):
            busy[0]=False;button.setEnabled(True);m=result['metrics']
            metrics.setText(tf('{0} pièces en vrac · {1} références · {2} sets possédés\n{3} pièces réservées · {4} exemplaires affectés aux projets\n{5} pièces localisées · {6} pièces à ranger · {7} liens sans quantité\n{8} meubles · {9} tiroirs · {10} projets actifs',*[m[key] for key in ('loose_units','loose_references','owned_sets','reserved_loose','allocated_sets','located_units','remaining_to_store','unknown_locations','cabinets','drawers','active_projects')]))
            fill_table(sources,[(r['source'],r['sets'],r['inventories_present'],r['without_local_inventory'],r['last_import'] or '—') for r in result['sources']]);fill_table(projects,[(r['name'],r['required'],r['reserved'],r['missing']) for r in result['projects']]);fill_table(imports,[(r['file'],r['date'],r['rows']) for r in result['imports']])
            backup=result['backup'];status.setText(tr('Dernière sauvegarde automatique : ')+backup.get('path','—')+('\n'+backup['error'] if backup.get('error') else ''))
        def failed(error):busy[0]=False;button.setEnabled(True);status.setText(str(error))
        async_task(widget,lambda progress:snapshot(db),done,failed)
    widget.refresh=refresh;button.clicked.connect(refresh);return widget
