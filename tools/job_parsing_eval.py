"""Measure how many requirement lines the parser finds in real, live job postings.

    python tools/job_parsing_eval.py --fetch 60   # download a sample from Disney Careers (robots.txt allows job pages)
    python tools/job_parsing_eval.py              # score the downloaded sample again after a parser change

Postings are saved under .job-corpus/ (git-ignored): they are someone else's text, so they stay out
of the repository. The score is rough. A "requirement line" is any line under a heading that
reads like requirements ("Required Qualifications", "You must", "Preferred Skills"...), so a few
company blurbs count too; compare runs against each other rather than reading it as a percentage.
"""

import argparse
import html
import json
import random
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / ".job-corpus"
SITEMAP = "https://join.disneycareers.com/global/en/sitemap.xml"
AGENT = "resume-engine-parser-eval/1.0"

REQ = re.compile(r"qualif|requir|must|skills|experience|education|need from you|bring|looking for|you have|who you are|nice to have|bonus", re.I)
STOP = re.compile(
    r"pay transparency|disclaimer|accommodation|submitting|benefit|perks|schedule|about|summary|reasons|responsib|"
    r"what you( wi|’|')ll do|description",
    re.I,
)


def _get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "tr"}

    def __init__(self):
        super().__init__()
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.skip += 1
        if tag in self.BLOCK:
            self.out.append("\n")
        if tag == "li":
            self.out.append("- ")

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.skip = max(0, self.skip - 1)
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def plain_text(fragment: str) -> str:
    """The posting as a person would paste it: one line per paragraph or bullet."""
    parser = _Text()
    parser.feed(html.unescape(fragment) if "&lt;" in fragment else fragment)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in "".join(parser.out).replace("\xa0", " ").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def job_from_page(page: str) -> dict:
    """Phenom career pages embed the posting as JSON next to "jobDetail"."""
    at = max(page.find('"jobDetail","data":'), page.find('"jobDetail":{"data":'))
    if at < 0:
        raise ValueError("no job data on this page")
    start = page.find('{"job"', at)
    job, _ = json.JSONDecoder().raw_decode(page[start:])
    return job["job"]


def fetch(count: int, seed: int) -> None:
    CORPUS.mkdir(exist_ok=True)
    urls = re.findall(r"<loc>([^<]*/job/[^<]*)</loc>", _get(SITEMAP))
    random.Random(seed).shuffle(urls)
    saved = 0
    for url in urls:
        if saved >= count:
            break
        key = url.split("/job/")[1].split("/")[0]
        target = CORPUS / f"{key}.json"
        if target.exists():
            saved += 1
            continue
        try:
            job = job_from_page(_get(url))
        except Exception as error:  # a page without the JSON is skipped, not fatal
            print("skip", url, error, file=sys.stderr)
            continue
        text = plain_text(job.get("description") or "")
        if not text:
            print("skip", url, "empty description", file=sys.stderr)
            continue
        target.write_text(json.dumps({"url": url, "title": job.get("title"), "category": job.get("category"), "text": text}, ensure_ascii=False))
        saved += 1
        time.sleep(1)
    print(f"{saved} postings in {CORPUS}")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _is_heading(line: str) -> bool:
    return bool(line) and not line.startswith("-") and len(line) <= 70 and not line.endswith(".") and len(line.split()) <= 8


def requirement_lines(text: str) -> list[str]:
    lines, inside = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _is_heading(line):
            if STOP.search(line):
                inside = False
                continue
            if REQ.search(line) and len(line.split()) <= 6:
                inside = True
                continue
        if inside and len(line) < 400:
            lines.append(line.lstrip("-•* ").strip())
    return lines


def score(verbose: bool) -> None:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.job_match import parse_requirements

    postings = [json.loads(path.read_text()) for path in sorted(CORPUS.glob("*.json"))]
    if not postings:
        raise SystemExit("No postings yet: run with --fetch first.")
    total = found = rows = empty = 0
    misses = []
    for posting in postings:
        parsed = parse_requirements(posting["text"])
        texts = " | ".join(_norm(row["text"]) for key in parsed for row in parsed[key])
        rows += sum(len(parsed[key]) for key in parsed)
        wanted = requirement_lines(posting["text"])
        hits = [line for line in wanted if _norm(line)[:60] in texts]
        total += len(wanted)
        found += len(hits)
        empty += bool(wanted) and not hits
        misses += [(posting["title"], line) for line in wanted if line not in hits]
    print(f"{len(postings)} postings: {found}/{total} requirement lines found ({found / max(total, 1):.0%}), {rows} rows, {empty} postings with none found")
    if verbose:
        for title, line in random.Random(1).sample(misses, min(30, len(misses))):
            print(f"  missed  {title[:30]:30}  {line[:100]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fetch", type=int, metavar="N", help="download N postings first")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("-v", "--verbose", action="store_true", help="list a sample of missed lines")
    args = parser.parse_args()
    if args.fetch:
        fetch(args.fetch, args.seed)
    score(args.verbose)
