import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from supabase import create_client, Client
import os
from urllib.parse import urljoin

# --- CONFIG ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # service key needed to write
client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Use the real Agenda Center page
NP_URL = "https://www.newprov.us/AgendaCenter"

# Matches things like "Dec 2, 2025" or "December 2, 2025"
DATE_REGEX = r"([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})"


def parse_date(text: str):
    m = re.search(DATE_REGEX, text)
    if not m:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(m.group(1), fmt).date()
        except ValueError:
            continue
    return None


def scrape_new_providence():
    print("Scraping New Providence...")

    resp = requests.get(NP_URL, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 1) Find the "Borough Council" section header
    borough_header = None
    for h in soup.find_all(["h2", "h3"]):
        if "Borough Council" in h.get_text():
            borough_header = h
            break

    if borough_header is None:
        print("Could not find Borough Council section")
        return []

    meetings = []

    # 2) Walk forward from that header until we hit the next main section
    for node in borough_header.find_all_next():
        # Stop when we hit another big section (like Board of Health, Planning Board, etc.)
        if node.name == "h2" and "Borough Council" not in node.get_text():
            break

        # Each meeting line is an h3 like "Dec 2, 2025"
        if node.name == "h3":
            date_text = node.get_text(" ", strip=True)
            meeting_date = parse_date(date_text)
            if not meeting_date:
                continue

            # Look ahead from this h3 for the first anchor with "Borough Council" in it
            link = None
            cur = node
            while True:
                cur = cur.find_next()
                if cur is None:
                    break
                if cur.name == "h3":  # next meeting, stop
                    break
                if cur.name == "a" and "Borough Council" in cur.get_text(" ", strip=True):
                    link = cur
                    break

            if not link or not link.has_attr("href"):
                continue

            href = urljoin(NP_URL, link["href"])
            title = link.get_text(" ", strip=True)

            meetings.append(
                {
                    "municipality": "New Providence",
                    "body_name": "Borough Council",
                    "title": title,
                    "meeting_date": meeting_date.isoformat(),
                    "agenda_url": href,
                }
            )

    print(f"Found {len(meetings)} NP meetings")
    return meetings


def upsert_meetings(meetings):
    if not meetings:
        print("No meetings to upsert")
        return

    # Bulk upsert into Supabase
    client.table("meetings").upsert(
        meetings,
        on_conflict=["municipality", "body_name", "meeting_date"],
    ).execute()

    print(f"Inserted/updated {len(meetings)} meetings.")


if __name__ == "__main__":
    meetings = scrape_new_providence()
    upsert_meetings(meetings)
