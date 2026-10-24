"""Reject missing/duplicate/failed shards rather than claiming a partial suite passed."""
import argparse
import json
from pathlib import Path
from test_shards import combine

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    reports=[json.loads(path.read_text(encoding='utf-8')) for path in args.reports.rglob('tests.json')]
    summary=combine(reports)
    if {row['system'] for row in summary}!={'Linux','Windows'}:
        raise ValueError('Both Linux and Windows reports are required')
    args.output.write_text(json.dumps(dict(success=True,platforms=summary),indent=2)+'\n',encoding='utf-8')
    print(args.output.read_text(encoding='utf-8'))
