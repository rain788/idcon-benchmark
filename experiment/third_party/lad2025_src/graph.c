// This software has been written by Chrstine Solnon.
// It is distributed under the CeCILL-B FREE SOFTWARE LICENSE
// see http://www.cecill.info/licences/Licence_CeCILL-B_V1-en.html for more details

void printGraph(Tgraph* graph){
    int i, j;
    printf("graph with %d vertices\n",graph->nbVertices);
    for (i=0; i<graph->nbVertices; i++){
        printf("Vertex %d has %d adjacent vertices: ",
               i,graph->nbAdj[i]);
        for (j=0; j<graph->nbAdj[i]; j++) printf("%d ", graph->adj[i][j]);
        printf("\n");
    }
}

int cmp(const void * a, const void * b) {
    return (*(int*)a - *(int*)b);
}


Tgraph* createGraph(char* fileName){
	// reads data in fileName and create the corresponding graph
	
	FILE* fd;
	int i, j;
	Tgraph* graph = (Tgraph*)malloc(sizeof(Tgraph));

	if ((fd=fopen(fileName, "r"))==NULL){
		printf("ERROR: Cannot open ascii input file %s\n", fileName); 
		exit(1);
	}
	if (fscanf(fd,"%d",&(graph->nbVertices)) != 1){
		printf("ERROR while reading input file %s\n", fileName); 
		exit(1);
	}
    graph->edgeId = (int**)malloc(graph->nbVertices*sizeof(int*));
    graph->isLoop = (bool*)calloc(graph->nbVertices,sizeof(bool));
    graph->nbAdj = (int*)calloc(graph->nbVertices,sizeof(int));
	graph->adj = (int**)malloc(graph->nbVertices*sizeof(int*));
	for (i=0; i<graph->nbVertices; i++){
        graph->isLoop[i] = false;
		graph->edgeId[i] = (int*)malloc(graph->nbVertices*sizeof(int));
	}
    graph->maxDegree = 0;
    graph->nbEdges = 0;
    graph->isClique = true;
	for (i=0; i<graph->nbVertices; i++){
		// read degree of vertex i
		if ((fscanf(fd,"%d",&(graph->nbAdj[i])) != 1) || (graph->nbAdj[i] < 0) || (graph->nbAdj[i]>=graph->nbVertices) || (feof(fd))) {
			printf("ERROR while reading input file %s: Vertex %d has an illegal number of successors (%d should be between 0 and %d)\n", 
				   fileName, i, graph->nbAdj[i], graph->nbVertices);
			exit(1);
		}
        graph->adj[i] = (int*)malloc(graph->nbAdj[i]*sizeof(int));
        bool sorted=true;
        for (j=0; j<graph->nbAdj[i]; j++){
			// read jth successor of i
			if ((fscanf(fd,"%d",&(graph->adj[i][j])) != 1) || (graph->adj[i][j]<0) || (graph->adj[i][j]>=graph->nbVertices) || (feof(fd))){
				printf("ERROR while reading input file %s: Successor %d of vertex %d has an illegal value %d (should be between 0 and %d)\n", 
					   fileName, j, i, graph->adj[i][j], graph->nbVertices);
				exit(1);
			}
            if (i == graph->adj[i][j]){ // The edge is a loop
                graph->isLoop[i] = true;
                graph->nbAdj[i]--;
                j--;
            }
            else if (j>0 && graph->adj[i][j]<graph->adj[i][j-1]) sorted=false;
        }
        if (graph->nbAdj[i] > graph->maxDegree)
            graph->maxDegree = graph->nbAdj[i];
        if (graph->nbAdj[i] < graph->nbVertices-1)
            graph->isClique = false;
        if (!sorted)
            qsort(graph->adj[i], graph->nbAdj[i], sizeof(int), cmp);
        int k=0;
        for (j=0; j<graph->nbAdj[i]; j++){
            int u = graph->adj[i][j];
            while (k<u) graph->edgeId[i][k++] = -j-1;
            if (i<u) graph->edgeId[i][u] = graph->nbEdges++;
            else graph->edgeId[i][u] = graph->edgeId[u][i];
            k++;
        }
        while (k<graph->nbVertices) graph->edgeId[i][k++] = -graph->nbVertices-1;
	}
 	fclose(fd);
 	return graph;
}


int firstGreaterSucc(int i, Tgraph* g){
    // returns the index in g->adj[i] of the first vertex greater than i (or -1 if no such vertex exists)
    int ii=i+1;
    if (ii>=g->nbVertices) return -1;
    if (g->edgeId[i][ii]>=0) return -g->edgeId[i][i]-1;
    if (g->edgeId[i][ii]<-g->nbVertices) return -1;
    return -g->edgeId[i][ii]-1;
}

int firstGreaterSucc2(int i, int j, Tgraph* g){
    // returns the index in g->adj[i] of the first vertex greater than j (or -1 if no such vertex exists)
    int jj=j+1;
    if (jj>=g->nbVertices) return -1;
    if (g->edgeId[i][jj]>=0) return -g->edgeId[i][j]-1;
    if (g->edgeId[i][jj]<-g->nbVertices) return -1;
    return -g->edgeId[i][jj]-1;
}



