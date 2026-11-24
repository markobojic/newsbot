"""Official NBS middle rate EUR -> RSD, scraped from the NBS web app. Plain Python, no Claude.

NBS publishes a list on working days only. Asking for a weekend or holiday returns the
last list (e.g. Saturday -> Friday's), so the list date, not today, says how fresh it is.
"""

import html
import re
from datetime import date, datetime

import httpx2

LIST_URL = "https://webappcenter.nbs.rs/ExchangeRateWebApp/ExchangeRate/IndexByDate"
MIDDLE_RATE = 3  # ExchangeRateListTypeID for the official middle rate

# "КУРСНА ЛИСТА БР. 224 ... ФОРМИРАНА НА ДАН 24.11.2026." and the row "EUR 978 ЕМУ 1 117,6503"
LIST_HEADER = re.compile(r"КУРСНА ЛИСТА БР\.\s*(\d+).*?ФОРМИРАНА НА ДАН\s*(\d{2}\.\d{2}\.\d{4})")
EUR_ROW = re.compile(r"\bEUR\s+978\s+\S+\s+1\s+(\d+,\d+)")


class FxParseError(Exception):
    """The page answered, but the list number, date or EUR row could not be found."""


def _page_text(raw_html: str) -> str:
    # Tags out, entities decoded (the page writes Cyrillic as &#x41A;), whitespace collapsed.
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(raw_html)))


def parse_list(raw_html: str) -> dict:
    """Extract {rate, list_date, list_number} from the NBS page; raise FxParseError if missing."""
    text = _page_text(raw_html)
    header, row = LIST_HEADER.search(text), EUR_ROW.search(text)
    if not header or not row:
        # Most likely NBS changed the page layout: the scraper needs fixing.
        raise FxParseError("NBS page has no list header or EUR row")
    return {
        "rate": float(row.group(1).replace(",", ".")),  # Serbian decimal comma
        "list_date": datetime.strptime(header.group(2), "%d.%m.%Y").date().isoformat(),
        "list_number": int(header.group(1)),
    }


def get_eur_rsd(on: date) -> dict:
    """Return the NBS list valid on `on`: {rate, list_date, list_number}."""
    resp = httpx2.get(
        LIST_URL,
        params={
            "isSearchExecuted": "true",
            "Date": on.strftime("%d.%m.%Y"),
            "ExchangeRateListTypeID": MIDDLE_RATE,
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    resp.raise_for_status()
    return parse_list(resp.text)
