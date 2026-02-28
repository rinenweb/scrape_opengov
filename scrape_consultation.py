import requests
from bs4 import BeautifulSoup
import csv
import time
import re

BASE = "https://www.opengov.gr/minenv/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# PARENT ID
CONSULTATION_ID = 12390


def get_chapter_pids(consultation_id):
    url = f"{BASE}?p={consultation_id}"
    print(f"Fetching consultation root: {url}")
    r = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(r.text, "html5lib")
    pids = []
    nav_ul = soup.find("ul", class_="other_posts")
    if not nav_ul:
        print("Navigation block not found.")
        return []
    for a in nav_ul.find_all("a", class_="list_comments_link", href=True):
        match = re.search(r"\?p=(\d+)", a["href"])
        if match:
            pids.append(int(match.group(1)))
    print("Detected chapter PIDs:", pids)
    return pids

def scrape_pid(pid):
    all_rows = {}
    prev_first_id = None

    for cpage in range(1, 2000):
        url = f"{BASE}?p={pid}&cpage={cpage}#comments"
        print(f"p={pid} page={cpage}")

        r = requests.get(url, headers=HEADERS)
        soup = BeautifulSoup(r.text, "html5lib")

        comments = soup.select("ul.comment_list > li.comment")

        if not comments:
            break

        first_id = comments[0].get("id")
        if first_id == prev_first_id:
            break

        prev_first_id = first_id

        for li in comments:
            cid = li.get("id", "").replace("comment-", "")

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

            user_block = li.find("div", class_="user")
            if user_block:
                user_block.extract()

            text = li.get_text("\n", strip=True)

            all_rows[cid] = {
                "chapter_p": pid,
                "comment_id": cid,
                "author": author,
                "datetime": dt,
                "text": text
            }

        time.sleep(0.5)

    return all_rows


def main():
    pids = get_chapter_pids(CONSULTATION_ID)

    seen = set()

    with open("consultation_comments.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["chapter_p", "comment_id", "author", "datetime", "text"])

        total = 0

        for pid in pids:
            print(f"\n=== Scraping chapter {pid} ===")
            data = scrape_pid(pid)

            for cid, row in data.items():
                if cid in seen:
                    continue
                seen.add(cid)

                writer.writerow([
                    row["chapter_p"],
                    row["comment_id"],
                    row["author"],
                    row["datetime"],
                    row["text"]
                ])
                total += 1

            print(f"Chapter {pid}: {len(data)} comments")

    print("\nDONE")
    print("Total unique comments:", total)


if __name__ == "__main__":
    main()
