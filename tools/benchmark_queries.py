"""Repeatable query measurements on a disposable bundled-catalogue collection.

--prepare refuses an existing file. Never pass a personal collection. Results
include the first call, warm median, SQL statement counts and result digests.
--source-root allows identical measurements against an earlier checkout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter
from contextlib import contextmanager


def prepare(db,root):
    files=['part_categories.csv.zip','themes.csv.zip','colors.csv.zip','parts.csv.zip',
           'sets.csv.zip','minifigs.csv.zip','inventories.csv.zip','inventory_parts.csv.zip',
           'inventory_sets.csv.zip','inventory_minifigs.csv.zip','part_relationships.csv.zip',
           'Parts.txt','Sets.txt','Minifigures.txt']
    for name in files:
        start=perf_counter();n=db.import_file(root/'ressources'/name)
        print('Imported',name,n,round(perf_counter()-start,3),flush=True)
    from atelier.brickarchitect import replace_catalogue
    replace_catalogue(db,json.loads((root/'ressources/brickarchitect.json').read_text()))
    with db.connect() as c:
        ids=[r[0] for r in c.execute("SELECT id FROM items WHERE source='RB' AND kind='part' ORDER BY id LIMIT 5000")]
        c.executemany('INSERT INTO stock(item_id,color,quantity) VALUES(?,?,?)',[(i,color,100) for i in ids for color in ('0','4')])
        for number in range(100):
            pid=c.execute('INSERT INTO construction_projects(name,ignore_colors,include_set_stock) VALUES(?,?,?)',('Benchmark '+str(number),int(number%3==0),0)).lastrowid
            c.executemany('INSERT INTO project_parts(project_id,item_id,color,required) VALUES(?,?,?,?)',[(pid,i,'4',120) for i in ids[number*50:number*50+50]])
        c.executemany('INSERT INTO storage_walls(name,columns,rows,x,y) VALUES(?,50,40,?,0)',[('Bench '+str(i),i*51) for i in range(5)])
        c.executemany('INSERT INTO storage_drawers(wall_id,col,row) VALUES(?,?,?)',[(w,col,row) for w in range(1,6) for row in range(1,41) for col in range(1,51)])
        drawers=[r[0] for r in c.execute('SELECT id FROM storage_drawers ORDER BY id LIMIT 5000')]
        c.executemany('INSERT INTO storage_contents(drawer_id,item_id,color,quantity) VALUES(?,?,?,?)',[(d,i,'4',50) for d,i in zip(drawers,ids)])
    db.set_setting('benchmark_queries',True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true');parser.add_argument('--full',action='store_true')
    parser.add_argument('--repeats',type=int,default=3);parser.add_argument('--timeout',type=float,default=30)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.source_root.resolve()
    if args.prepare and args.database.exists():parser.error('Preparation requires a new disposable database')
    sys.path.insert(0,str(root/'app'))
    from atelier.data import Database
    from atelier import projects,storage_assignment,storage_wall
    from atelier.build_stock import find_builds
    from atelier.version import VERSION
    db=Database(args.database)
    try:
        if args.prepare:prepare(db,root)
        if not db.setting('benchmark_queries',False):raise ValueError('Not a disposable benchmark collection')
        cases=[
            ('catalogue_first',lambda:db.query('RB','part')),
            ('catalogue_page_50',lambda:db.query('RB','part',page=50)),
            ('catalogue_name',lambda:db.query('RB','part',sort='name')),
            ('catalogue_search',lambda:db.query('RB','part',search='brick -duplo')),
            ('catalogue_undecorated',lambda:db.query('RB','part',hide_decorated=True)),
            ('catalogue_sets_theme',lambda:db.query('RB','set',search='star wars')),
            ('catalogue_categories',lambda:db.categories('RB','part')),
            ('catalogue_years',lambda:db.years('RB','set')),
            ('stock_first',lambda:db.query(scope='stock')),
            ('stock_remaining',lambda:db.query(scope='stock',sort='remaining_quantity')),
            ('projects_summary',lambda:projects.list_projects(db)),
            ('project_details',lambda:projects.detail(db,1)),
            ('drawer_stock_search',lambda:storage_assignment.stock_rows(db,'brick',limit=5000,remaining_only=True)),
            ('drawer_catalogue_search',lambda:storage_assignment.catalogue_rows(db,'brick',limit=5000)),
            ('cabinet_contents',lambda:storage_wall.wall_contents(db)),
            ('settings_1000',lambda:[db.setting('template',{}) for _ in range(1000)]),
            ('builds_millennium',lambda:find_builds(db,text='millennium',ignore_colors=True,minimum=1,include_set_stock=False)),
        ]
        if args.full:cases.append(('builds_all',lambda:find_builds(db,ignore_colors=True,minimum=1,include_set_stock=False)))
        results=[]
        active=[None];original_connect=db.connect
        @contextmanager
        def observed_connect():
            with original_connect() as connection:
                current=active[0]
                if current:
                    counter,deadline=current
                    connection.set_trace_callback(lambda sql:counter.__setitem__(0,counter[0]+1))
                    connection.set_progress_handler(lambda:int(perf_counter()>deadline),1000)
                try:yield connection
                finally:connection.set_trace_callback(None);connection.set_progress_handler(None,0)
        db.connect=observed_connect
        for name,action in cases:
            times=[];statements=[];digests=[];error=''
            for _ in range(args.repeats):
                count=[0];start=perf_counter();deadline=start+args.timeout
                active[0]=(count,deadline)
                with db.read() as c:
                    c.set_trace_callback(lambda sql:count.__setitem__(0,count[0]+1))
                    c.set_progress_handler(lambda:int(perf_counter()>deadline),1000)
                    try:
                        value=action();elapsed=perf_counter()-start
                        digests.append(hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest())
                    except Exception as exc:error=type(exc).__name__+': '+str(exc);elapsed=perf_counter()-start
                    finally:c.set_trace_callback(None);c.set_progress_handler(None,0);active[0]=None
                times.append(elapsed);statements.append(count[0])
                if error:break
            result=dict(case=name,first_seconds=times[0],warm_median_seconds=median(times[1:] or times),statements=statements,digests=digests,error=error)
            results.append(result);print(name,round(times[0],6),round(result['warm_median_seconds'],6),statements,error,flush=True)
            args.output.write_text(json.dumps(dict(version=VERSION,system=platform.system(),python=platform.python_version(),counts=dict(items=db.rows('SELECT COUNT(*) AS n FROM items')[0],inventory_parts=db.rows('SELECT COUNT(*) AS n FROM inventory_parts')[0],stock=db.rows('SELECT COUNT(*) AS n FROM stock')[0]),results=results),indent=2)+'\n')
    finally:db.close()


if __name__=='__main__':main()
