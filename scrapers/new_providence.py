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

# New Providence agenda page (Agenda Center)
NP_URL = "https://www.newprov.us/AgendaCenter"

# Regex to pull _MMDDYYYY- out of the href, e.g. _12022025-1258
DATE_FROM_HREF = re.compile(r"_([0-9]{8})-")


def date_from_href(href: str):
    """
    Extract a date from an href like:
    /AgendaCenter/ViewFile/Agenda/_12022025-1258
    -> 2025-12-02
    """
    m = DATE_FROM_HREF.search(href)
    if not m:
        return None

    num = m.group(1)  # e.g. "12022025" = MMDDYYYY
    try:
        return datetime.strptime(num, "%m%d%Y").date()
    except ValueError:
        return None


def scrape_new_providence():
    print("Scraping New Providence...")

    response = requests.get(NP_URL, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    meetings = []

    # Find all <a> links that look like agenda links
    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = link.get_text(" ", strip=True)

        # Only agenda links in the AgendaCenter
        if "/AgendaCenter/ViewFile/Agenda/" not in href:
            continue

        # Only Borough Council meetings
        if "Borough Council" not in text:
            continue

        meeting_date = date_from_href(href)
        if not meeting_date:
            continue

        full_url = href
        if full_url.startswith("/"):
            full_url = "https://www.newprov.us" + full_url

        meetings.append(
            {
                "municipality": "New Providence",
                "body_name": "Borough Council",
                "title": text or "Borough Council Meeting",
                "meeting_date": meeting_date.isoformat(),
                "agenda_url": full_url,
            }
        )

    print(f"Found {len(meetings)} NP meetings")
    return meetings


def upsert_meetings(meetings):
    if not meetings:
        print("No meetings to upsert.")
        return

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
