"""Deterministic test partitions with a census that proves full coverage."""
import hashlib
import json
import unittest


def census(ids):
    return hashlib.sha256(json.dumps(sorted(ids),separators=(',',':')).encode()).hexdigest()


def select_suite(suite, shard=None):
    def flatten(value):
        for child in value:
            if isinstance(child,unittest.TestSuite):yield from flatten(child)
            else:yield child
    cases=list(flatten(suite));ids=[case.id() for case in cases]
    index,total=shard or (0,1)
    selected=[case for case in cases if int.from_bytes(hashlib.sha256(case.id().encode()).digest()[:8],'big')%total==index]
    metadata=dict(shard_index=index,shard_count=total,discovered_tests=len(ids),discovered_digest=census(ids))
    return unittest.TestSuite(selected),metadata


def combine(reports):
    groups={}
    for report in reports:
        groups.setdefault((report['version'],report['system']),[]).append(report)
    summaries=[]
    for (version,system),values in sorted(groups.items()):
        total=values[0]['shard_count'];expected=values[0]['discovered_tests'];digest=values[0]['discovered_digest']
        if len(values)!=total or {r['shard_index'] for r in values}!=set(range(total)):
            raise ValueError('Missing or duplicate test shard: '+system)
        if any(r['shard_count']!=total or r['discovered_tests']!=expected or r['discovered_digest']!=digest for r in values):
            raise ValueError('Inconsistent test census: '+system)
        if any(not r['success'] or not r['qt_shutdown'] or r['failures'] or r['errors'] for r in values):
            raise ValueError('A test shard did not pass: '+system)
        cases=[case for report in values for case in report['cases']]
        if sum(r['tests'] for r in values)!=expected or len(cases)!=expected or census([case['id'] for case in cases])!=digest:
            raise ValueError('Full test coverage was not established: '+system)
        summaries.append(dict(version=version,system=system,tests=expected,failures=0,errors=0,
            skipped=sum(r['skipped'] for r in values),shards=total,discovered_digest=digest,success=True,
            qt_shutdown=True,seconds_total=sum(r['seconds'] for r in values)))
    if not summaries:raise ValueError('No test reports')
    return summaries
