#!/usr/bin/env python3
"""List the functions of a built src/smart_hub.cpp that nothing reaches (retiring the old overlay layers).

The WS350 image is rebuilt from the pinned upstream by a chain of apply_*.py layers; the older ones (v9 to v11.25 and the
first Workshop OS 12 UI passes) still insert screens that the More overhaul and the tabs overhaul replaced. The linker
drops what nothing calls, so the image does not carry them, but the source does, and so do those layers. This finds them
so each can be retired from its layers and the chain rebuilt (the built file must then differ only by the deleted
functions).

A function is live when it is not static, or is named outside any function body or in another source or header, or is
named by a live function. The scan is textual (comments and strings stripped), so read the list, do not trust it blindly.

  scripts/run_os12_ux_local.sh builds a tree; then
  python3 scripts/find_dead_ui_functions.py BUILD_DIR           prints the count and the names
"""
import glob
import re
import sys
if len(sys.argv) != 2:
    sys.exit(__doc__)
B=sys.argv[1].rstrip('/')
src=open(B+'/src/smart_hub.cpp').read()
# strip comments and strings crudely
def strip(s):
    s=re.sub(r'//[^\n]*','',s); s=re.sub(r'/\*.*?\*/','',s,flags=re.S)
    s=re.sub(r'"(?:\\.|[^"\\\n])*"','""',s); return s
code=strip(src)
# top-level function definitions: find 'name(' ... ')' '{' at brace depth 0
funcs={}
depth=0;i=0;n=len(code);start=0
# tokenise at depth 0: collect text since last ';' or '}' at depth0
buf_start=0
spans=[]
while i<n:
    c=code[i]
    if c=='{':
        if depth==0:
            head=code[buf_start:i]
            spans.append([head,i,None,buf_start])
        depth+=1
    elif c=='}':
        depth-=1
        if depth==0:
            spans[-1][2]=i
            buf_start=i+1
    elif c==';' and depth==0:
        buf_start=i+1
    i+=1
for head,a,b,hs in spans:
    if b is None: continue
    m=re.search(r'(\w+)\s*\([^()]*(?:\([^()]*\)[^()]*)*\)\s*(?:const)?\s*(?:noexcept)?\s*$',head.strip())
    if not m or re.match(r'(if|for|while|switch|struct|class|namespace|enum)\b',head.strip()): continue
    name=m.group(1)
    st='static' in head
    funcs.setdefault(name,[]).append((hs,b,st))
names=set(funcs)
body={n:''.join(code[a:b] for a,b,_ in funcs[n]) for n in names}
refs={n:set(re.findall(r'\b\w+\b',body[n]))&names-{n} for n in names}
# external refs: other src files + outside function bodies
ext=''
for f in glob.glob(B+'/src/*.cpp')+glob.glob(B+'/src/*.h')+glob.glob(B+'/include/*.h'):
    if f.endswith('smart_hub.cpp'): continue
    ext+=strip(open(f,errors='replace').read())
inbody=set()
outside=code
for n in names:
    for a,b,_ in funcs[n]: pass
# remove function bodies to get outside text
mask=list(code)
for n in names:
    for a,b,_ in funcs[n]:
        for k in range(a,b+1): mask[k]=' '
outside=''.join(mask)
roots={n for n in names if re.search(r'\b'+n+r'\b',outside) or re.search(r'\b'+n+r'\b',ext)}
# nonstatic functions treated as roots
roots|={n for n in names if any(not st for _,_,st in funcs[n])}
live=set(roots);st=list(roots)
while st:
    x=st.pop()
    for y in refs[x]:
        if y not in live: live.add(y); st.append(y)
dead=sorted(names-live)
tot=sum(len(body[n]) for n in names)
print('functions',len(names),'dead',len(dead),'dead bytes',sum(len(body[n]) for n in dead),'of',tot)
print('\n'.join(dead))
