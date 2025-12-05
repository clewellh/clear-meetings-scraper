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

    # Find PDF links that look like agendas or minutes
    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = link.get_text(" ", strip=True)

        if ".pdf" not in href.lower():
            continue

        # Try to extract a date
        meeting_date = parse_date(text)
        if not meeting_date:
            continue

        meeting = {
            "municipality": "New Providence",
            "body_name": "Borough Council",
            "title": "Borough Council Meeting",
            "meeting_date": meeting_date.isoformat(),
            "agenda_url": href,
        }

        meetings.append(meeting)

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
