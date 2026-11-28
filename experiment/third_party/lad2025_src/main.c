// This software has been written by Christine Solnon.
// It is distributed under the CeCILL-B FREE SOFTWARE LICENSE
// see http://www.cecill.info/licences/Licence_CeCILL-B_V1-en.html for more details

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <getopt.h>
#include <sys/time.h>
#include <sys/resource.h>
#include <limits.h>
#include <signal.h>

// define boolean type as char
#define true 1
#define false 0
#define bool char

#include "sparseSet.c"

typedef struct{
    bool* isLoop; // isLoop[i] = true if there is a loop on vertex i
    int nbVertices; // Number of vertices
    int nbEdges; // Number of edges
    int maxDegree;  // max_{0<=i<nbVertices} nbAdj[i]
    int* nbAdj;    // nbAdj[i] = number of vertices j such that (i,j) or (j,i) is an edge
    int** adj;     // forall j in [0..nbAdj[i]-1], adj[i][j] = jth vertex adjacent to i
    int** edgeId; // if (i,j) is an edge, then edgeId[i][j] = id of edge (i,j); otherwise edgeId[i][j] = - min_k>j (i,k) is an edge
    bool isClique;
} Tgraph;

typedef struct{
    int size; // number of decisions in the branch
    int* var; // forall i in [0..size-1], var[i]=variable involved in the ith decision
    int* val; // forall i in [0..size-1], if val[i]>=0, then the ith decision is var[i]=val[i]
              // otherwise, the ith decision is var[i]!=-val[i]
} Tbranch;

// Parameters
bool firstSol;        // true if search stop at first solution; false if search for all solutions
char verbose;         // level of verbosity (from 0 to 2)
int timeLimit;        // time limit
int cliqueLevel;      // 0=no clique computation; i=computation of cliques of order i+2
int nbMaxFail;        // cutoff limit for restarting search
float ratio;          // ratio of the geometric progression used for increasing nbMaxFail
int filteringLevel;   // 0=LAD; 1=FC 2=adaptative

// Global variables
struct rusage ru;     // reusable structure to get CPU time usage
int nbNodes = 1;      // number of nodes in the search tree
int nbFail = 0;       // number of failed nodes in the search tree
int nbSol = 0;        // number of solutions found
int* toFilter;        // contain all pattern nodes whose domain should be filtered
int nextOutToFilter;  // position in toFilter of the next pattern node whose domain should be filtered (-1 if no domain to filter)
int lastInToFilter;   // position in toFilter of the last pattern node whose domain should be filtered
unsigned int* markedToFilter;   // For each pattern node u, markedToFilter[u]=last time u was in toFilter
unsigned int tmarkedToFilter; // current time for toFilter
unsigned long* mark;  // mark[v]=last time v was marked
unsigned long* mark2; // mark2[v]=last time v was marked
unsigned long* mark3; // mark3[u]=last time u was marked (for SCC)
unsigned long tmark;  // current time for mark
unsigned long tmark2; // current time for mark2
unsigned long tmark3; // current time for mark3
SparseSet* unassigned;// set of unassigned variables
SparseSet* dom;       // For each pattern node u, dom[u] = domain of u
Tgraph* Gp;           // Pattern graph
Tgraph* Gt;           // Target graph
int* pmate;           // For each pattern node u, pmate[u] = node of Gt matched to u in GAD
int* tmate;           // For each target node v, tmate[v] = node of Gp matched to v in GAD or -1 if v is not matched
int*** lpmate;        // lpmate[u][v][i] = node of Gt matched with adj[u][i] in the bipartite graph G_{u,v}
int nbMaxBranches = 1000; // max number of restarts
bool FC;               // true if filtering=FC; false if filtering=LAD

// Global variables used for computing supplemental labels
int** Gt2;             // Gt2[v1][v2] = number of paths of length 2 between v1 and v2 in Gt
int** Gp2;             // Gp2[u1][u2] = number of paths of length 2 between u1 and u2 in Gp
int origCliqueLevel;   // initial value of cliqueLevel
int** elabelP; // for i in [1,cliqueLevel] and e in [0..Gp->nbEdges[, elabelP[i-1][e] = number of cliques of order i+2 in Gp
int** elabelT; // for i in [1,cliqueLevel] and e in [0..Gt->nbEdges[, elabelT[i-1][e] = number of cliques of order i+2 in Gt

