// This software has been written by Christine Solnon.
// It is distributed under the CeCILL-B FREE SOFTWARE LICENSE
// see http://www.cecill.info/licences/Licence_CeCILL-B_V1-en.html for more details


bool addEdge(int u1, int u, int v, int* pred, int* fifo, int* nextIn){
    // this procedure is used in augmentingPath
    // if v is free, then update the current matching wrt the augmenting path
    // otherwise, if v is not already used, add edge (u,v) to the bipartite graph
    if (tmate[v]<0){ // v is free => SAP found
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
    if (mark[v]<tmark){// v is not free and not marked => add edge (u,v)
        pred[v]=u;
        fifo[(*nextIn)++]=v;
        mark[v]=tmark;
    }
    return false;
}


bool augmentingPath(int u, int nbV){
    // return true if there exists an augmenting path starting from u and ending on a free vertex v
    // in the bipartite directed graph G=(U,V,E) such that U=pattern nodes, V=target nodes, and
    // E={(u,v), v in D(u)} U {(v,u), pmate[u]=v}
    // update pmate and tmate consequently
    int fifo[nbV];
    int pred[nbV];
    int nextIn = 0;
    int nextOut = 0;
    int i, v, u2;
    v=pmate[u];
    if (v>=0){
        tmate[pmate[u]]=-1;
        pmate[u]=-1;
    }
    tmark++;
    for (i=0; i<dom[u].nb; i++){
        if (addEdge(u, u, dom[u].val[i], pred, fifo, &nextIn)) return true;
    }
    while (nextOut < nextIn){
        u2 = tmate[fifo[nextOut++]];
        for (i=0; i<dom[u2].nb; i++){
            if (addEdge(u, u2, dom[u2].val[i], pred, fifo, &nextIn)) return true;
        }
    }
    if (v>=0){
        pmate[u]=v;
        tmate[v]=u;
    }
    return false;
}


void traverse(int nbU, int nbV, int v, int* lifo, int* top, int* c, int* num, int* lowlink, int* sccU, int* sccV, int* nbSCC){
    num[v]=(*c); lowlink[v]=(*c); (*c)++;
    (*top)++; lifo[*top]=v;
    mark[v]=tmark;
    mark2[v]=tmark2;
    if (tmate[v]>=0){// v is not free
        int u=tmate[v];
        for (int i=0; i<dom[u].nb; i++){
            int w = dom[u].val[i];
            if (v != w){ // w is a successor of v
                if (mark2[w]<tmark2){
                    traverse(nbU, nbV, w, lifo, top, c, num, lowlink, sccU, sccV, nbSCC);
                    if (lowlink[w]<lowlink[v]) lowlink[v]=lowlink[w];
                }
                else if (mark[w]==tmark && num[w]<lowlink[v]) lowlink[v]=num[w];
            }
        }
    }
    else // v is free => the sink nbV is its only successor
        if (mark[nbV]==tmark && num[nbV]<lowlink[v]) lowlink[v]=num[nbV];
    if (lowlink[v]==num[v]){ // v is a root => compute its SCC
        (*nbSCC)++;
        if (lifo[*top]==v){
            sccV[v]=*nbSCC;
            (*top)--;
            mark[v]=0;
        }
        else{
            int w;
            do{
                w=lifo[*top];
                (*top)--;
                mark[w]=0;
                if (w<nbV){
                    sccV[w]=*nbSCC;
                    int u = tmate[w];
                    if (u>=0){
                        sccU[u]=*nbSCC;
                        mark3[u]=tmark3;
                    }
                }
            }while (w!=v);
        }
    }
}

int tarjan(int nbU, int nbV, int* sccU, int* sccV){
    // postrelation: sccV[v]==sccU[u] iff they belong to the same
    // strongly connected component in the bipartite graph Go=(U,V,E) such that
    // U = vertices of Gp
    // V = vertices of Gt
    // E = { (v,tmate[v]) / tmate[v]>=0 } U
    //     { (u,v) / v in D[u] and v != pmate[u]}
    // return the number of SCC
    int lifo[nbV+1];
    int top=0;
    int c=1;
    int num[nbV+1];
    int lowlink[nbV+1];
    int nbSCC=0, i, w;
    tmark2++;
    tmark3++;
    num[nbV]=0;
    lowlink[nbV]=0;
    lifo[0]=nbV;
    tmark++;
    mark[nbV]=tmark;
    for (i=0; i<unassigned->nb; i++){
        int w=pmate[unassigned->val[i]]; // w is a successor of the sink nbV
        if (mark2[w]<tmark2){
            traverse(nbU, nbV, w, lifo, &top, &c, num, lowlink, sccU, sccV, &nbSCC);
        }
    }
    if (nbSCC==0) return 1;
    nbSCC++;
    while (lifo[top]!=nbV){
        w=lifo[top]; top--;
        sccV[w]=nbSCC;
        if (tmate[w]>=0){
            sccU[tmate[w]]=nbSCC;
            mark3[tmate[w]]=tmark3;
        }
    }
    return nbSCC;
}


bool ensureGACallDiff(){
	// precondition: gmate is an all different matching of the pattern vertices
	// postcondition: filter domains wrt GAC(allDiff)
	//                return false if an inconsistency is detected; true otherwise
	int u, v, i, j, oldNbVal, nbToMatch;
	int numV[Gt->nbVertices+1], numU[Gp->nbVertices], toMatch[Gp->nbVertices];
    int nbSCC=tarjan(Gp->nbVertices,Gt->nbVertices,numU,numV);
    if (nbSCC==1 || (nbSCC==2 && Gp->nbVertices==Gt->nbVertices)) return true;
	// remove v from D[u] if u and v are not in the same SCC and gmate[u] != v
	nbToMatch = 0;
    for (j=0; j<unassigned->nb; j++){
        u=unassigned->val[j];
		oldNbVal=dom[u].nb;
		for (i=0; i<dom[u].nb; i++){
			v=dom[u].val[i]; // v in D(u)
            if ((mark3[u] < tmark3 || numV[v]!=numU[u]) && (pmate[u]!=v)){
                if (dom[u].nb==1 || !filterValue(u,v)) return false;
                i--;
            }
		}
		if ((oldNbVal>1) && (dom[u].nb==1)) toMatch[nbToMatch++] = u;
	}
	return matchVertices(nbToMatch, toMatch);
}
