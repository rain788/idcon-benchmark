
void rewardClique(int i, int* tab, int* label, int* elabel, Tgraph* g){
    // tab[0..i-1] contains vertices of a clique of g
    // increment label[u] and elabel[e] for each vertex u and each edge e of the clique
     for (int j=0; j<i; j++){
        int u = tab[j];
        label[u]++;
        for (int k=j+1; k<i; k++)
            elabel[g->edgeId[u][tab[k]]]++;
    }
}

void computeCliques(Tgraph* g, bool isPattern, int i, int* tab, int label[cliqueLevel][g->nbVertices], int elabel[cliqueLevel][g->nbEdges], int* nb){
    // tab[0..i-1] contains a clique
    // extend it to all possible cliques of at most cliqueLevel+2 vertices greater than tab[i-1]
    // update label, elabel, and nb consequently
    int u, j, k, su;
    u = tab[i-1];
    j = firstGreaterSucc(u,g);
    if (j<0) return;
    for (; j<g->nbAdj[u]; j++){
        su=g->adj[u][j];
        if (!isPattern && mark[su]<tmark) continue;
        for (k=0; k<i-1 && g->edgeId[su][tab[k]]>=0; k++);
        if (k<i-1) continue;
        tab[i] = su;
        // tab[0..i] is a clique
        if (i>1){
            rewardClique(i+1,tab,label[i-2],elabel[i-2],g);
            nb[i-2]++;
        }
        if (i<cliqueLevel+1) computeCliques(g, isPattern, i+1, tab, label, elabel, nb);
    }
}

void searchCliques(int cliqueSize, int* clique, int nbCand, int* cand, int f){
    // clique[0..cliqueSize-1] contains a clique
    // cand[0..nbCand-1] contains every vertex which is connected to and greater than all vertices in clique
    nbNodes++;
    for (int i=0; i<nbCand && (!firstSol || !nbSol); i++){
        clique[cliqueSize] = cand[i];
        // clique[0..cliqueSize] is a clique
        if (cliqueSize+1 == Gp->nbVertices){
            if (firstSol){
                nbSol++;
                if (verbose > 1){
                    printf("Solution 1: ");
                    for (int u=0; u<Gp->nbVertices; u++)
                        printf("%d=%d ",u,clique[u]);
                    printf("\n");
                }
           } else {
                if (verbose > 1){
                    printf("Solution %d: ", nbSol+1);
                    for (int u=0; u<Gp->nbVertices; u++)
                        printf("%d=%d ",u,clique[u]);
                    printf("\n");
                    printf("Solutions %d to %d are permutations of solution %d\n", nbSol+2, nbSol+f, nbSol+1);
                }
                nbSol += f;
            }
            return;
        }
        int newCand[nbCand];
        int newNbCand = 0;
        for (int j=i+1; j<nbCand; j++){
            if (Gt->edgeId[cand[i]][cand[j]]>=0)
                newCand[newNbCand++] = cand[j];
        }
        if (newNbCand+cliqueSize+1 < Gp->nbVertices) continue;
        searchCliques(cliqueSize+1, clique, newNbCand, newCand, f);
    }
}

void cliquePattern(){
    // Gp is a clique -> search for cliques of Gp->nbVertices in Gt
    int clique[Gp->nbVertices];
    int cand[Gt->maxDegree];
    int f = 1;
    for (int i=2; i<=Gp->nbVertices; i++) f *= i;
    for (int v=0; v<Gt->nbVertices && (!firstSol || !nbSol); v++){
        if (Gt->nbAdj[v]+1<Gp->nbVertices) continue;
        int i = firstGreaterSucc(v,Gt);
        if (i>=0){
            int nbCand = Gt->nbAdj[v]-i;
            if (nbCand+1<Gp->nbVertices) continue;
            memcpy(cand, &(Gt->adj[v][i]), nbCand*sizeof(int));
            clique[0]=v;
            searchCliques(1, clique, nbCand, cand, f);
        }
    }
}

void cliqueTarget(){
    // Gt is a clique -> every subset of target vertices that has the same number of vertices as Gp (with loops and without loops) is a solution
    int nbLoops = 0;
    for (int u=0; u<Gp->nbVertices; u++)
        if (Gp->isLoop[u]) nbLoops++;
    if (nbLoops == 0){
        if (firstSol) nbSol = 1;
        else{
            printf("Target graph is a clique -> all permutations are solutions ");
            exit(0);
        }
        return;
    }
    int nbLoopsT = 0;
    for (int v=0; v<Gt->nbVertices; v++){
        if (Gt->isLoop[v]){
            nbLoopsT++;
            if (nbLoopsT == nbLoops){
                if (firstSol) nbSol = 1;
                else{
                    printf("Target graph is a clique -> all permutations are solutions ");
                    exit(0);
                }
                return;
            }
        }
    }
}

int computeCliqueMax(Tgraph* g, int nb, int nbCand, int* cand, int best, int max){
    // cand[0..nbCand-1] contains candidates to extend a clique of order nb
    if (nbCand == 0){
        if (best > nb) return best;
        return nb;
    }
    if (nb+1==max) return max;
    int newCand[nbCand-1];
    for (int j=0; j<nbCand; j++){
        int u = cand[j];
        int newNbCand = 0;
        for (int k=j+1; k<nbCand; k++){
            if (g->edgeId[u][cand[k]]>=0) newCand[newNbCand++] = cand[k];
        }
        if (nb+1+newNbCand>best){
            best = computeCliqueMax(g, nb+1, newNbCand, newCand, best, max);
            if (best == max) return max;
        }
    }
    return best;
}
