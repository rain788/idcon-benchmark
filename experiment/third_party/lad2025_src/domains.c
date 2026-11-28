// This software has been written by Christine Solnon.
// It is distributed under the CeCILL-B FREE SOFTWARE LICENSE
// see http://www.cecill.info/licences/Licence_CeCILL-B_V1-en.html for more details

void printDomains(){
	int u;
	for (u=0; u<Gp->nbVertices; u++){
        if (Gp->nbAdj[u]>0){
            printf("D[%d] = ",u);
            if (isIn(u,unassigned)) printf("unassigned ");
            else printf("assigned ");
            print(&(dom[u]));
        }
        else if (Gp->isLoop[u]) printf("D[%d] = any non matched target vertex with a loop\n",u);
        else printf("D[%d] = any non matched target vertex\n",u);
	}
}

bool toFilterEmpty(){
	// return true if there is no more nodes in toFilter
	return (nextOutToFilter < 0);
}

void resetToFilter(){
    // empty toFilter and unmark the vertices that are marked to be filtered
	(tmarkedToFilter)++;
    nextOutToFilter = -1;
}

int nextToFilter(){
	// precondition: toFilterEmpty = false
	// remove a node from toFilter (FIFO)
	// unmark this node and return it
	int u = toFilter[nextOutToFilter];
	markedToFilter[u] = 0;
	if (nextOutToFilter == lastInToFilter) // u was the last node in tofilter
		nextOutToFilter = -1;
	else if (nextOutToFilter == Gp->nbVertices-1)
		nextOutToFilter = 0;
	else nextOutToFilter++;
	return u;
}

void addToFilter(int u){
	// if u is not marked, then add it to toFilter and mark it
	if (markedToFilter[u] == tmarkedToFilter) return;
	markedToFilter[u] = tmarkedToFilter;
	if (nextOutToFilter < 0){
		lastInToFilter = 0;
		nextOutToFilter = 0;
	}
	else if (lastInToFilter == Gp->nbVertices-1)
		lastInToFilter = 0;
	else lastInToFilter++;
	toFilter[lastInToFilter] = u;
}

bool augmentingPath(int u, int nbV); // function defined in allDiff.c

bool filterValue(int u, int v){
    // remove v from D(u) and add all successors of u in toFilter if !FC
    // return false if an inconsistency is detected wrt global all diff
    if (!FC) for (int j=0; j<Gp->nbAdj[u]; j++) addToFilter(Gp->adj[u][j]);
    // remove v from the domain of u
    removeValue(v, &(dom[u]));
    // update global matchings that support the global all different constraint
    if (pmate[u] == v) return augmentingPath(u, Gt->nbVertices);
    return true;
}

bool isCompatible(int pe, int te){
    if (egEdges && egEdges[pe] && !egEdges[pe][te]) return false;
    // return true if the pattern edge pe is compatible with the target edge te
    for (int i=0; i<cliqueLevel; i++)
        if (elabelP[pe][i]>elabelT[te][i]) return false;
    return true;
}

