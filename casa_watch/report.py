"""Write a local HTML report and JSON export. Escape all scraped text."""
from dataclasses import asdict
from html import escape
import json
from pathlib import Path


def atomic_write(path, text):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def money(value):
    return f"€{value:,.0f}" if value is not None else "Unknown"


def write_report(rows, status, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    export = [{**row, "home": asdict(row["home"])} for row in rows]
    atomic_write(directory / "homes.json", json.dumps({"status": status, "results": export}, indent=2, ensure_ascii=False))
    cards = []
    for row in rows:
        home = row["home"]
        description = escape(home.description[:600])
        reasons = "".join(f"<li>{escape(reason)}</li>" for reason in row["reasons"])
        flags = "".join(f"<p class='warning'>{escape(flag)}</p>" for flag in row["flags"])
        detail = home.detail_checked or "Pending"
        cards.append(f"""<article data-price='{home.price}' data-kind='{home.property_type}'>
          <div class='card-top'><span>{escape(home.property_type.upper())} · {escape(home.city)}</span><b>Signal {row['score']:g}</b></div>
          <h2><a href='{escape(home.url, quote=True)}' target='_blank' rel='noopener noreferrer'>{escape(home.title)} ↗</a></h2>
          <div class='price'>{money(home.price)} <small>{home.sqm or '?'} m² · {money(home.price_per_sqm)}/m²</small></div>
          <p>{home.bedrooms if home.bedrooms is not None else '?'} bedrooms · {home.bathrooms if home.bathrooms is not None else '?'} bathrooms · Energy {escape(home.energy_class or '?')}</p>
          <ul>{reasons}</ul>{flags}<p class='description'>{description}</p>
          <footer>Listing #{escape(home.id)} · Last observed {escape(home.last_seen)}<br>Details checked {escape(detail)}</footer>
        </article>""")
    errors = "".join(f"<li>{escape(error)}</li>" for error in status.get("errors", []))
    html = """<!doctype html><html lang='en'><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <meta http-equiv='refresh' content='120'><title>Casa Watch · Milan homes</title>
    <style>
    *{box-sizing:border-box}body{margin:0;background:#f3f4ef;color:#183c32;font:16px/1.55 system-ui,sans-serif}
    main{max-width:1120px;margin:auto;padding:40px 24px}header{border-bottom:1px solid #b7c9be;padding-bottom:25px}
    .eyebrow{font-size:12px;letter-spacing:3px;font-weight:700}h1{font-size:clamp(32px,5vw,56px);line-height:1.1;margin:14px 0}
    .intro{max-width:790px;color:#435f55}a{color:inherit}h2{font-size:22px;line-height:1.3}h2 a{text-decoration:none}
    .toolbar{display:flex;gap:16px;flex-wrap:wrap;margin:25px 0}input,select{padding:10px;border:1px solid #a6bbb0;border-radius:6px;font:inherit;max-width:100%}
    label{display:grid;gap:5px;font-size:13px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(440px,100%),1fr));gap:20px}
    article{background:white;border:1px solid #d8e1d9;border-radius:12px;padding:24px}.card-top{display:flex;justify-content:space-between;gap:10px;font-size:12px}
    .card-top b{background:#e8efaa;padding:2px 8px;border-radius:4px}.price{font-size:26px;font-weight:700}.price small{display:block;font-size:14px;font-weight:400}
    li{font-size:14px}ul{padding-left:20px}.warning{background:#fff2d6;padding:8px;font-size:13px;border-radius:4px}
    .description{color:#51615a;font-size:14px}footer{font-size:11px;color:#677970;border-top:1px solid #e3e9e3;padding-top:12px}
    .status{background:#e5ece6;border-radius:8px;padding:16px;margin:20px 0;font-size:14px}[hidden]{display:none!important}
    </style></head><body><main><header><div class='eyebrow'>CASA WATCH / ITALIA</div>
    <h1>Your next home, in view.</h1><p class='intro'>Homes for sale in Milano, up to €10 million. Real Case24 asking prices, collected locally. The signal ranks price comparisons and recorded reductions; it is not a valuation.</p>
    </header>"""
    city = escape(status.get("city", "Milano"))
    budget = status.get("max_price", 10000000)
    html = html.replace("Milan homes", city + " homes").replace("Homes for sale in Milano, up to €10 million.", f"Homes for sale in {city}, up to {money(budget)}.")
    html += f"<div class='status'><strong>{len(rows)} matches · {status['observed']} recently observed homes</strong><br>Last attempt: {escape(status['checked_at'])} · Last fully successful cycle: {escape(status.get('last_success') or 'None yet')}<br>{status['requests_today']} / {status['daily_budget']} requests used today (UTC). {status['details_pending']} homes awaiting detail checks.<ul>{errors}</ul></div>"
    html += """<p class='intro'>Coverage is a growing sample from one portal, not every home in Milan. Comparisons use the same city, property type and similar size; neighbourhood and condition can differ. Confirm availability and terms with the original advert. All times are UTC.</p>
    <div class='toolbar'><label>Search advert text<input id='search' type='search' placeholder='e.g. Isola, terrazzo'></label>
    <label>Maximum asking price (€)<input id='budget' type='number' min='0' value='10000000'></label>
    <label>Property type<select id='kind'><option value=''>All types</option value='apartment'>Apartment</option><option value='penthouse'>Penthouse</option><option value='house'>House</option><option value='rustic'>Rustic</option></select></label></div>
    <p id='count' aria-live='polite'></p><div class='grid'>"""
    html = html.replace("every home in Milan", f"every home in {city}").replace("value='10000000'", f"value='{budget}'")
    html += "".join(cards) or "<p>No matches yet. Check the status above or loosen your filters in config.toml.</p>"
    html += """</div><p class='intro'>This report refreshes every two minutes while open. Run the monitor to collect updates. Saved observations do not prove a property is still available.</p></main>
    <script>
    const search=document.querySelector('#search'),budget=document.querySelector('#budget'),kind=document.querySelector('#kind');
    function filter(){let shown=0;document.querySelectorAll('article').forEach(card=>{
      const match=card.textContent.toLowerCase().includes(search.value.toLowerCase()) &&
      (budget.value===''||Number(card.dataset.price)<=Number(budget.value)) && (!kind.value||card.dataset.kind===kind.value);
      card.hidden=!match;if(match)shown++;});document.querySelector('#count').textContent=shown+' homes shown';}
    [search,budget,kind].forEach(input=>input.addEventListener('input',filter));filter();
    </script></body></html>"""
    atomic_write(directory / "index.html", html)
