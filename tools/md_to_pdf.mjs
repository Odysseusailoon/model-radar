// Render a Markdown report to a print-styled HTML and an A4 PDF via headless Chrome.
// usage: node tools/md_to_pdf.mjs <in.md> <out.html> <out.pdf> "<header label>"
import fs from 'node:fs'; import {execFileSync} from 'node:child_process';
// `marked` is resolved from a normal install; set MARKED_ESM to an absolute
// path to marked.esm.js when running somewhere without node_modules.
let marked;
try {
  ({marked} = await import('marked'));
} catch {
  if (!process.env.MARKED_ESM) {
    console.error('marked not found — run `npm i marked`, or set MARKED_ESM=/abs/path/to/marked.esm.js');
    process.exit(1);
  }
  ({marked} = await import(process.env.MARKED_ESM));
}
const [inMd,outHtml,outPdf,label='MODEL RADAR']=process.argv.slice(2);
const md=fs.readFileSync(inMd,'utf8');
let html=marked.parse(md,{gfm:true});
const title=(md.match(/^#\s+(.+)$/m)||[,'Report'])[1].replace(/<[^>]+>/g,'');
html=html.replace(/<table>/g,'<div class="tw"><table>').replace(/<\/table>/g,'</table></div>');
html=html.replace(/<a href="(https?:[^"]+)"/g,'<a target="_blank" rel="noopener" href="$1"');
const css=`
:root{--ink:#18283d;--muted:#657180;--blue:#2357a4;--line:#dbe2e9;--pale:#eef3fa}
*{box-sizing:border-box}body{margin:0;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;font-size:15px;line-height:1.8;background:#fff}
main{max-width:920px;margin:0 auto;padding:36px 40px 60px}
.label{font-size:11px;letter-spacing:3px;color:var(--muted);border-bottom:3px solid var(--ink);padding-bottom:10px;margin-bottom:6px}
h1{font-size:30px;line-height:1.3;margin:14px 0 6px;letter-spacing:-.5px}
h2{font-size:21px;margin:40px 0 14px;padding-top:14px;border-top:2px solid var(--ink);line-height:1.4}
h3{font-size:17px;margin:26px 0 10px;color:var(--blue)}h4{font-size:15px;margin:18px 0 8px}
p{margin:10px 0}li{margin:5px 0}ul,ol{padding-left:22px}
blockquote{margin:16px 0;padding:10px 16px;border-left:3px solid var(--blue);background:var(--pale);color:#2b3a4f}
code{font-size:.85em;background:#f0f3f6;border-radius:3px;padding:1px 4px;overflow-wrap:anywhere}pre{white-space:pre-wrap;background:#f6f8fa;padding:12px;border-radius:4px;font-size:12px}
.tw{margin:14px 0;overflow-x:auto;border:1px solid var(--line);border-radius:4px}
table{border-collapse:collapse;width:100%;font-size:12.5px;line-height:1.55}th{background:var(--pale);text-align:left;font-size:11.5px;font-weight:650}
td,th{padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}tr:last-child td{border-bottom:0}tbody tr:nth-child(even){background:#fafbfd}td{overflow-wrap:anywhere}
a{color:var(--blue);text-decoration:none;border-bottom:1px solid #bfd0e7}hr{border:0;border-top:1px solid var(--line);margin:30px 0}
strong{font-weight:650}
@media print{body{font-size:10.5pt;line-height:1.65}main{max-width:none;padding:0}h1{font-size:22pt}h2{font-size:15pt;margin-top:22pt;break-after:avoid}h3{font-size:12.5pt;break-after:avoid}h4{break-after:avoid}
p{orphans:3;widows:3}.tw{overflow:visible;border:0}table{font-size:8.6pt}th,td{padding:4px 6px}tr{break-inside:avoid}thead{display:table-header-group}a{color:var(--blue);border:0}blockquote{break-inside:avoid}
@page{size:A4;margin:16mm 15mm 18mm}}`;
const doc=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><style>${css}</style></head><body><main><div class="label">${label}</div>${html}</main></body></html>`;
fs.writeFileSync(outHtml,doc);
const chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
execFileSync(chrome,['--headless=new','--disable-gpu','--no-pdf-header-footer','--print-to-pdf='+outPdf,'file://'+fs.realpathSync(outHtml)],{stdio:'ignore',timeout:120000});
console.log(JSON.stringify({title,mdChars:md.length,pdf:outPdf}));
