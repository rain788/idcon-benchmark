"""Versioned extensions; the v1 implementation and accepted result snapshots remain untouched."""
import numpy as np
import networkx as nx
from inference import Problem

class ComplexProblem(Problem):
    def __init__(self,identity,cycle_filter=False):
        self.identity=identity;self.xyz=np.asarray(identity['candidate_xyz']);self.n=identity['role_count'];self.N=len(self.xyz)
        self.adj=np.zeros((self.N,self.N),bool)
        for a,b in identity['candidate_edges']:self.adj[a,b]=self.adj[b,a]=True
        self.lengths=np.linalg.norm(self.xyz[:,None,:]-self.xyz[None,:,:],axis=-1)
        self.compat={};self.neighbors=[[] for _ in range(self.n)]
        for r,s,length,implicit in identity['role_edges']:
            mat=self.adj.copy() if length is None else self.adj&(np.abs(self.lengths-length)<identity['length_tolerance'])
            self.compat[r,s]=mat;self.compat[s,r]=mat.T;self.neighbors[r].append(s);self.neighbors[s].append(r)
        self.domains=np.ones((self.n,self.N),bool)
        for r in range(self.n):self.domains[r]&=self.adj.sum(1)>=len(self.neighbors[r])
        for r,pos in identity['registered_positions'].items():self.domains[int(r)]&=np.max(np.abs(self.xyz-pos),axis=1)<identity['coordinate_tolerance']
        self.propagation_checks=0
        if cycle_filter:self.apply_cycle_filter()

    def apply_cycle_filter(self):
        """Necessary cycle-count conditions, derived from the same graph information. No gold ids."""
        host=nx.Graph();host.add_nodes_from(range(self.N));host.add_edges_from(self.identity['candidate_edges'])
        query=nx.Graph();query.add_nodes_from(range(self.n));query.add_edges_from((r,s) for r,s,_,_ in self.identity['role_edges'])
        def counts(g):
            node=np.zeros((len(g),4),int);edge={}
            for cyc in nx.simple_cycles(g,length_bound=6):
                k=len(cyc)
                if k<3:continue
                for u in cyc:node[u,k-3]+=1
                for u,v in zip(cyc,cyc[1:]+cyc[:1]):edge.setdefault(tuple(sorted((u,v))),np.zeros(4,int))[k-3]+=1
            return node,edge
        hc,he=counts(host);qc,qe=counts(query)
        for r in range(self.n):self.domains[r]&=np.all(hc>=qc[r],axis=1)
        for (r,s),need in qe.items():
            mat=self.compat[r,s].copy()
            for u,v in self.identity['candidate_edges']:
                if np.any(he.get(tuple(sorted((u,v))),np.zeros(4,int))<need):mat[u,v]=mat[v,u]=False
            self.compat[r,s]=mat;self.compat[s,r]=mat.T

def model_identity(identity):
    """Encoder input zero means no specified length, with explicit schema provenance retained."""
    return {**identity,'role_edges':[[r,s,0. if length is None else length,implicit] for r,s,length,implicit in identity['role_edges']]}

def legal(identity,mapping):
    if len(mapping)!=identity['role_count'] or len(set(mapping))!=len(mapping):return False
    xyz=np.array(identity['candidate_xyz']);edges={tuple(sorted(e)) for e in identity['candidate_edges']}
    for r,pos in identity['registered_positions'].items():
        if np.max(np.abs(xyz[mapping[int(r)]]-pos))>=identity['coordinate_tolerance']:return False
    for r,s,length,_ in identity['role_edges']:
        if tuple(sorted((mapping[r],mapping[s]))) not in edges:return False
        if length is not None and abs(np.linalg.norm(xyz[mapping[r]]-xyz[mapping[s]])-length)>=identity['length_tolerance']:return False
    return True
