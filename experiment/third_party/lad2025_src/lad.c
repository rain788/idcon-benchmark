// This software has been written by Christine Solnon.
// It is distributed under the CeCILL-B FREE SOFTWARE LICENSE
// see http://www.cecill.info/licences/Licence_CeCILL-B_V1-en.html for more details


bool addEdgeLAD(int u1, int u, int v, int* pmate, int* tmate, int* pred, int* fifo, int* nextIn){
    // for each target vertex vv:
    // - if mark[vv] < tmark0, then vv is free
    // - if tmark0 <= mark[vv] < tmark, then vv is not free and not marked
    // - if mark[vv] = tmark, then vv is not free and marked
    if (mark2[v]<tmark2){ // v is free => SAP found
        mark2[v]=tmark2;
        if (u1==u){
            tmate[v]=u;
            pmate[u]=v;
        }
        else{
            while (u != u1){
                int vv=pmate[u];
                pmate[u]=v;
                tmate[v]=u;
                v=vv;
                u=pred[v];
            }
            pmate[u1]=v;
            tmate[v]=u1;
        }
        return true;
    }
    // v is not free
    if (mark[v]<tmark){// v is not marked => add edge (u,v)
        pred[v]=u;
        fifo[(*nextIn)++]=v;
        mark[v]=tmark;
    }
    return false;
}


bool findSAP(int g1, int g, int b, int nbBoys, int* pmate, int* tmate){
    // return true if there exists an augmenting path starting from g1 and ending on a free boy in the bipartite graph G_(g,b)
    // update consequently pmate and tmate
    int fifo[nbBoys], pred[nbBoys];
    int nextIn = 0;
    int nextOut = 0;
    int i, b2, g2;
    tmark++;
    g2 = g1;
    while (true){
        if (dom[g2].nb <= Gt->nbAdj[b]){
            for (i=0; i<dom[g2].nb; i++){
                b2 = dom[g2].val[i];
                if (Gt->edgeId[b][b2]>=0 &&
                    isCompatible(Gp->edgeId[g][g2],Gt->edgeId[b][b2]) &&
                    addEdgeLAD(g1, g2, b2, pmate, tmate, pred, fifo, &nextIn))
                    return true;
            }
        }
        else{
            for (i=0; i<Gt->nbAdj[b]; i++){
                b2=Gt->adj[b][i];
                if (isIn(b2,&dom[g2]) &&
                    isCompatible(Gp->edgeId[g][g2],Gt->edgeId[b][b2]) &&
                    addEdgeLAD(g1, g2, b2, pmate, tmate, pred, fifo, &nextIn))
                    return true;
            }
        }
        if (nextOut == nextIn) return false;
        g2 = tmate[fifo[nextOut++]];
    }
}


bool checkLAD(int u, int v){
    // return true if G_(u,v) has an adj(u)-covering matching; false otherwise
    int u2, v2, i;
    // special case when u has only 1 adjacent node => no need to call Ford Fulkerson
    if (Gp->nbAdj[u]==1){
        u2 = Gp->adj[u][0]; // u2 is the only node adjacent to u
        v2 = lpmate[u][v][0];
        if (v2>=0 && isIn(v2,&(dom[u2]))) return true;
        // look for a support of edge (u,u2) for v
        if (dom[u2].nb <= Gt->nbAdj[v]){
            for (i=0; i<dom[u2].nb; i++){
                v2 = dom[u2].val[i];
                if (Gt->edgeId[v][v2]>=0 &&
                    isCompatible(Gp->edgeId[u][u2],Gt->edgeId[v][v2])){
                    lpmate[u][v][0]=v2;
                    return true;
                }
            }
            return false;
        }
        else{
            for (i=0; i<Gt->nbAdj[v]; i++){
                v2 = Gt->adj[v][i];
                if (isIn(v2, &dom[u2]) &&
                    isCompatible(Gp->edgeId[u][u2],Gt->edgeId[v][v2])){
                    lpmate[u][v][0]=v2;
                    return true;
                }
            }
            return false;
        }
    }
    // u has more than 1 adjacent node
    int fg=0;
    int llpmate[Gp->nbVertices], lltmate[Gt->nbVertices];
    int free[Gp->nbAdj[u]];
    tmark2++;
    for (i=0; i<Gp->nbAdj[u]; i++){
        // remove from the matching of G_(u,v) edges which no longer belong to G_(u,v)
        u2 = Gp->adj[u][i];
        v2 = lpmate[u][v][i];
        if ((v2<0) || (!isIn(v2,&(dom[u2])))) free[fg++]=u2;
        else{
            llpmate[u2]=v2;
            lltmate[v2]=u2;
            mark2[v2]=tmark2;
        }
    }
    if (fg == 0) return true;
    for (i=0; i<fg; i++){
        if (!findSAP(free[i], u, v, Gt->nbVertices, llpmate, lltmate)) return false;
    }
    for (i=0; i<Gp->nbAdj[u]; i++) lpmate[u][v][i]=llpmate[Gp->adj[u][i]];
    return true;
}
