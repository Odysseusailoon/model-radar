"""Escape markdown for lark-cli docs +create import: $ ~ < _ and single * outside URLs/code."""
import re,sys
src=open(sys.argv[1]).read(); out=[]
# split on markdown links (keep URL part untouched) and inline code
tok=re.split(r'(\]\([^)]*\)|`[^`]*`|https?://\S+)', src)
for i,t in enumerate(tok):
    if i%2==1: out.append(t); continue
    t=t.replace('$','\\$').replace('~','\\~').replace('<','\\<').replace('_','\\_')
    t=re.sub(r'(?<!\*)\*(?!\*)','\\*',t)
    out.append(t)
open(sys.argv[2],'w').write(''.join(out)); print('escaped',sys.argv[2])
