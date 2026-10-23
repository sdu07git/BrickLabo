"""Resolve bounded groups of exact identities using the existing unique index."""


def items_by_reference(c,identities):
    values=list(dict.fromkeys(identities));result={}
    for start in range(0,len(values),128):
        batch=values[start:start+128]
        sql='WITH wanted(source,kind,ref) AS (VALUES '+','.join('(?,?,?)' for _ in batch)+') SELECT i.* FROM wanted w JOIN items i ON i.source=w.source AND i.kind=w.kind AND i.ref=w.ref'
        for row in c.execute(sql,[v for identity in batch for v in identity]):result[(row['source'],row['kind'],row['ref'])]=dict(row)
    return result
