import sys, re, subprocess, urllib.parse, html

def search(query, n=10):
    q = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/search?q={q}&count={n}"
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    out = subprocess.run(["curl","-s","-A",ua,url], capture_output=True, text=True).stdout
    # extract result blocks: <li class="b_algo"> ... <h2><a href="URL">TITLE</a> ... <p>SNIPPET</p>
    results = []
    for m in re.finditer(r'<li class="b_algo"[^>]*>(.*?)</li>', out, re.S):
        block = m.group(1)
        am = re.search(r'<h2[^>]*>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not am: continue
        link = html.unescape(am.group(1))
        title = html.unescape(re.sub('<[^<]+?>', '', am.group(2))).strip()
        pm = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        snippet = html.unescape(re.sub('<[^<]+?>', '', pm.group(1))).strip() if pm else ""
        results.append((title, link, snippet))
    return results

if __name__ == "__main__":
    query = sys.argv[1]
    for t, l, s in search(query):
        print(f"TITLE: {t}\nURL: {l}\nSNIPPET: {s}\n---")
