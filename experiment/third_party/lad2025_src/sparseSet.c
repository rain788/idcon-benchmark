// This software has been written by Christine Solnon.
// It is distributed under the CeCILL-B FREE SOFTWARE LICENSE
// see http://www.cecill.info/licences/Licence_CeCILL-B_V1-en.html for more details

typedef struct{
    int nb;   // current number of values in the sparse set
    int* val; // val[0..nb-1] = current values in the sparse set
    int* pos; // pos[v] = position of v in val, i.e., val[i] = v <=> pos[v] = i
} SparseSet;

void createSparseSet(SparseSet* s, int nbValues){
    // create the sparse set s that contains all values ranging from 0 to nbValues-1
    s->val = (int*)malloc(sizeof(int)*nbValues);
    s->pos = (int*)malloc(sizeof(int)*nbValues);
    for (int i = 0; i < nbValues; i++){
        s->val[i] = i;
        s->pos[i] = i;
    }
}

void removeValue(int v, SparseSet* s){
    // remove value v from sparse set s, i.e., exchange v with the last value in s
    s->nb--;
    s->val[s->pos[v]] = s->val[s->nb];
    s->pos[s->val[s->nb]] = s->pos[v];
    s->val[s->nb] = v;
    s->pos[v] = s->nb;
}

void removeAllValuesButOne(int v, SparseSet* s){
    // remove all values but v from s, i.e., exchange v with the first value in s
    s->val[s->pos[v]] = s->val[0];
    s->pos[s->val[0]] = s->pos[v];
    s->val[0] = v;
    s->pos[v] = 0;
    s->nb = 1;
}

void addValue(int v, SparseSet* s){
    // add v to s, i.e., exchange v with the value at pos nb
    s->val[s->pos[v]] = s->val[s->nb];
    s->pos[s->val[s->nb]] = s->pos[v];
    s->val[s->nb] = v;
    s->pos[v] = s->nb++;
}

void setPos(int v, int pos, SparseSet* s){
    // put v at position pos in s, i.e., exchange v with the value at position pos
    s->val[s->pos[v]] = s->val[pos];
    s->pos[s->val[pos]] = s->pos[v];
    s->val[pos] = v;
    s->pos[v] = pos;
}

bool isIn(int u, SparseSet* s){
    // return true if value u belongs to sparse set s
    return s->pos[u] < s->nb;
}

void print(SparseSet* s){
    // print all values in v on stdout
    for (int i=0; i<s->nb; i++) printf("%d ",s->val[i]);
    printf("\n");
}