bool matchVertices(int nb, int* toBeMatched){
    // for each u in toBeMatched[0..nb-1], match u to val[firstVal[u]]
    // and filter domains of other non matched vertices wrt FC(Edges) and FC(diff)
    // (this is not mandatory when FC=false, as LAD is stronger than FC(Edges), but this speeds up the solution process).
    // return false if an inconsistency is detected by FC(Edges) or FC(diff); true otherwise;
    int j, u, v, u2, v2;
    while (nb>0){
        u = toBeMatched[--nb];
        removeValue(u, unassigned);
        v = dom[u].val[0];
        // match u to v
        for (u2=0; u2<Gp->nbVertices; u2++){
            if (u2==u || !isIn(u2, unassigned)) continue;
            if (dom[u2].nb == 1){ // special case where there is only one value v2 in dom[u2]
                v2 = dom[u2].val[0];
                if (v2 == v) return false;
                if (Gp->edgeId[u][u2] >= 0){
                    if (Gt->edgeId[v][v2]<0 || !isCompatible(Gp->edgeId[u][u2],Gt->edgeId[v][v2])){
                        if (FC) weight[Gp->edgeId[u][u2]] += 1;
                        else weight[u] += 1;
                        return false;
                    }
                }
                else if (Gp2[u][u2]>Gt2[v][v2]){
                    if (!FC) weight[u] += 1;
                    return false;
                }
                continue;
            }
            // There are more than 1 value in dom[u2]
            if (isIn(v, &(dom[u2])) && (!filterValue(u2,v))) return false;
            if (Gp->edgeId[u][u2] >= 0){// remove from dom[u2] vertices which are not adjacent to v
                for (j=dom[u2].nb-1; j>=0; j--){
                    v2 = dom[u2].val[j];
                    if (Gt->edgeId[v][v2]<0 || !isCompatible(Gp->edgeId[u][u2],Gt->edgeId[v][v2])){
                        if (dom[u2].nb == 1 || !filterValue(u2,v2)){
                            if (FC) weight[Gp->edgeId[u][u2]] += 1;
                            else weight[u] += 1;
                            return false;
                        }
                    }
                }
            }
            else if (Gp2[u][u2]>0){// remove from dom[u2] every vertex v2 st Gp2[u][u2] > Gt2[v][v2]
                for (j=dom[u2].nb-1; j>=0; j--){
                    v2 = dom[u2].val[j];
                    if (Gp2[u][u2]>Gt2[v][v2]){
                        if (dom[u2].nb==1 || !filterValue(u2,v2)){
                            if (!FC) weight[u] += 1;
                            return false;
                        }
                    }
                }
            }
            if (dom[u2].nb == 1) toBeMatched[nb++]=u2;
        }
    }
    return true;
}

bool matchVertex(int u){
    // match u to dom[u]->val[0]
    // and filter domains of other non matched vertices wrt FC(Edges) and FC(diff)
    // (this is not mandatory, as LAD is stronger than FC(Edges) and GAC(allDiff)
    // is stronger than FC(diff), but this speeds up the solution process).
    // return false if an inconsistency is detected by FC(Edges) or FC(diff); true otherwise;
    int toBeMatched[Gp->nbVertices];
    toBeMatched[0]=u;
    return matchVertices(1, toBeMatched);
}

bool assign(int u, int v){
    // remove all values but v from the domain of u and add all successors of u in toFilter if !FC
    // return false if an inconsistency is detected wrt to global all diff
    int j;
    // add all successors of u in toFilter
    if (!FC) for (j=0; j<Gp->nbAdj[u]; j++) addToFilter(Gp->adj[u][j]);
    // remove all values but v from the domain of u
    removeAllValuesButOne(v, &(dom[u]));
    // update global matchings that support the global all different constraint
    if (pmate[u]!=v && !augmentingPath(u,Gt->nbVertices)) return false;
    return matchVertex(u);
}

bool compatibleVertices(int u, int v){
    if (egDomains && !egDomains[u][v]) return false;
    // return true if u may be matched with v
    if (Gp->isLoop[u] && !Gt->isLoop[v]) return false;
    if (Gp->nbAdj[u] > Gt->nbAdj[v]) return false;
    return true;
}

bool inconsistent(int* pnb, int* tnb){
    // for each level l, pnb[l] and tnb[l] = number of cliques of order l+3 in Gp and Gt
    // return true if pnb[l] <= tnb[l] for every level l
    for (int i=0; i<cliqueLevel; i++)
        if (pnb[i]>tnb[i]) return true;
    return false;
}

bool inconsistentValue(int u, int v, int plabel[cliqueLevel][Gp->nbVertices], int tlabel[cliqueLevel][Gt->nbVertices]){
    // for each vertex u, and each level l, plabel[l][u] and tlabel[l][u] = number of cliques of order l+3 that contain u in Gp and Gt
    for (int i=0; i<cliqueLevel; i++)
        if (plabel[i][u]>tlabel[i][v]) return true;
    return false;
}

