"""All Case24 HTML selectors live here. Start here if the website changes."""
from dataclasses import replace
import logging
import re
import time
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
import requests

from .models import Home, italian_number

LOG = logging.getLogger(__name__)
AGENT = "CasaWatch/0.1 (personal property monitor)"
ORIGIN = "https://www.case24.it"


def canonical_url(base, href):
    parsed = urlsplit(urljoin(base, href))
    if parsed.scheme != "https" or parsed.netloc != "www.case24.it":
        raise ValueError("Unexpected source host")
    return urlunsplit((parsed.scheme, parsed.netloc, re.sub(r"/+", "/", parsed.path), parsed.query, ""))


def property_type(url):
    path = urlsplit(url).path
    if "_in_vendita/" not in path and "-in-vendita/" not in path:
        return None  # Rent must never be compared with purchase prices.
    if "attic" in path:
        return "penthouse"
    if "ville" in path:
        return "house"
    if "rustic" in path:
        return "rustic"
    if any(word in path for word in ("camere", "mono_e_mini", "appartament")):
        return "apartment"
    return None


def parse_search(html, url):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".risultatoRicerca")
    if not cards:
        # Do not silently report 'no homes' when a block page or changed layout arrives.
        raise ValueError("No listing cards found. The source may be empty, blocked, or changed; check the page manually.")
    homes = {}
    for card in cards:
        link = card.select_one('a[href*=".html"]')
        facts = card.select_one(".fasciaAltaRisultato03")
        if not link or not facts:
            raise ValueError("A listing card is missing its link or facts; source layout changed")
        target = canonical_url(url, link["href"])
        kind = property_type(target)
        if not kind:
            continue
        text = facts.get_text(" ", strip=True)
        price = re.search(r"€\s*([\d.,]+)", text)
        area = re.search(r"([\d.,]+)\s*M[qQ]", text)
        content = card.select_one(".contenutiRisultatiDati02") or card.find("p")
        title = card.select_one("strong.elenco") or card.find("strong")
        home_id = re.search(r"/(\d+)\.html$", urlsplit(target).path)
        if not home_id:
            raise ValueError("Unrecognised listing ID")
        homes[home_id[1]] = Home(
            id=home_id[1], url=target,
            title=title.get_text(" ", strip=True) if title else kind,
            city=text.split("|")[0].split("(")[0].strip(), property_type=kind,
            price=italian_number(price[1]) if price else None,
            sqm=italian_number(area[1]) if area else None,
            description=content.get_text(" ", strip=True) if content else "",
        )
    pages = [1]
    for link in soup.select(".linkPagine a[href]"):
        query = parse_qs(urlsplit(link["href"]).query)
        if query.get("page", [""])[0].isdigit():
            pages.append(int(query["page"][0]))
    return list(homes.values()), max(pages)


def parse_detail(html, home):
    soup = BeautifulSoup(html, "html.parser")
    facts = {}
    for row in soup.select("table tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) == 2:
            label = cells[0].get_text(" ", strip=True).rstrip(": ").casefold()
            facts[label] = cells[1].get_text(" ", strip=True)
    if facts.get("codice inserzione") != home.id:
        raise ValueError("Detail page ID missing or mismatched; refusing to save")
    description = next((p.get_text(" ", strip=True) for p in soup.select("p.contenuti")
                        if "Descrizione:" in p.get_text()), "")
    if not description:
        raise ValueError("Detail description missing; source layout changed")

    def count(key):
        value = facts.get(key, "")
        return int(value) if value.isdigit() else None

    furnished = facts.get("arredato", "").casefold()
    garden = facts.get("tipologia giardino", "").casefold()
    return replace(home,
        description=description.removeprefix("Descrizione:").strip(),
        city=facts.get("comune", home.city),
        price=italian_number(facts.get("prezzo", "")),
        sqm=italian_number(facts.get("superficie (mq)", "")),
        bedrooms=count("camere"), bathrooms=count("bagni"),
        energy_class=facts.get("classe energetica") or None,
        condition=facts.get("stato immobile") or None,
        furnished=True if furnished in ("sì", "si") else False if furnished == "no" else None,
        garden=None if not garden else garden not in ("nessuno", "assente", "no"),
    )


class Case24:
    def __init__(self, store, settings, deadline=None):
        self.store = store
        self.settings = settings
        self.deadline = deadline
        self.session = requests.Session()
        self.session.headers["User-Agent"] = AGENT
        self.last_request = 0.0
        self.robots = None
        self.robots_checked = 0.0
        self.blocked_until = 0.0

    def close(self):
        self.session.close()

    def raw_get(self, url):
        url = canonical_url(ORIGIN, url)
        if time.time() < max(self.blocked_until, self.store.get_state("source_cooldown", 0)):
            raise RuntimeError("Source cooling down after HTTP rejection; waiting before retry")
        delay = self.settings["request_delay_seconds"]
        if self.robots:
            delay = max(delay, self.robots.crawl_delay(AGENT) or 0)
        wait = max(0, delay - (time.monotonic() - self.last_request))
        if self.deadline and time.monotonic() + wait >= self.deadline:
            raise TimeoutError("Requested running time ended")
        time.sleep(wait)
        self.store.reserve_request(self.settings["max_requests_per_day"])
        self.last_request = time.monotonic()
        remaining = self.deadline - time.monotonic() if self.deadline else 20
        response = self.session.get(url, timeout=max(0.1, min(20, remaining)), allow_redirects=False)
        # Never follow a login, CAPTCHA, or a redirect to an unchecked URL.
        if response.status_code in (401, 403, 429):
            retry = response.headers.get("Retry-After", "")
            seconds = 3600
            if retry.isdigit():
                seconds = max(seconds, int(retry))
            elif retry:
                from email.utils import parsedate_to_datetime
                try:
                    seconds = max(seconds, parsedate_to_datetime(retry).timestamp() - time.time())
                except (ValueError, TypeError):
                    pass
            self.blocked_until = time.time() + seconds
            self.store.set_state("source_cooldown", self.blocked_until)
        if 300 <= response.status_code < 400:
            raise RuntimeError(f"Source redirected (HTTP {response.status_code}); inspect the URL manually")
        response.raise_for_status()
        # Case24 declares its encoding in HTML. BeautifulSoup will read the bytes.
        return response

    def get(self, url):
        if self.robots is None or time.monotonic() - self.robots_checked > 3600:
            response = self.raw_get(ORIGIN + "/robots.txt")
            parser = RobotFileParser()
            parser.parse(response.text.splitlines())
            self.robots = parser
            self.robots_checked = time.monotonic()
        if not self.robots.can_fetch(AGENT, url):
            raise RuntimeError("robots.txt disallows this URL; source disabled for this request")
        return self.raw_get(url).content
