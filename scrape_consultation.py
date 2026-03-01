import requests
from bs4 import BeautifulSoup
import csv
import time
import re
from urllib.parse import urlparse, parse_qs, urljoin

HEADERS = {"User-Agent": "Mozilla/5.0"}
REQUEST_TIMEOUT = 20


# eg. "https://www.opengov.gr/minenv/?p=12390"
CONSULTATION_URL = "https://www.opengov.gr/tourism/?p=2223"


def split_base_and_pid(consultation_url: str):
    u = consultation_url.strip()
    parsed = urlparse(u)

    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL (missing scheme/host): {consultation_url}")

    qs = parse_qs(parsed.query)
    if "p" not in qs or not qs["p"]:
        raise ValueError("Consultation URL must include '?p=<id>' (parent id).")

    try:
        parent_pid = int(qs["p"][0])
    except ValueError:
        raise ValueError(f"Invalid p value: {qs['p'][0]}")

    # Keep the path up to the trailing slash as base
    # e.g. path "/minenv/" -> base "https://www.opengov.gr/minenv/"
    path = parsed.path
    if not path.endswith("/"):
        # if someone pasted ".../minenv" (no trailing slash), normalize
        path = path + "/"

    base_url = f"{parsed.scheme}://{parsed.netloc}{path}"
    return base_url, parent_pid


def get_chapter_pids(base_url: str, parent_pid: int):
    url = f"{base_url}?p={parent_pid}"
    print(f"Fetching consultation root: {url}")

    r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html5lib")
    pids = []

    nav_ul = soup.find("ul", class_="other_posts")
    if not nav_ul:
        print("Navigation block not found. Returning empty chapter list.")
        return []

    for a in nav_ul.find_all("a", class_="list_comments_link", href=True):
        href = a["href"].strip()
        full = urljoin(base_url, href)  # handles relative or absolute
        parsed = urlparse(full)
        qs = parse_qs(parsed.query)
        if "p" in qs and qs["p"]:
            try:
                pids.append(int(qs["p"][0]))
            except ValueError:
                pass

    # de-dup while preserving order
    seen = set()
    ordered = []
    for x in pids:
        if x not in seen:
            seen.add(x)
            ordered.append(x)

    print("Detected chapter PIDs:", ordered)
    return ordered


def scrape_pid(base_url: str, pid: int, max_pages: int = 2000, sleep_s: float = 0.5):
    all_rows = {}
    prev_first_id = None

    for cpage in range(1, max_pages + 1):
        url = f"{base_url}?p={pid}&cpage={cpage}#comments"
        print(f"p={pid} page={cpage}")

        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code == 404:
            break
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html5lib")
        comments = soup.select("ul.comment_list > li.comment")

        if not comments:
            break

        first_id = comments[0].get("id")
        if first_id == prev_first_id:
            break
        prev_first_id = first_id

        for li in comments:
            cid = li.get("id", "").replace("comment-", "").strip()
            if not cid:
                continue

            author_div = li.select_one("div.user div.author")
            author = ""
            dt = ""

            if author_div:
                strong = author_div.find("strong")
                if strong:
                    author = strong.get_text(strip=True)

                raw = author_div.get_text(" ", strip=True)
                if "|" in raw:
                    dt = raw.split("|")[0].strip()
                else:
                    dt = raw.strip()

            # remove "user" block so the comment text is clean
            user_block = li.find("div", class_="user")
            if user_block:
                user_block.extract()

            text = li.get_text("\n", strip=True)

            all_rows[cid] = {
                "chapter_p": pid,
                "comment_id": cid,
                "author": author,
                "datetime": dt,
                "text": text,
            }

        time.sleep(sleep_s)

    return all_rows


def main():
    base_url, parent_pid = split_base_and_pid(CONSULTATION_URL)
    print(f"Base URL detected: {base_url}")
    print(f"Parent PID detected: {parent_pid}")

    pids = get_chapter_pids(base_url, parent_pid)
    if not pids:
        print("No chapter PIDs detected. Exiting.")
        return

    seen = set()

    with open("consultation_comments.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["chapter_p", "comment_id", "author", "datetime", "text"])

        total = 0
        for pid in pids:
            print(f"\n=== Scraping chapter {pid} ===")
            data = scrape_pid(base_url, pid)

            for cid, row in data.items():
                if cid in seen:
                    continue
                seen.add(cid)

                writer.writerow([
                    row["chapter_p"],
                    row["comment_id"],
                    row["author"],
                    row["datetime"],
                    row["text"],
                ])
                total += 1

            print(f"Chapter {pid}: {len(data)} comments")

    print("\nDONE")
    print("Total unique comments:", total)


if __name__ == "__main__":
    main()
