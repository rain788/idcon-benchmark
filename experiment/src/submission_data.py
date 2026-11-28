"""Method-blind, single-draw confirmation input generator.

No EG-ICAF imports, solver results, acceptance-by-performance, or test tuning.
Real graph topology and constructed unary predicates are labelled separately.
"""
import collections,gzip,hashlib,json,random,urllib.request
from pathlib import Path
import networkx as nx
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/processed/submission_confirmation'
RAW=ROOT/'data/raw/submission_graphs'
SEED=202611020731
FAMILIES=['geometric','preferential','small_world','regular','erdos','articulation_modules']
SOURCES={
 'ca-GrQc':'https://snap.stanford.edu/data/ca-GrQc.txt.gz',
 'email-Eu-core':'https://snap.stanford.edu/data/email-Eu-core.txt.gz',
 'wiki-Vote':'https://snap.stanford.edu/data/wiki-Vote.txt.gz',
 'p2p-Gnutella04':'https://snap.stanford.edu/data/p2p-Gnutella04.txt.gz'}
SCENARIOS=['all_s','single_role_violation','missing_evidence','distributed_violation']

def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')

def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def acquire():
    RAW.mkdir(parents=True,exist_ok=True);meta={}
    for name,url in SOURCES.items():
        p=RAW/(name+'.txt.gz')
        if not p.exists():
            with urllib.request.urlopen(url,timeout=45) as response:p.write_bytes(response.read())
        # Reject HTML/errors rather than silently substituting a source.
        with gzip.open(p,'rt') as f:
            lines=sum(1 for x in f if x.strip() and not x.startswith('#'))
        meta[name]=dict(url=url,sha256=sha(p),edge_lines=lines)
    dump(RAW/'sources.json',meta)

def graph(family,n,seed,density=1):
    # density=1 reproduces every v1/R1 host exactly; revision R2 (IdCon-Hard-X)
    # uses density=2, which doubles the mean degree of every family.
    d=int(density)
    if family=='geometric':g=nx.random_geometric_graph(n,2.2*(d**.5)/(n**.5),seed=seed)
    elif family=='preferential':g=nx.barabasi_albert_graph(n,2*d,seed=seed)
    elif family=='small_world':g=nx.watts_strogatz_graph(n,4*d,.18,seed=seed)
    elif family=='regular':g=nx.random_regular_graph(4*d,n,seed=seed)
    elif family=='erdos':g=nx.fast_gnp_random_graph(n,4.5*d/n,seed=seed)
    else:
        # Independent random communities joined through a genuine articulation,
        # not copied query motifs or solver-selected Hall-deficient examples.
        g=nx.Graph();g.add_node(0)
        parts=4;offset=1
        for j in range(parts):
            size=(n-1)//parts+(j<(n-1)%parts)
            h=nx.barabasi_albert_graph(size,2*d,seed=seed+j+1)
            h=nx.relabel_nodes(h,{u:u+offset for u in h})
            g=nx.compose(g,h);g.add_edge(0,offset);offset+=size
    return nx.convert_node_labels_to_integers(g)

def bfs_nodes(g,start,count,rng):
    seen={start};order=[start];queue=collections.deque([start])
    while queue and len(order)<count:
        u=queue.popleft();neighbors=sorted(g[u]);rng.shuffle(neighbors)
        for v in neighbors:
            if v in seen:continue
            seen.add(v);order.append(v);queue.append(v)
            if len(order)==count:break
    # Disconnected nodes are retained by a fixed rule; no draw is rejected.
    if len(order)<count:
        rest=sorted(set(g)-seen);rng.shuffle(rest);order.extend(rest[:count-len(order)])
    return order

