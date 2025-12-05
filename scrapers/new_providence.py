import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from supabase import create_client, Client
import os

# --- CONFIG ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # service key needed to write
client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# New Providence agenda page
NP_URL = "https://www.newprov.us/AgendaCenter"

# Regex for dates like "January 8, 2024"
DATE_REGEX = r"([A-Za-z]+ \d{1,2}, \d{4})"


def parse_date(text):
    match = re.search(DATE_REGEX, text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%B %d, %Y").date()
    except:
        return None


def scrape_new_providence():
    print("Scraping New Providence...")

    response = requests.get(NP_URL, timeout=20)
    soup = BeautifulSoup(response.text, "html.parser")

    meetings = []

    # 1. Find the "Borough Council" section header
    borough_header = soup.find(["h2", "h3"], string=lambda s: s and "Borough Council" in s)
    if not borough_header:
        print("No Borough Council section found")
        return meetings

    # 2. Walk forward from that header until the next h2 (next category)
    for el in borough_header.find_all_next():
        # Stop when we hit the next top-level section
        if el.name == "h2" and el is not borough_header:
            break

        # Each meeting date is in an <h3> like "Dec 2, 2025"
        if el.name == "h3":
            date_text = el.get_text(" ", strip=True)
            meeting_date = parse_date(date_text)
            if not meeting_date:
                continue

            # Find the first link after this h3 with "Borough Council" in the text
            meeting_link = None
            next_el = el
            while True:
                next_el = next_el.find_next()
                if not next_el or next_el.name in ["h2", "h3"]:
                    break
                if next_el.name == "a":
                    link_text = next_el.get_text(" ", strip=True)
                    if "Borough Council" in link_text:
                        meeting_link = next_el
                        break

            agenda_url = meeting_link["href"] if meeting_link and meeting_link.has_attr("href") else None
            if agenda_url and agenda_url.startswith("/"):
                agenda_url = "https://www.newprov.us" + agenda_url

            meetings.append(
                {
                    "municipality": "New Providence",
                    "body_name": "Borough Council",
                    "title": "Borough Council Meeting",
                    "meeting_date": meeting_date.isoformat(),
                    "agenda_url": agenda_url,
                }
            )

    print(f"Found {len(meetings)} NP meetings")
    return meetings



def upsert_meetings(meetings):
    for m in meetings:
        # Upsert based on municipality + body_name + meeting_date
        client.table("meetings").upsert(
            {
                "municipality": m["municipality"],
                "body_name": m["body_name"],
                "title": m["title"],
                "meeting_date": m["meeting_date"],
                "agenda_url": m["agenda_url"],
            },
            on_conflict=["municipality", "body_name", "meeting_date"],
        ).execute()

    print(f"Inserted/updated {len(meetings)} meetings.")


if __name__ == "__main__":
    meetings = scrape_new_providence()
    upsert_meetings(meetings)
