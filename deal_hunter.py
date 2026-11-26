import os
import re
import json
import time
import hashlib
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from html import unescape
import requests
from bs4 import BeautifulSoup

# ==============================================================================
# КОНФИГУРАЦИЯ И ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

MIN_DISCOUNT_PERCENT = int(os.environ.get("MIN_DISCOUNT_PERCENT", "50"))
MAX_NEW_DEALS_PER_RUN = int(os.environ.get("MAX_NEW_DEALS_PER_RUN", "8"))
CONTACT_HANDLE = os.environ.get("CONTACT_HANDLE", "@y0uarecl0wn")

STATE_FILE = Path(__file__).parent / "seen_deals.json"

TARGET_BRANDS = [
    "Jomashop",
    "Nike",
    "Adidas",
    "Calvin Klein",
    "Tommy Hilfiger",
    "Guess",
    "Karl Lagerfeld",
    "Michael Kors",
    "Coach",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ==============================================================================
# ХРАНИЛИЩЕ СОСТОЯНИЯ (seen_deals.json)
# ==============================================================================
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("seen_ids", [])
                    data.setdefault("last_update_id", 0)
                    return data
        except Exception as e:
            print(f"[WARN] Ошибка чтения {STATE_FILE}: {e}")
    return {"seen_ids": [], "last_update_id": 0}


def save_state(state: dict) -> None:
    # Храним последние 3000 ID, чтобы файл не разрастался бесконечно
    state["seen_ids"] = state.get("seen_ids", [])[-3000:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def make_deal_id(url: str, title: str) -> str:
    raw = f"{url.strip()}|{title.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


# ==============================================================================
# 1. ОБРАБОТКА ОТВЕТОВ ПОЛЬЗОВАТЕЛЯ В TELEGRAM (ПОДСТАНОВКА ЦЕНЫ В ГРН)
# ==============================================================================
def process_telegram_price_replies(state: dict) -> None:
    """
    Проверяет входящие сообщения в Telegram.
    Если ты ответил (Reply) на карточку товара числом (например, '6000' или '6000 грн'),
    бот заменяет '💰 Ціна: [Вкажи ціну] грн' на '💰 Ціна: 6000 грн' и присылает
    чистый готовый пост (с фото или текстом) для пересылки в канал/Инстаграм.
    """
    if not TELEGRAM_BOT_TOKEN:
        return

    last_update_id = state.get("last_update_id", 0)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"offset": last_update_id + 1, "timeout": 2}

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if not data.get("ok"):
            return

        for update in data.get("result", []):
            update_id = update["update_id"]
            state["last_update_id"] = max(state.get("last_update_id", 0), update_id)

            msg = update.get("message") or update.get("channel_post")
            if not msg:
                continue

            chat_id = str(msg.get("chat", {}).get("id", ""))
            if TELEGRAM_CHAT_ID and chat_id != str(TELEGRAM_CHAT_ID):
                continue

            reply_to = msg.get("reply_to_message")
            user_text = (msg.get("text") or "").strip()
            if not reply_to or not user_text:
                continue

            # Ищем число цены в ответе (например: "6000", "6 000", "6000 грн")
            price_match = re.search(r"(\d[\d\s.,]*)", user_text)
            if not price_match:
                continue

            clean_price = re.sub(r"[^\d]", "", price_match.group(1))
            if not clean_price:
                continue

            original_text = reply_to.get("caption") or reply_to.get("text") or ""
            if not original_text:
                continue

            # Отрезаем служебный блок байера (всё, что ниже разделителя '---')
            post_body = original_text.split("────────────")[0].strip()

            # Заменяем плейсхолдер цены на введённую сумму
            updated_post = re.sub(
                r"💰\s*Ціна:.*",
                f"💰 Ціна: {clean_price} грн",
                post_body,
            )
            if f"💰 Ціна: {clean_price} грн" not in updated_post:
                updated_post += f"\n\n💰 Ціна: {clean_price} грн"

            # Если в исходном сообщении было фото — отправляем с тем же file_id
            photos = reply_to.get("photo")
            if photos:
                best_photo_id = photos[-1]["file_id"]
                send_telegram_photo(
                    chat_id=chat_id,
                    photo_ref=best_photo_id,
                    caption=updated_post,
                    reply_to_message_id=msg["message_id"],
                )
            else:
                send_telegram_text(
                    chat_id=chat_id,
                    text=updated_post,
                    reply_to_message_id=msg["message_id"],
                )
            print(f"[INFO] Сформирован готовый пост с ценой {clean_price} грн")

    except Exception as e:
        print(f"[WARN] Ошибка при проверке ответов Telegram: {e}")


# ==============================================================================
# 2. ИСТОЧНИКИ СКИДОК (БЕЗ ПЛАТНЫХ ПРОКСИ, РАБОТАЮТ ИЗ GITHUB ACTIONS)
# ==============================================================================
def fetch_nike_us_clearance() -> list[dict]:
    """
    Запрашивает официальный публичный каталог Nike US Sale через API browse/v2.
    Отбирает позиции со скидкой >= MIN_DISCOUNT_PERCENT.
    """
    deals = []
    # endpoint каталога скидок Nike US
    api_url = (
        "https://api.nike.com/cic/browse/v2"
        "?queryid=products"
        "&anonymousId=usdealbot123"
        "&country=us"
        "&endpoint=%2Fproduct_feed%2Frollup_threads%2Fv2"
        "%3Ffilter%3Dmarketplace(US)"
        "%26filter%3Dlanguage(en)"
        "%26filter%3DemployeePrice(true)"
        "%26filter%3DonSale(true)"
        "%26anchor%3D0"
        "%26consumerChannelId%3Dd9a5bc42-4b9c-4976-858a-f159cf99c647"
        "%26count%3D40"
    )
    try:
        resp = requests.get(api_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return deals
        payload = resp.json()
        products = (
            payload.get("data", {})
            .get("products", {})
            .get("products", [])
        )
        for item in products:
            title = item.get("title", "")
            subtitle = item.get("subtitle", "")
            full_title = f"Nike {title} ({subtitle})" if subtitle else f"Nike {title}"

            price_info = item.get("price", {}) or {}
            current_price = float(price_info.get("currentPrice") or 0)
            full_price = float(price_info.get("fullPrice") or 0)
            if current_price <= 0 or full_price <= current_price:
                continue

            discount = round((1 - current_price / full_price) * 100)
            if discount < MIN_DISCOUNT_PERCENT:
                continue

            raw_url = item.get("url", "").replace("{countryLang}", "https://www.nike.com")
            if raw_url.startswith("/"):
                raw_url = f"https://www.nike.com{raw_url}"

            image_url = item.get("images", {}).get("squarishURL") or item.get("images", {}).get("portraitURL") or ""
            colors_count = len(item.get("colorways", []) or [])
            color_desc = item.get("colorDescription", "")

            deals.append({
                "source": "Nike US Official",
                "brand": "Nike",
                "title": full_title,
                "sale_price": current_price,
                "original_price": full_price,
                "discount_pct": discount,
                "url": raw_url,
                "image_url": image_url,
                "details": f"Color: {color_desc}. Total available colorways: {colors_count}. Category: {subtitle}",
            })
    except Exception as e:
        print(f"[WARN] Nike US API: {e}")
    return deals


def fetch_shopsimon_brands() -> list[dict]:
    """
    Парсит публичный Shopify JSON-каталог крупных американских аутлетов/магазинов
    (ShopSimon / ShopPremiumOutlets и аналогичные витрины с Adidas, Guess, CK, Tommy, Karl Lagerfeld).
    """
    deals = []
    # Список коллекций на базе Shopify, отдающих открытый products.json
    shopify_feeds = [
        ("ShopSimon Adidas Outlet", "Adidas", "https://shopsimon.com/collections/adidas/products.json?limit=50"),
        ("ShopSimon Karl Lagerfeld", "Karl Lagerfeld", "https://shopsimon.com/collections/karl-lagerfeld-paris/products.json?limit=50"),
        ("ShopSimon Guess Outlet", "Guess", "https://shopsimon.com/collections/guess/products.json?limit=50"),
        ("ShopSimon Calvin Klein", "Calvin Klein", "https://shopsimon.com/collections/calvin-klein/products.json?limit=50"),
        ("ShopSimon Tommy Hilfiger", "Tommy Hilfiger", "https://shopsimon.com/collections/tommy-hilfiger/products.json?limit=50"),
    ]

    for source_name, brand, feed_url in shopify_feeds:
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            products = resp.json().get("products", [])
            for prod in products:
                title = prod.get("title", "")
                handle = prod.get("handle", "")
                variants = prod.get("variants", [])
                if not variants:
                    continue

                v = variants[0]
                sale_price = float(v.get("price") or 0)
                orig_price = float(v.get("compare_at_price") or 0)
                if sale_price <= 0 or orig_price <= sale_price:
                    continue

                discount = round((1 - sale_price / orig_price) * 100)
                if discount < MIN_DISCOUNT_PERCENT:
                    continue

                images = prod.get("images", [])
                image_url = images[0].get("src", "") if images else ""

                body_html = prod.get("body_html") or ""
                clean_desc = BeautifulSoup(body_html, "html.parser").get_text(" ", strip=True)

                # Собираем доступные цвета/размеры из вариантов
                avail_options = set()
                for var in variants:
                    if var.get("available", True) and var.get("title"):
                        avail_options.add(var.get("title"))

                base_domain = "/".join(feed_url.split("/")[:3])
                product_url = f"{base_domain}/products/{handle}"

                deals.append({
                    "source": source_name,
                    "brand": brand,
                    "title": f"{brand} {title}" if brand.lower() not in title.lower() else title,
                    "sale_price": sale_price,
                    "original_price": orig_price,
                    "discount_pct": discount,
                    "url": product_url,
                    "image_url": image_url,
                    "details": f"{clean_desc[:500]}. Variants: {', '.join(list(avail_options)[:8])}",
                })
        except Exception as e:
            print(f"[WARN] Ошибка фида {source_name}: {e}")

    return deals


def fetch_slickdeals_brand_feeds() -> list[dict]:
    """
    Ищет горячие скидки по целевым брендам (Jomashop, Nike, Adidas, Calvin Klein,
    Tommy Hilfiger, Guess, Karl Lagerfeld, Michael Kors, Coach) через RSS-поиск Slickdeals.
    """
    deals = []
    for brand in TARGET_BRANDS:
        encoded = urllib.parse.quote_plus(brand)
        rss_url = (
            f"https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals"
            f"&searchin=first&rss=1&q={encoded}"
        )
        try:
            resp = requests.get(rss_url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue

            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:10]:
                raw_title = unescape(item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc_html = item.findtext("description") or ""

                # Ищем процент скидки или пару цен ($XX vs $YY) в заголовке или описании
                soup = BeautifulSoup(desc_html, "html.parser")
                desc_text = soup.get_text(" ", strip=True)
                img_tag = soup.find("img")
                image_url = img_tag["src"] if img_tag and img_tag.get("src") else ""

                combined_text = f"{raw_title} {desc_text}"

                # Проверяем явный процент скидки (например, "65% Off")
                pct_match = re.search(r"(\d{2})\s*%\s*off", combined_text, re.IGNORECASE)
                # Ищем цены формата $49.99
                prices = [
                    float(p.replace(",", ""))
                    for p in re.findall(r"\$\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?)", combined_text)
                ]

                sale_price = 0.0
                orig_price = 0.0
                discount = 0

                if len(prices) >= 2:
                    sorted_p = sorted(set(prices))
                    if sorted_p[0] > 0 and sorted_p[-1] > sorted_p[0]:
                        sale_price = sorted_p[0]
                        orig_price = sorted_p[-1]
                        discount = round((1 - sale_price / orig_price) * 100)
                elif len(prices) == 1:
                    sale_price = prices[0]

                if pct_match:
                    discount = max(discount, int(pct_match.group(1)))
                    if sale_price > 0 and orig_price == 0 and discount < 100:
                        orig_price = round(sale_price / (1 - discount / 100.0), 2)

                if discount < MIN_DISCOUNT_PERCENT:
                    continue

                deals.append({
                    "source": f"Slickdeals ({brand})",
                    "brand": brand,
                    "title": raw_title,
                    "sale_price": sale_price,
                    "original_price": orig_price,
                    "discount_pct": discount,
                    "url": link,
                    "image_url": image_url,
                    "details": desc_text[:600],
                })
        except Exception as e:
            print(f"[WARN] Ошибка RSS Slickdeals ({brand}): {e}")

    return deals


# ==============================================================================
# 3. ГЕНЕРАЦИЯ УКРАИНСКОГО ПОСТА ПО ТВОЕМУ ШАБЛОНУ ЧЕРЕЗ GEMINI API (БЕСПЛАТНО)
# ==============================================================================
def generate_ukrainian_post(deal: dict) -> str:
    """
    Генерирует готовый пост на украинском языке строго по шаблону Karl Lagerfeld.
    Автоматически переводит дюймы в сантиметры и оставляет поле цены для быстрого ввода.
    """
    prompt = f"""Ти — досвідчений фешн-копірайтер для українського Telegram/Instagram-каналу байєра брендових речей зі США.
Створи готовий пост українською мовою СТРОГО за наведеним нижче шаблоном і структурою.

ВХІДНІ ДАНІ ПРО ТОВАР:
- Бренд: {deal['brand']}
- Назва: {deal['title']}
- Деталі та характеристики (англ.): {deal['details']}

ПРАВИЛА ОФОРМЛЕННЯ:
1. Перший рядок: 🔥 [Оригінальна англійська назва бренду та моделі без зайвого сміття на кшталт "60% Off" або "Free Shipping"]
2. Другий абзац: Живий, привабливий опис моделі українською мовою (2-3 речення: силует, фактура, деталі, з чим носити або чому це крута пропозиція).
3. Абзац про колір: 🎨 Опиши колір на фото та інші доступні кольори/варіанти під викуп (якщо інформація про кольори є в деталях; якщо немає — напиши лаконічно про класичне/актуальне виконання моделі).
4. Блок "Характеристики:":
   - Матеріали / Склад (або Механізм/Скло для годинників, Ноти/Об'єм для парфумів)
   - Габарити / Розміри (ВАЖЛИВО: якщо в англійському описі є дюйми (inches / "), ОБОВ'ЯЗКОВО переведи їх у сантиметри за формулою 1 inch = 2.54 см, формат: 28,5 × 9,7 × 10 см. Якщо габаритів немає — вкажи доступну розмірну сітку або тип посадки).
   - Особливості: ключові фішки моделі (застібки, кишені, технологія підошви, водозахист тощо).
5. Рядок оригіналу: 💎 Тільки 100% оригінал.
6. Рядок ціни (залиш саме такий плейсхолдер, щоб байєр підставив свою ціну): 💰 Ціна: [Вкажи ціну] грн
7. Останній рядок: 📩 З усіх питань, за фото інших кольорів та для швидкого оформлення замовлення - {CONTACT_HANDLE}
8. НЕ використовуй Markdown-зірочки (** або *), пиши чистим текстом як у прикладі.

ЕТАЛОННИЙ ПРИКЛАД:
🔥 Karl Lagerfeld Croco Elongated Shoulder Bag

Ефектна жіноча сумка в актуальному подовженому силуеті від Karl Lagerfeld. Глянцева фактура під крокодила, подвійні регульовані ремінці та лаконічний металевий брендинг спереду роблять її ідеальним акцентом як під кежуал-образи, так і на вечірній вихід.

🎨 На фото представлений класичний чорний, але під викуп також доступні м'який чайно-зелений та насичений червоний кольори.

Характеристики:
Матеріали: 50% поліуретан, 50% поліестер; підкладка - 100% перероблений поліестер
Габарити: 28,5 × 9,7 × 10 см
Особливості: верхня застібка-блискавка, внутрішня кишеня, регульовані подвійні плечові ремінці

💎 Тільки 100% оригінал.

💰 Ціна: [Вкажи ціну] грн

📩 З усіх питань, за фото інших кольорів та для швидкого оформлення замовлення - {CONTACT_HANDLE}
"""

    if GEMINI_API_KEY:
        try:
            api_url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
            )
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.4},
            }
            resp = requests.post(api_url, json=payload, timeout=25)
            if resp.status_code == 200:
                candidates = resp.json().get("candidates", [])
                if candidates:
                    text = (
                        candidates[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                        .strip()
                    )
                    if text:
                        return text.replace("**", "")
        except Exception as e:
            print(f"[WARN] Ошибка Gemini API, использую резервный шаблон: {e}")

    # Резервный шаблон, если ключ Gemini не задан или лимит временно исчерпан
    return (
        f"🔥 {deal['title']}\n\n"
        f"Стильна оригінальна позиція від бренду {deal['brand']} напряму зі США за суперціною.\n\n"
        f"🎨 Уточнюйте доступні кольори та розміри під викуп.\n\n"
        f"Характеристики:\n"
        f"Бренд: {deal['brand']}\n"
        f"Особливості: {deal['details'][:220]}\n\n"
        f"💎 Тільки 100% оригінал.\n\n"
        f"💰 Ціна: [Вкажи ціну] грн\n\n"
        f"📩 З усіх питань, за фото інших кольорів та для швидкого оформлення замовлення - {CONTACT_HANDLE}"
    )


# ==============================================================================
# 4. ОТПРАВКА КАРТОЧКИ ТОВАРА В TELEGRAM
# ==============================================================================
def send_telegram_photo(chat_id: str, photo_ref: str, caption: str, reply_to_message_id: int | None = None) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo_ref,
        "caption": caption[:1024],
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    resp = requests.post(url, json=payload, timeout=15)
    return resp.status_code == 200 and resp.json().get("ok", False)


def send_telegram_text(chat_id: str, text: str, reply_to_message_id: int | None = None) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4096],
        "disable_web_page_preview": False,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    resp = requests.post(url, json=payload, timeout=15)
    return resp.status_code == 200 and resp.json().get("ok", False)