void computePaths2Gp(int v, int* mv, int** g2){
    // for each vertex v2 of Gp: set g2[v][v2] to the number of paths of length 2 between v and v2 in Gp
    // for each i in [0,Gp->maxDegree]: set mv[i] to the number of vertices v2 such that there are i paths of length 2 between v and v2
    g2[v] = (int*)calloc(Gp->nbVertices,sizeof(int));
    int i, sv, j, ssv;
    for (i=0; i<Gp->nbAdj[v]; i++){
        sv = Gp->adj[v][i];
        for (j=0; j<Gp->nbAdj[sv]; j++){
            ssv = Gp->adj[sv][j];
            if (ssv == v) continue;
            // there is a path of length 2 between v and ssv
            g2[v][ssv]++;
            if (g2[v][ssv] == 1) mv[1]++;
            else{
                mv[g2[v][ssv]-1]--;
                mv[g2[v][ssv]]++;
            }
        }
    }
}

void computePaths2Gt(int v, int* mv, int** g2){
    // for each vertex v2 of Gt: set g2[v][v2] to the number of paths of length 2 between v and v2 in Gt
    // for each i in [0,Gp->maxDegree-1]: set mv[i] to the number of vertices v2 such that there are i paths of length 2 between v and v2
    // set mv[Gp->maxDegree] to the number of vertices v2 such that there are at least Gp->maxDegree paths of length 2 between v and v2
    g2[v] = (int*)calloc(Gt->nbVertices,sizeof(int));
    int i, sv, j, ssv;
    for (i=0; i<Gt->nbAdj[v]; i++){
        sv = Gt->adj[v][i];
        if (mark[sv]<tmark) continue; // sv cannot be matched to any pattern vertex
        for (j=0; j<Gt->nbAdj[sv]; j++){
            ssv = Gt->adj[sv][j];
            if (ssv == v || mark[ssv]<tmark) continue;
            // there is a path of length 2 between v and ssv
            g2[v][ssv]++;
            if (g2[v][ssv] == 1) mv[1]++;
            else{
                if (g2[v][ssv] > Gp->maxDegree) mv[Gp->maxDegree]++;
                else{
                    mv[g2[v][ssv]-1]--;
                    mv[g2[v][ssv]]++;
                }
            }
        }
    }
}