// Global variables used for ordering heuristics
float* p2; // forall i in [1,Gt->maxDegree], p2[i] = 2^{i-1}
int* lastVal; // forall u in [0,Gp->nbVertices-1], lastVal[u] = last target vertex assigned to u in the largest partial assignment found so far
int bestSolSize = 0; // number of assigned variables in the largest partial assignment found so far
float* weight; // if FC, then forall i in [0,Gp->nbEdges-1], weight[i] = number of failures raised when propagating the ith edge constraint
               // otherwise, forall u in [0,Gp->nbVertices-1], weight[u] = number of failures raised when propagating LAD(u)

// Global variables used for restarts
SparseSet* activeBranches;
int nbBranches = 0;
Tbranch* branch; // for 0<=i<nbBranches, branch[i]=sequence of decisions of the right most branch of the search tree just before the ith restart
int* alpha; // for 0<=i<nbBranches, for 0<=j<alpha[i], the jth decision in branch[i] is satisfied and decision at position alpha[i] is positive
int* beta; // for 0<=i<nbBranches, for alpha[i]<j<beta[i], the jth decision in branch[i] is satisfied

#include "graph.c"
#include "clique.c"

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
#include "domains.c"
#include "allDiff.c"
#include "lad.c"
#include "random.c"
#include "nogoods.c"
#include "heuristic.c"


bool filter(){
    // filter domains of all vertices in toFilter wrt LAD and ensure the DC of GAD
    // return false if some domain becomes empty (and increase weight consequently); true otherwise
    int i, u, v;
    while (!toFilterEmpty()){
        while (!toFilterEmpty()){
            u = nextToFilter();
            if (isIn(u, unassigned)){
                i = 0;
                while (i < dom[u].nb){
                    v = dom[u].val[i]; // v is in D(u) -> check if G_(u,v) has a covering matching
                    if (checkLAD(u, v)) i++;
                    else if (dom[u].nb == 1 || !filterValue(u, v)){
                        weight[u] += 1;
                        return false;
                    }
                }
                if (dom[u].nb == 1 && !matchVertex(u)){
                    weight[u] += 1;
                    return false;
                }
            }
        }
        if (!ensureGACallDiff()) return false;
    }
    return true;
}

void printSolution(){
    printf("Solution %d: ",nbSol);
    for (int u=0; u<Gp->nbVertices; u++){
        if (Gp->nbAdj[u]==0 && !Gp->isLoop[u]) printf("%d=? ",u);
        else printf("%d=%d ",u,dom[u].val[0]);
    }
    printf("\n");
}

void checkSolution(){
    if (Gt->isClique || Gp->isClique) return; // treated as special cases in clique.c
    // check that the current solution is correct (to be used when debugging...)
    for (int u=0; u<Gp->nbVertices; u++){
        for (int i=0; i<Gp->nbAdj[u]; i++){
            int u2 = Gp->adj[u][i];
            if (Gt->edgeId[dom[u].val[0]][dom[u2].val[0]] < 0)
                printf("Incorrect solution: (%d,%d) is a pattern edge but (%d,%d) is not a target\n",
                       u, u2, dom[u].val[0], dom[u2].val[0]);
        }
    }
}


