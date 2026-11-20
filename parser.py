import csv
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://online.vostokinc.ru/"
CATALOG_URL = "https://online.vostokinc.ru/katalog-tovarov/"
CSV_FILE = "vostok_limited.csv"
HTML_FILE = "index.html"

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "").strip()

PATTERN = re.compile(r"(ограничен\w*|лимитирован\w*|тираж\w*)", re.IGNORECASE)
INDEX_PATTERN = re.compile(r"\b\d{4}(?:\.\d{2})?/\d{5,6}[А-ЯA-Zа-яa-z]?\b")
PRICE_PATTERN = re.compile(r"\d[\d\s]{1,10}(?:[.,]\d{2})?\s*₽")
EXCLUDE_IMG_PARTS = ("logo", "cart", "heart", "discount", "flags", "icon", "placeholder")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Восток — Лимитированные серии</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: #ffffff;
    --surface: #fafafa;
    --border: #e5e7eb;
    --border-hover: #111827;
    --text: #111827;
    --muted: #6b7280;
    --accent: #111827;
    --ok-bg: #ecfdf5;
    --ok-text: #065f46;
    --no-bg: #f3f4f6;
    --no-text: #6b7280;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.45;
  }
  .wrap { max-width: 1240px; margin: 0 auto; padding: 20px 16px 48px; }
  header {
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end;
    gap: 8px; padding-bottom: 14px; border-bottom: 1px solid var(--border);
  }
  h1 { margin: 0; font-size: 21px; font-weight: 600; letter-spacing: -0.02em; }
  .updated { font-size: 12px; color: var(--muted); }
  .stats {
    display: flex; flex-wrap: wrap; gap: 14px; margin: 14px 0 16px;
    font-size: 13px; color: var(--muted);
  }
  .stats strong { color: var(--text); font-weight: 600; }
  .controls {
    display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 20px;
  }
  input[type="search"], select {
    height: 38px; padding: 0 10px; border: 1px solid var(--border);
    border-radius: 6px; background: #fff; color: var(--text); font-size: 14px;
  }
  input[type="search"] { flex: 1 1 200px; min-width: 180px; }
  input:focus, select:focus { outline: none; border-color: var(--accent); }
  .check {
    display: inline-flex; align-items: center; gap: 6px; font-size: 14px;
    cursor: pointer; user-select: none; padding: 0 4px;
  }
  .grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 16px;
  }
  .card {
    display: flex; flex-direction: column; border: 1px solid var(--border);
    border-radius: 8px; overflow: hidden; background: #fff;
  }
  .img-box {
    position: relative; aspect-ratio: 1 / 1; background: var(--surface);
    display: flex; align-items: center; justify-content: center;
    border-bottom: 1px solid var(--border); overflow: hidden;
  }
  .img-box img {
    width: 100%; height: 100%; object-fit: contain; padding: 12px; display: block;
  }
  .no-img { font-size: 12px; color: var(--muted); }
  .badge-edition {
    position: absolute; top: 8px; left: 8px; font-size: 11px; font-weight: 600;
    padding: 3px 7px; border-radius: 4px; background: #111827; color: #fff;
  }
  .badge-stock {
    position: absolute; top: 8px; right: 8px; font-size: 11px; font-weight: 500;
    padding: 3px 7px; border-radius: 4px;
  }
  .in-stock { background: var(--ok-bg); color: var(--ok-text); }
  .out-stock { background: var(--no-bg); color: var(--no-text); }
  .body {
    padding: 12px 14px 14px; display: flex; flex-direction: column; flex: 1; gap: 5px;
  }
  .line { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
  .idx { font-size: 16px; font-weight: 600; margin: 0; }
  .snippet {
    font-size: 12px; color: var(--muted); margin: 2px 0 8px; flex: 1;
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  }
  .footer {
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px; padding-top: 10px; border-top: 1px solid var(--border);
  }
  .price { font-size: 16px; font-weight: 600; white-space: nowrap; }
  .price.empty { font-size: 13px; font-weight: 400; color: var(--muted); }
  .btn {
    display: inline-block; padding: 7px 12px; font-size: 13px; font-weight: 500;
    color: #fff; background: var(--accent); text-decoration: none;
    border-radius: 6px; white-space: nowrap;
  }
  .empty-state {
    grid-column: 1 / -1; text-align: center; padding: 40px 16px;
    color: var(--muted); border: 1px dashed var(--border); border-radius: 8px;
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Восток — лимитированные серии</h1>
    <div class="updated">Обновлено: __UPDATED_AT__</div>
  </header>

  <div class="stats" id="stats"></div>

  <div class="controls">
    <input type="search" id="q" placeholder="Поиск по индексу или описанию...">
    <select id="line">
      <option value="">Все линейки</option>
      <option value="Амфибия">Амфибия</option>
      <option value="Восток">Восток</option>
      <option value="Командирские">Командирские</option>
    </select>
    <select id="sort">
      <option value="index">По индексу</option>
      <option value="price-asc">Сначала дешевле</option>
      <option value="price-desc">Сначала дороже</option>
      <option value="edition-asc">Малый тираж</option>
    </select>
    <label class="check">
      <input type="checkbox" id="inStockOnly"> В наличии
    </label>
  </div>

  <div class="grid" id="grid"></div>
</div>

<script>
if (window.Telegram && window.Telegram.WebApp) {
  window.Telegram.WebApp.ready();
  window.Telegram.WebApp.expand();
}

const RAW_DATA = __WATCH_DATA__;

function parsePrice(str) {
  if (!str) return null;
  const cleaned = String(str).replace(/[^\\d.,]/g, "").replace(",", ".");
  const n = parseFloat(cleaned);
  return Number.isFinite(n) ? Math.round(n) : null;
}

function formatPrice(n) {
  return n == null ? "" : n.toLocaleString("ru-RU") + " ₽";
}

function parseEdition(snippet) {
  const m = String(snippet || "").match(/тираж\\s*(\\d+)/i);
  return m ? parseInt(m[1], 10) : null;
}

function detectLine(item) {
  const src = ((item.title || "") + " " + (item.url || "")).toLowerCase();
  if (src.includes("amfib") || src.includes("амфиб")) return "Амфибия";
  if (src.includes("komandir") || src.includes("командир")) return "Командирские";
  return "Восток";
}

const ITEMS = RAW_DATA.map(d => ({
  ...d,
  priceNum: parsePrice(d.price),
  editionNum: parseEdition(d.snippet),
  line: detectLine(d),
  inStock: (d.stock || "").toLowerCase().includes("есть в наличии")
}));

const grid = document.getElementById("grid");
const stats = document.getElementById("stats");
const qEl = document.getElementById("q");
const lineEl = document.getElementById("line");
const sortEl = document.getElementById("sort");
const stockEl = document.getElementById("inStockOnly");

function render() {
  const q = qEl.value.trim().toLowerCase();
  const line = lineEl.value;
  const onlyStock = stockEl.checked;
  const sort = sortEl.value;

  let list = ITEMS.filter(it => {
    if (line && it.line !== line) return false;
    if (onlyStock && !it.inStock) return false;
    if (q) {
      const hay = (it.index + " " + it.title + " " + it.snippet).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  list.sort((a, b) => {
    if (sort === "price-asc") return (a.priceNum ?? 1e9) - (b.priceNum ?? 1e9);
    if (sort === "price-desc") return (b.priceNum ?? -1) - (a.priceNum ?? -1);
    if (sort === "edition-asc") return (a.editionNum ?? 1e9) - (b.editionNum ?? 1e9);
    return (a.index || "").localeCompare(b.index || "", "ru");
  });

  const prices = list.map(i => i.priceNum).filter(n => n != null);
  const inStockCount = list.filter(i => i.inStock).length;
  const priceRange = prices.length
    ? `${formatPrice(Math.min(...prices))} — ${formatPrice(Math.max(...prices))}`
    : "—";

  stats.innerHTML = `
    <span>Моделей: <strong>${list.length}</strong></span>
    <span>В наличии: <strong>${inStockCount}</strong></span>
    <span>Цены: <strong>${priceRange}</strong></span>
  `;

  if (!list.length) {
    grid.innerHTML = '<div class="empty-state">По выбранным фильтрам модели не найдены.</div>';
    return;
  }

  grid.innerHTML = list.map(it => {
    const editionLabel = it.editionNum ? `Тираж ${it.editionNum} шт.` : "Ограниченная серия";
    const stockBadge = it.stock
      ? `<span class="badge-stock ${it.inStock ? "in-stock" : "out-stock"}">${it.stock}</span>`
      : "";
    const imgHtml = it.image
      ? `<img src="${it.image}" alt="${it.index}" loading="lazy" onerror="this.outerHTML='<span class=no-img>Нет фото</span>'">`
      : `<span class="no-img">Нет фото</span>`;
    const priceHtml = it.priceNum != null
      ? `<span class="price">${formatPrice(it.priceNum)}</span>`
      : `<span class="price empty">Цена не указана</span>`;

    return `
      <article class="card">
        <div class="img-box">
          <span class="badge-edition">${editionLabel}</span>
          ${stockBadge}
          ${imgHtml}
        </div>
        <div class="body">
          <div class="line">${it.line}</div>
          <h2 class="idx">${it.index || it.title}</h2>
          <p class="snippet">${it.snippet || ""}</p>
          <div class="footer">
            ${priceHtml}
            <a class="btn" href="${it.url}" target="_blank" rel="noopener">В магазин →</a>
          </div>
        </div>
      </article>
    `;
  }).join("");
}

[qEl, lineEl, sortEl, stockEl].forEach(el => el.addEventListener("input", render));
render();
</script>
</body>
</html>
"""


def is_product_url(url: str) -> bool:
    parsed = urlparse(url)
    if "online.vostokinc.ru" not in parsed.netloc:
        return False
    if "product_id=" in parsed.query:
        return True
    if parsed.query:
        return False
    path = parsed.path.strip("/")
    if not path.startswith("katalog-tovarov/"):
        return False
    slug = path.split("/")[-1]
    return bool(re.search(r"\d{3,}", slug))


def collect_all_product_urls():
    session = requests.Session()
    session.headers.update(HEADERS)
    urls = set()
    page = 1

    while True:
        page_url = f"{CATALOG_URL}?page={page}" if page > 1 else CATALOG_URL
        resp = session.get(page_url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        found_on_page = set()
        for a in soup.find_all("a", href=True):
            full_url = urljoin(BASE_URL, a["href"]).split("#")[0]
            if is_product_url(full_url):
                found_on_page.add(full_url)

        new_urls = found_on_page - urls
        urls.update(new_urls)
        print(f"Страница каталога {page}: +{len(new_urls)} моделей (всего {len(urls)})")

        has_next = soup.find("link", rel="next") is not None
        if not has_next and not new_urls:
            break
        if not new_urls and page > 1:
            break

        page += 1
        time.sleep(0.2)

    return sorted(urls)


def extract_image_url(soup: BeautifulSoup, page_url: str) -> str:
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return urljoin(page_url, og["content"])

    content = soup.select_one("#content") or soup
    for selector in (".thumbnails a.thumbnail", ".product-image img", ".image img", "#image"):
        el = content.select_one(selector)
        if el:
            src = el.get("href") or el.get("src")
            if src:
                return urljoin(page_url, src)

    for img in content.find_all("img", src=True):
        src = img["src"]
        low = src.lower()
        if any(bad in low for bad in EXCLUDE_IMG_PARTS):
            continue
        if "image/cache/catalog" in low or "image/catalog" in low:
            return urljoin(page_url, src)

    return ""


def extract_price(soup: BeautifulSoup) -> str:
    content = soup.select_one("#content") or soup
    for selector in (
        ".price",
        ".product-price",
        ".autocalc-product-price",
        "ul.list-unstyled h2",
        "h2",
    ):
        for el in content.select(selector):
            m = PRICE_PATTERN.search(el.get_text(" ", strip=True))
            if m:
                return m.group(0).strip()

    m = PRICE_PATTERN.search(content.get_text(" ", strip=True))
    return m.group(0).strip() if m else ""


def parse_product(url: str):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    image_url = extract_image_url(soup, url)

    title_el = soup.find("h1")
    title = title_el.get_text(" ", strip=True) if title_el else ""
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
        title = re.sub(r"^Купить часы\s+Каталог товаров\s+", "", title, flags=re.I)
        title = re.sub(r"\s+недорого$", "", title, flags=re.I)

    for tag in soup(["header", "footer", "script", "style", "nav"]):
        tag.decompose()

    content = soup.select_one("#content") or soup
    page_text = content.get_text(" ", strip=True)
    m = PATTERN.search(page_text)
    if not m:
        return None

    match_idx = INDEX_PATTERN.search(title) or INDEX_PATTERN.search(page_text)
    model_index = match_idx.group(0) if match_idx else title

    start = max(0, m.start() - 40)
    end = min(len(page_text), m.end() + 80)
    snippet = page_text[start:end].strip()

    price = extract_price(soup)

    stock = ""
    if "Есть в наличии" in page_text:
        stock = "Есть в наличии"
    elif "Нет в наличии" in page_text:
        stock = "Нет в наличии"

    return {
        "index": model_index,
        "title": title,
        "price": price,
        "stock": stock,
        "snippet": snippet,
        "image": image_url,
        "url": url,
    }


def load_previous_data(filepath: str) -> dict:
    if not os.path.exists(filepath):
        return {}
    prev = {}
    with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            if row.get("url"):
                prev[row["url"]] = row
    return prev


def send_telegram_alert(item: dict, header_text: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return

    caption = (
        f"<b>{header_text}</b>\n\n"
        f"Модель: <b>{item['index']}</b>\n"
        f"Цена: {item['price'] or 'не указана'}\n"
        f"Наличие: {item['stock'] or 'не указано'}\n"
        f"<a href=\"{item['url']}\">Открыть в магазине</a>"
    )

    api_base = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"
    try:
        if item.get("image"):
            r = requests.post(
                f"{api_base}/sendPhoto",
                data={
                    "chat_id": TG_CHAT_ID,
                    "photo": item["image"],
                    "caption": caption,
                    "parse_mode": "HTML",
                },
                timeout=15,
            )
            if r.ok:
                return
        requests.post(
            f"{api_base}/sendMessage",
            data={
                "chat_id": TG_CHAT_ID,
                "text": caption,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")


def notify_changes(prev_map: dict, new_items: list):
    if not prev_map or not TG_BOT_TOKEN or not TG_CHAT_ID:
        return

    for item in new_items:
        old = prev_map.get(item["url"])
        if not old:
            send_telegram_alert(item, "🆕 Новая лимитированная модель")
            time.sleep(0.5)
        else:
            was_in_stock = "есть в наличии" in (old.get("stock") or "").lower()
            now_in_stock = "есть в наличии" in (item.get("stock") or "").lower()
            if not was_in_stock and now_in_stock:
                send_telegram_alert(item, "✅ Снова в наличии")
                time.sleep(0.5)
            elif old.get("price") and item.get("price") and old["price"] != item["price"]:
                send_telegram_alert(
                    item, f"💰 Изменилась цена ({old['price']} → {item['price']})"
                )
                time.sleep(0.5)


def build_html(results, output_html=HTML_FILE):
    data_json = json.dumps(results, ensure_ascii=False).replace("</", "<\\/")
    updated_at = datetime.now().strftime("%d.%m.%Y %H:%M")
    html = HTML_TEMPLATE.replace("__WATCH_DATA__", data_json).replace("__UPDATED_AT__", updated_at)
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    prev_map = load_previous_data(CSV_FILE)

    print("Шаг 1. Собираем все модели из каталога...")
    urls = collect_all_product_urls()
    print(f"\nВсего собрано карточек: {len(urls)}")
    if not urls:
        return

    print("Шаг 2. Проверяем описания, фото, цены и наличие...\n")
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(parse_product, u): u for u in urls}
        for done, future in enumerate(as_completed(futures), 1):
            url = futures[future]
            try:
                item = future.result()
                if item:
                    results.append(item)
                    print(f"[{done}/{len(urls)}] НАЙДЕНО: {item['index']} | {item['price']}")
            except Exception as e:
                print(f"[{done}/{len(urls)}] Ошибка ({url}): {e}")

    results.sort(key=lambda x: x["index"])

    notify_changes(prev_map, results)

    fieldnames = ["index", "title", "price", "stock", "snippet", "image", "url"]
    with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(results)

    build_html(results, HTML_FILE)
    print(f"\nГотово! Моделей: {len(results)}. Обновлены {CSV_FILE} и {HTML_FILE}.")


if __name__ == "__main__":
    main()