bool initDomains(){
    // For every pattern node u, initialize the domain of u with every vertex v so that for every neighbor u'
    // of u there exists a different neighbor v' of v such that degree(u) <= degree(v)
    // Filter domains wrt paths of length 2
    // If cliqueLevel>0, then filter domains wrt cliques of order cliqueLevel+2
	// return false if a domain is empty and true otherwise
    origCliqueLevel = cliqueLevel;
	int val[Gt->nbVertices];
    int u, v, i, j, total;
    int mu[Gp->maxDegree+1];
    int mv[Gt->nbVertices][Gp->maxDegree+1];
    tmark++;
    // initialise mv[v][i] to the number of vertices adjacent to v and of degree i
    memset(mv,0,(Gp->maxDegree+1)*Gt->nbVertices*sizeof(int));
    for (v=0; v<Gt->nbVertices; v++){
        for (i=0; i<Gt->nbAdj[v]; i++){
            if (Gt->nbAdj[Gt->adj[v][i]] < Gp->maxDegree) mv[v][Gt->nbAdj[Gt->adj[v][i]]]++;
            else mv[v][Gp->maxDegree]++;
        }
    }
    for (u=0; u<Gp->nbVertices; u++){
        if (Gp->nbAdj[u]==0 && !Gp->isLoop[u]){
            // u is an isolated vertex that may be matched with any non matched target vertex
            removeValue(u, unassigned);
            continue;
        }
        lpmate[u] = (int**)malloc(sizeof(int*)*Gt->nbVertices);
        addToFilter(u);
        dom[u].pos = (int*)malloc(sizeof(int)*Gt->nbVertices);
        dom[u].nb = 0;
        memset(mu,0,(Gp->maxDegree+1)*sizeof(int));
        for (i=0; i<Gp->nbAdj[u]; i++) mu[Gp->nbAdj[Gp->adj[u][i]]]++;
        for (v=0; v<Gt->nbVertices; v++){
            if (compatibleVertices(u, v)){
                total = 0;
                for (j=Gp->maxDegree; (j && (total >=0)); j--) total += mv[v][j] - mu[j];
                if (total >= 0){ // v is in the domain of u
                    mark[v] = tmark;
                    dom[u].pos[v] = dom[u].nb;
                    val[(dom[u].nb)++] = v;
                    lpmate[u][v] = (int*)malloc(sizeof(int)*Gp->nbAdj[u]);
                    memset(lpmate[u][v], -1, sizeof(int)*Gp->nbAdj[u]);
                }
                else dom[u].pos[v] = Gt->nbVertices;
            }
            else dom[u].pos[v] = Gt->nbVertices;
        }
        if (dom[u].nb==0) return 0; // the domain of u is empty
        dom[u].val = (int*)malloc(sizeof(int)*dom[u].nb);
        memcpy(dom[u].val, val, sizeof(int)*dom[u].nb);
    }
    // compute paths of length 2
    Gt2 = (int**)malloc(Gt->nbVertices*sizeof(int*));
    memset(mv,0,(Gp->maxDegree+1)*Gt->nbVertices*sizeof(int));
    for (v=0; v<Gt->nbVertices; v++){
        if (mark[v]==tmark && Gt->nbAdj[v]>0) computePaths2Gt(v, mv[v], Gt2);
    }
    Gp2 = (int**)malloc(Gp->nbVertices*sizeof(int*));
    for (u=0; u<Gp->nbVertices; u++){
        if (Gp->nbAdj[u]==0) continue;
        memset(mu,0,(Gp->maxDegree+1)*sizeof(int));
        computePaths2Gp(u, mu, Gp2);
        for (i=dom[u].nb-1; i>=0; i--){
            v = dom[u].val[i];
            total = 0;
            for (j=Gp->maxDegree; (j && (total >=0)); j--) total += mv[v][j] - mu[j];
            if (total < 0){
                if (dom[u].nb == 1) return false;
                removeValue(v, &dom[u]);
            }
        }
    }
    if (cliqueLevel == 0) return true;
    // compute cliques in Gp
    // for each vertex u, and each level l in [0,cliqueLevel[, plabel[l][u] = number of cliques of order l+3 that contain u
    // for each edge e, and each level l in [0,cliqueLevel[, pelabel[l][e] = number of cliques of order l+3 that contain e
    // for each level l in [0,cliqueLevel[, pnb[l] = number of cliques of order l+3
    int plabel[cliqueLevel][Gp->nbVertices], pelabel[cliqueLevel][Gp->nbEdges], pnb[cliqueLevel], clique[2+cliqueLevel];
    for (i=0; i<cliqueLevel; i++){
        memset(plabel[i], 0, Gp->nbVertices*sizeof(int));
        memset(pelabel[i], 0, Gp->nbEdges*sizeof(int));
        pnb[i]=0;
    }
    for (u=0; u<Gp->nbVertices; u++){
        if (Gp->nbAdj[u] < 2) continue;
        clique[0]=u;
        computeCliques(Gp, true, 1, clique, plabel, pelabel, pnb);
    }
    if (pnb[0]==0){// no clique of order 3 in Gp => no need to search for cliques in Gt
        cliqueLevel = 0;
        return true;
    }
    int tlabel[cliqueLevel][Gt->nbVertices], telabel[cliqueLevel][Gt->nbEdges], tnb[cliqueLevel];
    // search for cliques in Gt
    for (i=0; i<cliqueLevel && pnb[i]>0; i++){
        memset(tlabel[i], 0, Gt->nbVertices*sizeof(int));
        memset(telabel[i], 0, Gt->nbEdges*sizeof(int));
        tnb[i] = 0;
    }
    cliqueLevel = i; // no need to compute cliques of order greater than the largest pattern clique
    for (v=0; v<Gt->nbVertices; v++){
        if (mark[v]<tmark) continue; // v cannot be matched to any pattern vertex
        if (Gt->nbAdj[v] < 2) continue; // v cannot belong to a clique of order >= 3
        clique[0]=v;
        computeCliques(Gt, false, 1, clique, tlabel, telabel, tnb);
    }
    if (inconsistent(pnb, tnb)) return false;
    for (u=0; u<Gp->nbVertices; u++){ // filter the domain of u
        if (Gp->nbAdj[u]<2 || plabel[0][u] == 0) continue;
        for (j=dom[u].nb-1; j>=0; j--){
            v = dom[u].val[j];
            if (inconsistentValue(u, v, plabel, tlabel)){
                if (dom[u].nb == 1) return false;
                removeValue(v, &dom[u]);
            }
        }
    }
    elabelP = (int**)malloc(Gp->nbEdges*sizeof(int*));
    elabelT = (int**)malloc(Gt->nbEdges*sizeof(int*));
    for (i=0; i<Gp->nbEdges; i++){
        elabelP[i] = (int*)malloc(cliqueLevel*sizeof(int));
        elabelT[i] = (int*)malloc(cliqueLevel*sizeof(int));
        for (j=0; j<cliqueLevel; j++){
            elabelP[i][j] = pelabel[j][i];
            elabelT[i][j] = telabel[j][i];
        }
    }
    for (i=Gp->nbEdges; i<Gt->nbEdges; i++){
        elabelT[i] = (int*)malloc(cliqueLevel*sizeof(int));
        for (j=0; j<cliqueLevel; j++) elabelT[i][j] = telabel[j][i];
    }
	return true;
}