def format_buyer_card(post_text: str, deal: dict) -> str:
    sale_str = f"${deal['sale_price']:.2f}" if deal["sale_price"] > 0 else "см. на сайте"
    orig_str = f"${deal['original_price']:.2f}" if deal["original_price"] > 0 else "—"
    buyer_info = (
        f"\n\n────────────────────\n"
        f"🛒 Магазин: {deal['source']}\n"
        f"💵 Цена в США: {sale_str} (была {orig_str} | -{deal['discount_pct']}%)\n"
        f"🔗 Ссылка: {deal['url']}\n"
        f"💡 Ответь (Reply) на это сообщение числом (например: 6000), и я пришлю чистый пост с этой ценой!"
    )
    return post_text + buyer_info


# ==============================================================================
# ГЛАВНЫЙ ЦИКЛ
# ==============================================================================
def main() -> None:
    state = load_state()

    # Шаг 1: Проверяем, не ответил ли пользователь ценой в грн на прошлые находки
    process_telegram_price_replies(state)

    # Шаг 2: Собираем свежие скидки >= 50% по всем источникам
    all_deals = []
    all_deals.extend(fetch_shopsimon_brands())
    all_deals.extend(fetch_nike_us_clearance())
    all_deals.extend(fetch_slickdeals_brand_feeds())

    print(f"[INFO] Всего найдено кандидатов со скидкой >= {MIN_DISCOUNT_PERCENT}%: {len(all_deals)}")

    seen_set = set(state.get("seen_ids", []))
    new_deals = []

    for d in all_deals:
        deal_id = make_deal_id(d["url"], d["title"])
        if deal_id not in seen_set:
            d["id"] = deal_id
            new_deals.append(d)

    # Сортируем по максимальному проценту скидки
    new_deals.sort(key=lambda x: x.get("discount_pct", 0), reverse=True)
    batch = new_deals[:MAX_NEW_DEALS_PER_RUN]

    print(f"[INFO] Новых уникальных находок для отправки в этом запуске: {len(batch)}")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы. Вывожу пример первой карточки в консоль:")
        if batch:
            sample_post = generate_ukrainian_post(batch[0])
            print(format_buyer_card(sample_post, batch[0]))
        save_state(state)
        return

    for deal in batch:
        post_text = generate_ukrainian_post(deal)
        full_caption = format_buyer_card(post_text, deal)

        sent = False
        if deal.get("image_url"):
            sent = send_telegram_photo(TELEGRAM_CHAT_ID, deal["image_url"], full_caption)
        if not sent:
            sent = send_telegram_text(TELEGRAM_CHAT_ID, full_caption)

        if sent:
            state["seen_ids"].append(deal["id"])
            time.sleep(2)

    save_state(state)
    print("[INFO] Цикл успешно завершён.")


if __name__ == "__main__":
    main()