bool solve(int level){
    // The current node of the search tree is consistent wrt to LAD and GAD
    // Perform an n-ary search where each node has one child per value in the variable domain
    // return false if the number of fail limit is exceeded before the search is completed
    // return true otherwise

    nbNodes++;

    if (unassigned->nb == 0){// All vertices are matched => Solution found
        nbSol++;
        if (verbose >= 1) printSolution();
        resetToFilter();
        return true;
    }
    if (verbose >= 2) printDomains();

    int nbUnassigned = unassigned->nb;
    int nbActiveBranches = activeBranches->nb;
    int i, j, u, v, nbVal[Gp->nbVertices], saveAlpha[nbBranches], saveBeta[nbBranches];
    int nextVar = -1;
    int first = getNextRand(nbUnassigned);
    float h, bestH = -1;

    // Save domain sizes and search for nextVar to branch on
    for (i = 0; i < nbUnassigned; i++){
        u = unassigned->val[(i+first)%nbUnassigned];
        nbVal[u] = dom[u].nb;
        h = variableHeuristic(u);
        if (h > bestH){
            bestH = h;
            nextVar = u;
        }
    }

    // save alpha and beta for recorded nogoods
    memcpy(saveAlpha, alpha, nbBranches*sizeof(int));
    memcpy(saveBeta, beta, nbBranches*sizeof(int));
    // save and sort the domain of nextVar to iterate on its values
    int val[dom[nextVar].nb];
    sortValues(val, nextVar);

    // branch on nextVar=v, for every target node v in val
    for(i=0; i<nbVal[nextVar] && (!firstSol || !nbSol); i++){
        v = val[i];
        if (verbose == 2) printf("Create search node %d=%d\n",nextVar,v);
        if (!assign(nextVar, v) || (!FC && !filter()) || !propagateNoGoods()){
            if (verbose == 2) printf("Inconsistency detected while matching %d to %d\n",nextVar,v);
            nbNodes++;
            nbFail++;
            resetToFilter();
            if (!FC) weight[nextVar] += 1;
            savePartialAssignment(nbUnassigned);
            if (nbFail >= nbMaxFail && nbBranches < nbMaxBranches && i < nbVal[nextVar]-1){
                // save the right most branch of the search tree before restarting search
                branch[nbBranches].size = level+i+1;
                branch[nbBranches].var = (int*)malloc((level+i+1)*sizeof(int));
                branch[nbBranches].val = (int*)malloc((level+i+1)*sizeof(int));
                for (j=0; j<=i; j++){ // save the decision "nextVar != val[j]"
                    branch[nbBranches].var[level+j] = nextVar;
                    branch[nbBranches].val[level+j] = -val[j]-1;
                }
                return false;
            }
        }
        else if (!solve(level+1+i)){
            // save the right most branch of the search tree before restarting search
            branch[nbBranches].var[level+i] = nextVar; // save the decision "nextVar = v"
            branch[nbBranches].val[level+i] = v;
            for (j=0; j<i; j++){ // save the decision "nextVar != val[j]"
                branch[nbBranches].var[level+j] = nextVar;
                branch[nbBranches].val[level+j] = -val[j]-1;
            }
            return false;
        }
        if (verbose == 2) printf("End of search node %d=%d\n",nextVar,v);

        if (i < nbVal[nextVar]-1){ // restore domains, alpha and beta
            unassigned->nb = nbUnassigned;
            for (j=0; j<nbUnassigned; j++)
                dom[unassigned->val[j]].nb = nbVal[unassigned->val[j]];
            activeBranches->nb = nbActiveBranches;
            memcpy(alpha, saveAlpha, nbBranches*sizeof(int));
            memcpy(beta, saveBeta, nbBranches*sizeof(int));
        }
    }
    return true;
}


void initGlobalVar(){
    pmate = (int*)malloc(sizeof(int)*Gp->nbVertices);
    tmate = (int*)malloc(sizeof(int)*Gt->nbVertices);
    memset(pmate, -1, Gp->nbVertices*sizeof(int));
    memset(tmate, -1, Gt->nbVertices*sizeof(int));
    dom = (SparseSet*)malloc(sizeof(SparseSet)*Gp->nbVertices);
    markedToFilter = (unsigned int*)calloc(Gp->nbVertices,sizeof(unsigned int));
    tmarkedToFilter = 1;
    nextOutToFilter = -1;
    lastInToFilter = -1;
    toFilter = (int*)malloc(sizeof(int)*Gp->nbVertices);
    lpmate = (int***)malloc(sizeof(int**)*Gp->nbVertices);
    mark = (unsigned long*)calloc((Gt->nbVertices+1),sizeof(unsigned long));
    tmark = 0;
    mark2 = (unsigned long*)calloc((Gt->nbVertices+1),sizeof(unsigned long));
    tmark2 = 0;
    mark3 = (unsigned long*)calloc(Gp->nbVertices,sizeof(unsigned long));
    tmark3 = 0;
    unassigned = (SparseSet*)malloc(sizeof(SparseSet));
    createSparseSet(unassigned, Gp->nbVertices);
    unassigned->nb = Gp->nbVertices;
    seed(1);
    lastVal = (int*)malloc(Gp->nbVertices*sizeof(int));
    memset(lastVal, -1, Gp->nbVertices*sizeof(int));
    p2 = (float*)malloc((Gt->maxDegree+1)*sizeof(float));
    p2[1] = 1;
    for (int i=2; i<=Gt->maxDegree; i++) p2[i] = 2*p2[i-1];
}

