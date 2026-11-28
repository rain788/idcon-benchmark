void prob(int* src, int n, int* dest){
    // dest[0..n-1] is a permutation of src[0..n-1] such that the probability that src[i] is before src[j] in dest is defined by p2[Gt->nbAdj[i]] and p2[Gt->nbAdj[j]]
    int cand[n];
    float p[n];
    float total = 0;
    for (int i=0; i<n; i++){
        cand[i] = src[i];
        p[i] = p2[Gt->nbAdj[cand[i]]];
        total += p[i];
    }
    int nbCand = n;
    for (int i=0; i<n-1; i++){
        float f = randFloat();
        float acc = p[0];
        int j = 0;
        while (acc/total < f && j<nbCand-1){
            j++;
            acc += p[j];
        }
        dest[i] = cand[j];
        cand[j] = cand[--nbCand];
        total -= p[j];
        p[j] = p[nbCand];
    }
    dest[n-1] = cand[0];
}

void savePartialAssignment(int nbUnassigned){
    // if the number of assigned variables in the current assignment is larger than the best partial assignment found so far
    // then save the current assignment in lastVal
    if (Gp->nbVertices - nbUnassigned >= bestSolSize){
        bestSolSize = Gp->nbVertices - nbUnassigned;
        for (int j=nbUnassigned; j<Gp->nbVertices; j++){
            int u = unassigned->val[j];
            if (Gp->nbAdj[u] > 0)
                lastVal[u] = dom[u].val[0];
        }
    }
}

void sortValues(int* val, int nextVar){
    // copy the domain of nextVar in val, and sort val wrt value ordering heuristic
    // choose first the value in the largest consistent assignment; randomly break ties wrt degree
    if (lastVal[nextVar]>=0 && isIn(lastVal[nextVar], &dom[nextVar])){
        val[0] = lastVal[nextVar];
        removeValue(lastVal[nextVar], &dom[nextVar]);
        prob(dom[nextVar].val, dom[nextVar].nb, &(val[1]));
        dom[nextVar].nb++;
    }
    else prob(dom[nextVar].val, dom[nextVar].nb, val);
}

float variableHeuristic(int u){
    if (FC){
        float h = 0;
        for (int j = 0; j < Gp->nbAdj[u]; j++)
            if (dom[Gp->adj[u][j]].nb > 1)
                h += weight[Gp->edgeId[u][Gp->adj[u][j]]]+1;
        return h /(float)dom[u].nb;
    }
    float h = weight[u];
    for (int j = 0; j < Gp->nbAdj[u]; j++)
        if (dom[Gp->adj[u][j]].nb > 1)
            h += weight[Gp->adj[u][j]];
    return h /(float)dom[u].nb;
}