bool filterMaxClique(){
    // remove from dom[u] every target vertex v such that u belongs to a larger clique than v
    if (cliqueLevel<origCliqueLevel) return true; // there is no clique larger than 2+cliqueLevel in Gp
    int max = 0;
    int pmaxClique[Gp->nbVertices];
    int tmaxClique[Gt->nbVertices];
    int u, j, v;
    for (u=0; u<Gp->nbVertices; u++){
        pmaxClique[u] = 0;
        if (Gp->nbAdj[u]<2) continue;
        int cand[Gp->nbAdj[u]];
        memcpy(cand, Gp->adj[u], Gp->nbAdj[u]*sizeof(int));
        pmaxClique[u] = computeCliqueMax(Gp, 1, Gp->nbAdj[u], cand, 2, Gp->nbVertices);
        if (pmaxClique[u] > max) max = pmaxClique[u];
    }
    if (max == cliqueLevel+2) return true;
    memset(tmaxClique, 0, Gt->nbVertices*sizeof(int));
    for (u=0; u<Gp->nbVertices; u++){
        if (pmaxClique[u] <= cliqueLevel+2) continue;
        for (j=dom[u].nb-1; j>=0; j--){
            v = dom[u].val[j];
            if (Gt->nbAdj[v]<pmaxClique[u]-1){
                if (dom[u].nb == 1) return false;
                removeValue(v, &dom[u]);
                continue;
            }
            if (tmaxClique[v] == 0){
                int cand[Gt->nbAdj[v]];
                memcpy(cand, Gt->adj[v], Gt->nbAdj[v]*sizeof(int));
                tmaxClique[v] = computeCliqueMax(Gt, 1, Gt->nbAdj[v], cand, cliqueLevel+2, max);
            }
            if (pmaxClique[u] > tmaxClique[v]){
                if (dom[u].nb == 1) return false;
                removeValue(v, &dom[u]);
            }
        }
    }
    return true;
}
