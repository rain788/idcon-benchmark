bool pos(int i, int j){
    // return true if decision at position j in branch i is positive
    return branch[i].val[j] >= 0;
}

bool neg(int i, int j){
    // return true if decision at position j in branch i is negative
    return branch[i].val[j] < 0;
}

bool satisfiable(int i, int j){
    // return true if decision at position j in branch i can be satisfied
    int u=branch[i].var[j];
    int v=branch[i].val[j];
    if (v>=0) return isIn(v, &dom[u]);
    v=-v-1;
    return dom[u].nb>1 || dom[u].val[0] != v;
}

bool satisfied(int i, int j){
    // return true if decision at position j in branch i is satisfied
    int u=branch[i].var[j];
    int v=branch[i].val[j];
    if (v>=0) return dom[u].nb==1 && dom[u].val[0]==v;
    return !isIn(-v-1, &(dom[u]));
}

bool satisfyNeg(int i, int j){
    // return true if the negative decision at position j in branch i can be satisfied
    // postrelation: if true is returned, then the negative decision at position j in branch i is satistied
    int u=branch[i].var[j];
    int v=-branch[i].val[j]-1;
    if (isIn(v,&(dom[u]))){
        if (dom[u].nb==1 || !filterValue(u,v) || (dom[u].nb==1 && !matchVertex(u)))
            return false;
    }
    return true;
}

bool propagateBranch(int i){
    // preconditions:
    // - the decision at position alpha[i] is positive
    // - every decision at position j in [0,alpha[i]-1] U [alpha[i]+1,beta[i-1] is satisfied
    if (!satisfiable(i, alpha[i])){ // all nogoods in branch[i] are satisfied
        alpha[i] = branch[i].size;
        removeValue(i, activeBranches);
        return true;
    }
    if (satisfied(i, alpha[i])){
        // satisfy all negative decisions between beta and the next unsatisfied positive decision
        while (beta[i]<branch[i].size && (neg(i, beta[i]) || satisfied(i, beta[i]))){
            if (neg(i, beta[i]) && !satisfyNeg(i, beta[i])) return false;
            beta[i]++;
        }
        alpha[i]=beta[i];
        if (alpha[i]==branch[i].size){
            removeValue(i, activeBranches);
            return true;
        }
        if (!satisfiable(i, alpha[i])){ // all nogoods in branch[i] are satisfied
            alpha[i] = branch[i].size;
            removeValue(i, activeBranches);
            return true;
        }
        beta[i]=alpha[i]+1;
   }
    // alpha = position of the first unsatisfied (yet satisfiable) positive decision
    // move forward beta to skip satisfied decisions
    while (beta[i]<branch[i].size && satisfied(i, beta[i])) beta[i]++;
    if (beta[i]==branch[i].size){
        alpha[i]=beta[i];
        removeValue(i, activeBranches);
        return true;
    }
    if (pos(i, beta[i])) return true; // no unsatisfied negative decision between alpha and beta
    // search for falsified negative decisions between beta and the next unsatisfied positive decision
    int j, u, v, count[Gp->nbVertices];
    tmark3++;
    for (j=beta[i]; j<branch[i].size && (neg(i, j) || satisfied(i, j)); j++){
        u=branch[i].var[j];
        v=-branch[i].val[j]-1;
        if (v>=0 && isIn(v,&dom[u])){
            if (mark3[u]<tmark3){
                count[u] = 1;
                mark3[u]=tmark3;
            }
            else count[u]++;
            if (count[u]==dom[u].nb){
                int uu=branch[i].var[alpha[i]];
                int vv=branch[i].val[alpha[i]];
                // remove vv from dom[uu] because if uu=vv then the domain of u will be emptied
                if (dom[uu].nb==1 || !filterValue(uu, vv) || (dom[uu].nb==1 && !matchVertex(uu)))
                    return false;
                alpha[i]=branch[i].size;
                removeValue(i, activeBranches);
                return true; // all nogoods in branch[i] are satisfied
            }
        }
    }
    return true;
}


bool propagateNoGoods(){
    for (int i=activeBranches->nb-1; i>=0; i--){
        if (!propagateBranch(activeBranches->val[i])) return false;
    }
    return true;
}

