CC ?= gcc
CFLAGS ?= -O3 -Wall -fstrict-aliasing -std=c99

all: ../build/lad2025/lad2025

../build/lad2025/lad2025: main.c allDiff.c clique.c domains.c graph.c heuristic.c lad.c nogoods.c random.c sparseSet.c
	mkdir -p ../build/lad2025
	$(CC) $(CFLAGS) main.c -o $@
