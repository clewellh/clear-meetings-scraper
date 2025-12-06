import os
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

# --- CONFIG ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # service role key

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_KEY not set in env")

client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# New Providence Agenda Center
NP_URL = "https://www.newprov.us/AgendaCenter"

# Date patterns like "Dec 2, 2025" or "December 2, 2025"
DATE_REGEX = r"([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})"


def parse_date(text: str):
    """Parse dates like 'Dec 2, 2025' or 'December 2, 2025'."""
    if not text:
        return None

    m = re.search(DATE_REGEX, text)
    if not m:
        return None

    date_str = m.group(1)

    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    return None


def scrape_new_providence():
    print("Scraping New Providence Agenda Center...")

    resp = requests.get(NP_URL, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1) Find the Borough Council section header
    borough_header = None
    for h in soup.find_all(["h2", "h3"]):
        if "Borough Council" in h.get_text(strip=True):
            borough_header = h
            break

    if borough_header is None:
        print("Could not find Borough Council section in HTML")
        return []

    meetings = []

    # 2) Walk forward from that header until the next h2 (next big section)
    for node in borough_header.find_all_next():
        # Stop when we hit another top-level section (e.g. Planning Board)
        if node.name == "h2" and node is not borough_header:
            break

        # Each meeting heading is an h3 like "Dec 2, 2025"
        if node.name == "h3":
            date_text = node.get_text(" ", strip=True)
            meeting_date = parse_date(date_text)

            if not meeting_date:
                continue

            # Look ahead from this h3 for the first anchor that looks like the meeting
            link = None
            cur = node
            while True:
                cur = cur.find_next()
                if cur is None:
                    break
                if cur.name == "h3":  # next meeting
                    break
                if cur.name == "a":
                    text = cur.get_text(" ", strip=True)
                    href = cur.get("href", "")
                    if "Borough Council" in text or "/AgendaCenter/ViewFile/Agenda/" in href:
                        link = cur
                        break

            if not link or not link.has_attr("href"):
                continue

            href = link["href"]
            full_url = urljoin(NP_URL, href)
            title = link.get_text(" ", strip=True) or "Borough Council Meeting"

            meetings.append(
    {
        "uid": f"New Providence|Borough Council|{meeting_date.isoformat()}",
        "municipality": "New Providence",
        "body_name": "Borough Council",
        "title": title,
        "meeting_date": meeting_date.isoformat(),
        "agenda_url": full_url,
    }
)

        print(f"Found {len(meetings)} NP meetings before dedupe")

    # Deduplicate by uid so we don't send duplicates in one upsert
    unique_by_uid = {}
    for m in meetings:
        unique_by_uid[m["uid"]] = m  # later ones overwrite earlier ones with same uid

    deduped_meetings = list(unique_by_uid.values())
    print(f"After dedupe, {len(deduped_meetings)} NP meetings")

    return deduped_meetings



def upsert_meetings(meetings):
    if not meetings:
        print("No meetings to upsert")
        return

    resp = client.table("np_meetings").upsert(
        meetings,
        on_conflict=["uid"],
    ).execute()

    print("Supabase upsert response:", resp)
    print(f"Inserted/updated {len(meetings)} meetings.")

if __name__ == "__main__":
    meetings = scrape_new_providence()
    upsert_meetings(meetings)


