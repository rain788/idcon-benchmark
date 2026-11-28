import json,re,sys
d=json.load(open('bib.json'))
text=''.join(open(f).read() for f in sys.argv[1:])
order=[]
for m in re.finditer(r'\\cite\{([^}]+)\}',text):
    for k in m.group(1).split(','):
        k=k.strip()
        if k not in order: order.append(k)
missing=[k for k in order if k not in d]
assert not missing,missing
with open('references.tex','w') as f:
    f.write('\\begin{thebibliography}{99}\n')
    for k in order: f.write(f'\\bibitem{{{k}}} {d[k]}\n')
    f.write('\\end{thebibliography}\n')
print(len(order),'references')