void initRestartVar(){
    branch=(Tbranch*)malloc(nbMaxBranches*sizeof(Tbranch));
    alpha=(int*)malloc(nbMaxBranches*sizeof(int));
    beta=(int*)malloc(nbMaxBranches*sizeof(int));
    activeBranches = (SparseSet*)malloc(sizeof(SparseSet));
    createSparseSet(activeBranches, nbMaxBranches);
}


void usage(int status){
	// print usage notice and exit with status code status
	printf("Usage:\n");
	printf("  -p FILE  Input pattern graph (mandatory)\n");
	printf("  -t FILE  Input target graph (mandatory)\n\n"); 
	printf("  -s INT   Set CPU time limit in seconds (default: 100)\n");
    printf("  -a       Search for all solutions (default: stop at first solution)\n");
    printf("  -f INT   Level of filtering (0=LAD; 1=FC; 2=adaptive)\n");
    printf("  -c INT   Level of clique filtering (0=no filtering; i=filtering wrt cliques of order i+2); default=4\n");
    printf("  -l INT   Limit on the number of failures before restarting (default: 10)\n");
    printf("  -r FLOAT Ratio used to increase the limit after each restart (default: 1.1)\n");
 	printf("  -v       Print solutions (default: only number of solutions)\n");
	printf("  -vv      Be verbose\n");
	exit(status);
}

void parse(char* fileNameGp, char* fileNameGt, char* argv[], int argc){
    // get parameter values
    // return false if an error occurs; true otherwise
    char ch;
    extern char* optarg;
    while ( (ch = getopt(argc, argv, "vas:p:t:l:c:r:f:"))!=-1 ) {
        switch(ch) {
            case 'f': filteringLevel=atoi(optarg); break;
            case 'c': cliqueLevel=atoi(optarg); break;
            case 'l': nbMaxFail=atoi(optarg); break;
            case 'r': ratio=atof(optarg); break;
            case 'v': verbose++; break;
            case 'a': firstSol=false; break;
            case 's': timeLimit=atoi(optarg); break;
            case 'p': strncpy(fileNameGp, optarg, 254); break;
            case 't': strncpy(fileNameGt, optarg, 254); break;
            default:
                printf("Unknown option: %c.\n", ch);
                usage(2);
        }
    }
    if (fileNameGp[0] == 0){
        printf("Error: no pattern graph given.\n");
        usage(2);
    }
    if (fileNameGt[0] == 0){
        printf("Error: no target graph given.\n");
        return usage(2);
    }
}

void printStats(bool timeout){
    // print statistics and exit run
	getrusage(RUSAGE_SELF, &ru);
	if (timeout)
        printf("Time exceeded");
	else
		printf("Run completed");
    printf(": %d solutions; %d fail nodes; %d nodes; %d restarts; %d.%06d seconds\n",
		   nbSol, nbFail, nbNodes, nbBranches,
           (int) ru.ru_utime.tv_sec, (int) ru.ru_utime.tv_usec);
    if (nbSol >= 1) checkSolution();
    exit(0);
}

void alarmHandler(int sigNum){
    // catch alarm signal when the time limit is reached
    printStats(true);
}

