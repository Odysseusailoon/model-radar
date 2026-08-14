"""Render MINIMAX-H3-OFFICIAL-README.md into a Feishu-importable markdown file.

The GitHub README is built for GitHub: reference-style shields.io badges, <details>
collapsibles, decorative <p align> separators. Feishu's markdown importer would
HTTP-download every badge (~200 images) and parse the raw HTML as XML nodes, so the
review copy strips the presentation layer and keeps the information:

  [![][gh-Comfy--Org]](url)  ->  [Comfy-Org](url)      (download links survive)
  ![int8][badge-int8]        ->  `int8`                 (precision stays readable)
  <details><summary><b>X</b> ->  #### X                 (tables stop being hidden)
  <p align=...>divider</p>   ->  dropped
  the reference-definition block -> dropped (nothing references it any more)

Run:
    .venv/bin/python tools/readme_to_feishu.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "MINIMAX-H3-OFFICIAL-README.md"
OUT = ROOT / "_feishu-h3-readme.md"


def unshield(name: str) -> str:
    """shields.io text escaping, reversed: `--` is a literal hyphen, `__` an underscore."""
    return name.replace("--", "\x00").replace("__", "\x01") \
               .replace("\x00", "-").replace("\x01", "_")


def convert(text: str) -> str:
    # 1. header badge block: [![Model][hf-shield]][hf-url] -> plain labelled links
    text = text.replace(
        '[![Model][hf-shield]][hf-url]',
        '[Hugging Face — MiniMaxAI/MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3)')
    text = text.replace(
        '[![GitHub][gh-shield]][gh-url]',
        '[GitHub — MiniMax-AI/MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3)')
    text = text.replace(
        '[![ComfyUI][comfy-shield]][comfy-url]',
        '[ComfyUI tutorial](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)')

    # 2. download cells: [![][gh-Uploader]](url) -> [Uploader](url)
    text = re.sub(r'\[!\[\]\[gh-([A-Za-z0-9_.-]+)\]\]\((\S+?)\)',
                  lambda m: f'[{unshield(m.group(1))}]({m.group(2)})', text)
    # bare uploader shields with no link target
    text = re.sub(r'!\[\]\[gh-([A-Za-z0-9_.-]+)\]',
                  lambda m: unshield(m.group(1)), text)

    # 3. precision / category shields -> inline code, keeping the visible label
    text = re.sub(r'!\[([^\]]*)\]\[(?:badge|cat)-([A-Za-z0-9_.-]+)\]',
                  lambda m: f'`{m.group(1) or unshield(m.group(2))}`', text)

    # 4. <details> -> a real heading so nothing stays collapsed in review.
    #    The title stays on one line ([^\n]) on purpose: a dot-matches-newline
    #    capture will run past a summary whose </b> is followed by trailing text
    #    and swallow the next block whole.
    def detitle(match: re.Match[str]) -> str:
        title = re.sub(r'</?b>', '', match.group(1)).strip()
        return f'#### {title}'

    text = re.sub(r'<details>\s*<summary>([^\n]*?)</summary>', detitle, text)
    text = text.replace('</details>', '')

    # 5. decorative separators / centering wrappers
    text = re.sub(r'^<p[^>]*>[^<]*</p>\s*$', '', text, flags=re.M)
    text = re.sub(r'^</?div[^>]*>\s*$', '', text, flags=re.M)
    text = re.sub(r'^<a id="[^"]*"></a>\s*$', '', text, flags=re.M)

    # 6. drop the reference-definition block (nothing references it now)
    text = re.sub(r'\n<!-- MARKDOWN LINKS & IMAGES -->.*$', '\n', text, flags=re.S)
    text = re.sub(r'^\[[A-Za-z0-9_.-]+\]:\s*\S+.*$', '', text, flags=re.M)

    # 7. in-page anchors (#quants) do not resolve in Feishu -> keep the words only
    text = re.sub(r'\[([^\]]+)\]\(#[A-Za-z0-9-]+\)', r'\1', text)

    # 8. collapse the blank lines all of the above left behind
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() + '\n'


def main() -> int:
    out = convert(SRC.read_text())
    OUT.write_text(out)

    leftovers = {
        'unresolved reference links': len(re.findall(r'\]\[[A-Za-z0-9_.-]+\]', out)),
        'raw html tags': len(re.findall(r'<(?:details|summary|div|p|a)[ >]', out)),
        'shields.io urls': out.count('img.shields.io'),
    }
    table_rows = len(re.findall(r'^\| :', out, re.M))
    print(f"{SRC.name}: {len(SRC.read_text()):,} bytes -> {OUT.name}: {len(out):,} bytes")
    print(f"lines: {out.count(chr(10)):,}   tables: {table_rows}")
    for label, count in leftovers.items():
        flag = 'ok' if count == 0 else 'CHECK'
        print(f"  {flag:5s} {label}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