def make_identity(g,index,rng,source_ids=None):
    n=len(g);k=[6,10,16,24][index%4];k=min(k,n)
    planted=index%4!=3
    if planted:
        selected=bfs_nodes(g,rng.randrange(n),k,rng)
        q=g.subgraph(selected).copy()
        # Half of extracted queries use a BFS forest, half retain all edges.
        if index%2==0:
            forest=nx.Graph();forest.add_nodes_from(selected)
            for comp in nx.connected_components(q):
                forest.add_edges_from(nx.bfs_edges(q,min(comp)))
            q=forest
        q=nx.relabel_nodes(q,dict(zip(selected,range(k))))
    else:
        q=nx.gnp_random_graph(k,min(.55,3.8/max(1,k-1)),seed=rng.randrange(2**31))
        selected=rng.sample(range(n),k)
    # Variable anchor count creates connected and decomposable queries without
    # selecting instances based on the algorithm's block/cut behavior.
    ac=[0,1,2][(index//4)%3]
    anchor_roles=sorted(q,key=lambda r:(-q.degree[r],r))[:ac]
    coords=[[float(u),float((u*u)%104729),float(u%7)] for u in range(n)]
    metric=index%6==5 and planted
    edges=[]
    for r,s in sorted(q.edges()):
        length=float(np.linalg.norm(np.asarray(coords[selected[r]])-coords[selected[s]])) if metric and rng.random()<.25 else None
        edges.append([r,s,length,False])
    identity=dict(candidate_xyz=coords,candidate_edges=[list(e) for e in sorted(g.edges())],
        role_count=k,role_edges=edges,registered_positions={str(r):coords[selected[r]] for r in anchor_roles},
        coordinate_tolerance=1e-8,length_tolerance=1e-7,domain_complete=True,injective=True)
    free=sorted(set(range(k))-set(anchor_roles));checks=rng.sample(free,min(len(free),[2,4,8][index%3]))
    return identity,checks,dict(query_rule='extracted' if planted else 'independent_random',
        anchor_roles=anchor_roles,metric=metric,source_nodes=source_ids or list(range(n)))

def generate():
    if (DATA/'manifest.json').exists():raise FileExistsError('Frozen inputs already exist')
    rng=random.Random(SEED);pairs=[]
    for family in FAMILIES:
        for index in range(12):
            n=[48,120,300,600][index%4]
            pairs.append((family,index,graph(family,n,rng.randrange(2**31)),None,'synthetic',None))
    sources=read(RAW/'sources.json')
    for name in SOURCES:
        g=nx.Graph()
        with gzip.open(RAW/(name+'.txt.gz'),'rt') as f:
            for line in f:
                if not line.strip() or line.startswith('#'):continue
                a,b=map(int,line.split()[:2])
                if a!=b:g.add_edge(a,b)
        nodes=sorted(g)
        for index in range(6):
            chosen=bfs_nodes(g,rng.choice(nodes),[120,300,600][index%3],rng)
            h=nx.relabel_nodes(g.subgraph(chosen),dict(zip(chosen,range(len(chosen)))))
            pairs.append((name,index,h,chosen,'external_topology',sources[name]))
    records=[];ancestors=[];hashes={}
    for family,index,g,nodeids,nature,source in pairs:
        gid=f'sc_{family}_{index:02d}';identity,checks,detail=make_identity(g,index,rng,nodeids)
        ancestor=dict(group_id=gid,family=family,dataset=nature,independent_source=family if nature=='external_topology' else gid,
            role_count=identity['role_count'],candidates=len(g),checked_roles=checks,source=source,**detail)
        ancestors.append(ancestor)
        for scene in SCENARIOS:
            tid=gid+'__'+scene;n=len(g);tables={r:[0]*n for r in checks}
            if scene=='single_role_violation':tables[checks[0]]=[2 if rng.random()<.2 else 0 for _ in range(n)]
            if scene=='missing_evidence':tables[checks[0]]=[1 if rng.random()<.2 else 0 for _ in range(n)]
            if scene=='distributed_violation':tables={r:[2 if rng.random()<.2 else 0 for _ in range(n)] for r in checks}
            ip=DATA/'identities'/(gid+'.json');tp=DATA/'tables'/(tid+'.json')
            if not ip.exists():dump(ip,identity)
            dump(tp,dict(role_states=tables,global_state=0))
            records.append(dict(task_id=tid,group_id=gid,family=family,dataset=nature,independent_source=ancestor['independent_source'],
                scenario=scene,identity_file=ip.relative_to(ROOT).as_posix(),tables_file=tp.relative_to(ROOT).as_posix()))
            hashes[tid]=dict(identity=sha(ip),tables=sha(tp))
    dump(DATA/'ancestors.json',ancestors);dump(DATA/'manifest.json',records);dump(DATA/'input_hashes.json',hashes)
    print('GENERATED',len(ancestors),'ancestors',len(records),'tasks; external sources',len(SOURCES),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['acquire','generate']);globals()[p.parse_args().phase]()
