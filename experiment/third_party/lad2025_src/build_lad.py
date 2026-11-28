"""Reproducible domain/metric interface for official LAD2025 source.

Search, filtering levels, ordering and restarts remain native. Two unrestricted
clique shortcuts are disabled when domain restrictions are supplied.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent
SRC=ROOT/'LAD2025'; OUT=ROOT/'build/lad2025'
OUT.mkdir(parents=True,exist_ok=True)
for p in SRC.glob('*.c'):
    shutil.copy2(p,OUT/p.name)


def replace(path,old,new):
    s=path.read_text();assert s.count(old)==1,(path.name,old,s.count(old))
    path.write_text(s.replace(old,new))


replace(OUT/'main.c','#include "domains.c"','''
bool** egDomains = NULL;
bool** egEdges = NULL;
void loadExternalConstraints(){
    char* name = getenv("EG_LAD_CONSTRAINTS");
    if (!name) return;
    FILE* f = fopen(name,"r");
    int np,nt,count,v,r,s,u,w;
    if (!f || fscanf(f,"%d %d",&np,&nt)!=2 || np!=Gp->nbVertices || nt!=Gt->nbVertices) exit(2);
    egDomains = (bool**)malloc(np*sizeof(bool*));
    for (r=0;r<np;r++){
        egDomains[r]=(bool*)calloc(nt,sizeof(bool));
        if(fscanf(f,"%d",&count)!=1 || count<0 || count>nt) exit(2);
        for(int j=0;j<count;j++){
            if(fscanf(f,"%d",&v)!=1 || v<0 || v>=nt) exit(2);
            egDomains[r][v]=true;
        }
    }
    egEdges=(bool**)calloc(Gp->nbEdges,sizeof(bool*));
    int nm;
    if(fscanf(f,"%d",&nm)!=1 || nm<0) exit(2);
    for(int k=0;k<nm;k++){
        if(fscanf(f,"%d %d %d",&r,&s,&count)!=3 || r<0 || r>=np || s<0 || s>=np || Gp->edgeId[r][s]<0 || count<0) exit(2);
        int pe=Gp->edgeId[r][s];
        egEdges[pe]=(bool*)calloc(Gt->nbEdges,sizeof(bool));
        for(int j=0;j<count;j++){
            if(fscanf(f,"%d %d",&u,&w)!=2 || u<0 || u>=nt || w<0 || w>=nt || Gt->edgeId[u][w]<0) exit(2);
            egEdges[pe][Gt->edgeId[u][w]]=true;
        }
    }
    fclose(f);
}
#include "domains.c"''')
replace(OUT/'main.c','Gt = createGraph(fileNameGt);       // Target graph',
        'Gt = createGraph(fileNameGt);       // Target graph\n    loadExternalConstraints();')
replace(OUT/'main.c','if (Gt->isClique){ // special case where Gt is a clique',
        'if (Gt->isClique && !egDomains){ // unrestricted shortcut only')
replace(OUT/'main.c','if (Gp->isClique){ // special case where Gp is a clique',
        'if (Gp->isClique && !egDomains){ // unrestricted shortcut only')
replace(OUT/'domains.c','bool compatibleVertices(int u, int v){',
        'bool compatibleVertices(int u, int v){\n    if (egDomains && !egDomains[u][v]) return false;')
replace(OUT/'domains.c','bool isCompatible(int pe, int te){',
        'bool isCompatible(int pe, int te){\n    if (egEdges && egEdges[pe] && !egEdges[pe][te]) return false;')
subprocess.run(['gcc','-O3','-Wall','-fstrict-aliasing','-std=c99',str(OUT/'main.c'),'-o',str(OUT/'lad2025')],check=True)
record=dict(source_url='https://perso.citi-lab.fr/csolnon/LAD2025.tgz',
    archive_sha256=hashlib.sha256((ROOT/'LAD2025.tgz').read_bytes()).hexdigest(),
    original_sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in SRC.glob('*.c')},
    adapted_sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.c')},
    binary_sha256=hashlib.sha256((OUT/'lad2025').read_bytes()).hexdigest(),
    compiler=subprocess.check_output(['gcc','--version'],text=True).splitlines()[0],
    changes=['external vertex domains before filtering','edge metric compatibility in native edge checks',
             'disable domain-ignorant clique shortcuts under external constraints'],
    adapter='one fixed universal root eliminates isolated-role shortcut without removing original identities',
    performance='not yet measured; validation required')
(ROOT/'lad2025_provenance.json').write_text(json.dumps(record,indent=2),encoding='utf8')
print('LAD2025 built; original search preserved; domain/metric hooks recorded.',flush=True)