int main(int argc, char* argv[]){
    // Initialise parameters with default values
    timeLimit = 100;       // Default: time limit set to 100 seconds
    verbose = 0;           // Default: non verbose execution
    firstSol = true;       // Default: search for the first solution
    cliqueLevel = 4;       // Default: compute cliques of order 3 to 6
    nbMaxFail = 10;        // cutoff limit for restarting search
    ratio = 1.1;           // ratio of the geometric progression used for increasing nbMaxFail
    filteringLevel = 2;    // automatic choice of the filtering level wrt degree

    char fileNameGp[1024]; // Name of the file that contains the pattern graph
	char fileNameGt[1024]; // Name of the file that contains the target graph
	fileNameGp[0] = 0;
	fileNameGt[0] = 0;
 	parse(fileNameGp, fileNameGt, argv, argc);
    signal(SIGALRM,alarmHandler);
    alarm(timeLimit);      // alarm signal will be sent in timeLimit seconds
	if (verbose >= 1)
        printf("Parameters: firstSol=%d timeLimit=%d verbose=%d cliqueLevel=%d nbMaxFail=%d ratio=%f fileNameGp=%s fileNameGt=%s\n",
               firstSol, timeLimit, verbose, cliqueLevel, nbMaxFail, ratio, fileNameGp,fileNameGt);
	// Initialize graphs, data structures and domains
 	Gp = createGraph(fileNameGp);       // Pattern graph
	Gt = createGraph(fileNameGt);       // Target graph
    loadExternalConstraints();
 	if (verbose >= 2){
		printf("Pattern graph:\n"); printGraph(Gp);
		printf("Target graph:\n"); printGraph(Gt);
	}
    if ((Gp->nbVertices > Gt->nbVertices) || (Gp->maxDegree > Gt->maxDegree) || (Gp->nbEdges > Gt->nbEdges))
        printStats(false);
    if (Gt->isClique && !egDomains){ // unrestricted shortcut only
        cliqueTarget();
        printStats(false);
    }
    if (Gp->isClique && !egDomains){ // unrestricted shortcut only
        cliquePattern();
        printStats(false);
    }
    initGlobalVar();
    if (!initDomains()){ // inconsistency detected during the initialisation of domains
        nbFail++;
        printStats(false);
    }
    if (filteringLevel == 2){ // set FC depending on graph densities
        float dp = (float)(2*Gp->nbEdges)/(float)(Gp->nbVertices*(Gp->nbVertices-1));
        float dt = (float)(2*Gt->nbEdges)/(float)(Gt->nbVertices*(Gt->nbVertices-1));
        FC = (dp>0.15 && dt>0.15);
    }
    else FC = filteringLevel;
    if (FC){
        weight = (float*)malloc(Gp->nbEdges*sizeof(float));
        for (int i=0; i<Gp->nbEdges; i++) weight[i] = 1;
    }
    else{
        weight = (float*)malloc(Gp->nbVertices*sizeof(float));
        for (int u=0; u<Gp->nbVertices; u++) weight[u] = 1;
    }

    // Ensure the DC of GAD and assign all vertices with singleton domains
    for (int u=0; u<Gp->nbVertices; u++){
        if (!isIn(u,unassigned)) continue;
        if (!augmentingPath(u, Gt->nbVertices) ||
            (dom[u].nb == 1 && isIn(u,unassigned) && !matchVertex(u))){
            nbFail++;
            printStats(false);
        }
    }
    if (!FC && !filter()){ // Ensure the DC of LAD constraints
        nbFail++;
        printStats(false);
    }
    if (!filterMaxClique() || (!FC && !filter())){
        nbFail++;
        printStats(false);
    }
    if (verbose >= 2) printDomains();
    
	// Solve
    int saveNbUnassigned=unassigned->nb;
    int saveDomSize[Gp->nbVertices];
    int saveAlpha[nbMaxBranches];
    int saveBeta[nbMaxBranches];
    for (int u=0; u<Gp->nbVertices; u++) saveDomSize[u]=dom[u].nb;
    float currentNbFail = nbMaxFail;
    initRestartVar();
    while (true){ // restart search
        activeBranches->nb = nbBranches;
        if (solve(0))
            printStats(false); // search completed -> no need to restart
        // new restart
        // update currentNbFail and nbMaxFail wrt a geometric progression
        currentNbFail *= ratio;
        nbMaxFail += currentNbFail;
        if (verbose>=1)
            printf("Restart: current number of failures=%d; new failure limit=%d\n",nbFail,nbMaxFail);
        // restore domains as they were before the last call to solve
        unassigned->nb = saveNbUnassigned;
        for (int i=0; i<unassigned->nb; i++)
            dom[unassigned->val[i]].nb = saveDomSize[unassigned->val[i]];
        // propagate negative decisions of the last branch to filter domains
        saveAlpha[nbBranches] = 0;
        if (neg(nbBranches, 0)){
             while (saveAlpha[nbBranches]<branch[nbBranches].size && neg(nbBranches, saveAlpha[nbBranches])){
                if (!satisfyNeg(nbBranches, saveAlpha[nbBranches]))
                    printStats(false);
                saveAlpha[nbBranches]++;
            }
            saveNbUnassigned=unassigned->nb;
            for (int i=0; i<unassigned->nb; i++)
                saveDomSize[unassigned->val[i]] = dom[unassigned->val[i]].nb;
        }
        if (saveAlpha[nbBranches] < branch[nbBranches].size){
            saveBeta[nbBranches] = saveAlpha[nbBranches]+1;
            nbBranches++;
        }
        memcpy(alpha, saveAlpha, nbBranches*sizeof(int));
        memcpy(beta, saveBeta, nbBranches*sizeof(int));
    }
}
