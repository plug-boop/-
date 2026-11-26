import os
import re
import json
import time
import hashlib
from pathlib import Path
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
MAX_MEGA_SALE_ALERTS_PER_RUN = int(os.environ.get("MAX_MEGA_SALE_ALERTS_PER_RUN", "3"))
CONTACT_HANDLE = os.environ.get("CONTACT_HANDLE", "@y0uarecl0wn")

STATE_FILE = Path(__file__).parent / "seen_deals.json"

# ==============================================================================
# ТОП-20 ОФИЦИАЛЬНЫХ САЙТОВ И АУТЛЕТОВ США (БЕСТСЕЛЛЕРЫ УКРАИНЫ)
# (6pm и Slickdeals полностью исключены!)
# ==============================================================================
ALLOWED_DOMAINS = (
    "jomashop.com",
    "nike.com",
    "shopsimon.com",
    "karllagerfeldparis.com",
    "dkny.com",
    "champion.com",
    "uspoloassn.com",
    "juicycouture.com",
    "stevemadden.com",
    "ninewest.com",
    "rebeccaminkoff.com",
    "joesnewbalanceoutlet.com",
    "nordstromrack.com",
    "michaelkors.com",
    "calvinklein.us",
    "tommy.com",
    "guess.com",
    "guessfactory.com",
    "coachoutlet.com",
    "katespadeoutlet.com",
    "lacoste.com",
    "diesel.com",
    "adidas.com",
    "puma.com",
    "levis.com",
    "victoriassecret.com",
    "nautica.com",
)

# ==============================================================================
# БЕЛЫЙ СПИСОК БРЕНДОВ (ТОП-БЕСТСЕЛЛЕРЫ УКРАИНЫ ИЗ США И ЕВРОПЫ)
# ==============================================================================
ALLOWED_BRANDS = [
    # Главные приоритеты
    "Calvin Klein",
    "Tommy Hilfiger",
    "Guess",
    "Karl Lagerfeld",
    "Michael Kors",
    "Diesel",
    "Lacoste",
    "Adidas",
    "Nike",
    # Бестселлеры в Украине (американские и европейские хиты для байеров)
    "Coach",
    "Polo Ralph Lauren",
    "Ralph Lauren",
    "New Balance",
    "Puma",
    "Timberland",
    "Levi's",
    "Levis",
    "The North Face",
    "Columbia",
    "Converse",
    "Vans",
    "Reebok",
    "Under Armour",
    "Marc Jacobs",
    "Tory Burch",
    "Kate Spade",
    "DKNY",
    "Armani Exchange",
    "Emporio Armani",
    "Hugo Boss",
    "BOSS",
    "Versace",
    "Versus Versace",
    "Burberry",
    "Furla",
    "Pinko",
    "Tissot",
    "Seiko",
    "Citizen",
    "Bulova",
    "Fossil",
    "Ray-Ban",
    "Victoria's Secret",
    "Steve Madden",
    "U.S. Polo Assn",
    "US Polo Assn",
    "Champion",
    "Juicy Couture",
    "Nine West",
    "Rebecca Minkoff",
    "Nautica",
    "Crocs",
    "UGG",
    "Dr. Martens",
    "Asics",
]

# ==============================================================================
# БАНВОРДЫ: АРАБСКАЯ ПАРФЮМЕРИЯ, ИГРЫ, ТЕХНИКА, ЕДА И МУСОР
# ==============================================================================
BANNED_ARABIC_PERFUME_BRANDS = [
    "afnan", "lattafa", "armaf", "al haramain", "rasasi", "ajmal",
    "swiss arabian", "zimaya", "maison alhambra", "alhambra", "paris corner",
    "fragrance world", "ard al zaafaran", "khadlaj", "al wataniah",
    "orientica", "bharara", "asdaaf", "al rehab", "anfar", "kayaan",
    "ameer al oudh", "khamrah", "asad", "yara", "9pm", "club de nuit",
    "amber oud", "fakhar", "qaed", "badee al oud", "maahir", "ramz",
    "rave now", "turathi", "supremacy", "modest une", "detour noir",
    "shaghaf", "hawas", "jannan", "kismet", "pendora", "charuto",
    "emir", "ministry of oud", "oud mood", "velvet oud", "ana abiyedh",
    "ejazi", "raghba", "hayaati", "najdia", "ra'ed", "ishq al shuyukh",
    "al qiam", "tharwah", "eternal oud", "mayar", "ansend", "dumont",
    "borouj", "arabiyat", "grandeur", "emper", "milestone", "camara",
    "lataffa", "al absar", "al asrar", "al fares", "ahmed al maghribi",
    "ajyad", "almas", "amaran", "aouj", "auraa desire", "azha",
]

BANNED_KEYWORDS = [
    # Игры, консоли, игрушки, коллекционные карточки
    "game", "gaming", "xbox", "playstation", "ps4", "ps5", "nintendo",
    "switch", "steam", "roblox", "minecraft", "fortnite", "pokemon",
    "trading card", "yu-gi-oh", "magic the gathering", "funko", "lego",
    "board game", "puzzle", "doll", "barbie", "hot wheels", "nerf",
    "controller", "joystick", "gamepad", "console", "esports",
    # Техника, электроника, инструменты, бытовые приборы
    "printer", "3d", "filament", "laptop", "notebook", "desktop",
    "monitor", "television", "smart tv", "oled", "qled", "projector",
    "router", "modem", "ssd", "hard drive", "nvme", "ram", "motherboard",
    "graphics card", "gpu", "cpu", "processor", "keyboard", "mouse",
    "webcam", "microphone", "speaker", "soundbar", "subwoofer", "earbuds",
    "airpods", "headset", "headphones", "charger", "adapter", "cable",
    "power bank", "battery", "ups", "surge protector", "vacuum", "roomba",
    "blender", "mixer", "toaster", "microwave", "air fryer", "coffee maker",
    "espresso", "refrigerator", "washer", "dryer", "dishwasher", "iron",
    "hair dryer", "straightener", "curling", "shaver", "trimmer", "epilator",
    "toothbrush", "drill", "saw", "screwdriver", "wrench", "hammer",
    "flashlight", "generator", "lawn mower", "pressure washer", "dash cam",
    "camera", "lens", "tripod", "drone", "gopro", "garmin", "fitbit",
    "smartwatch", "apple watch", "galaxy watch", "iphone", "ipad", "macbook",
    "samsung", "xiaomi", "lenovo", "asus", "acer", "dell", "hp ",
    # Продукты питания, напитки, БАДы, витамины, корма
    "food", "snack", "chocolate", "candy", "cookie", "biscuit", "chips",
    "cracker", "cereal", "oatmeal", "pasta", "noodle", "sauce", "ketchup",
    "mayonnaise", "olive oil", "vinegar", "spice", "seasoning", "coffee",
    "tea ", "matcha", "juice", "soda", "energy drink", "water", "milk",
    "cheese", "butter", "yogurt", "meat", "beef", "chicken", "pork",
    "fish", "salmon", "tuna", "shrimp", "protein", "whey", "creatine",
    "bcaa", "pre-workout", "vitamin", "supplement", "collagen", "omega-3",
    "probiotic", "melatonin", "gummies", "capsule", "tablet", "pill",
    "syrup", "grocery", "organic food", "dog food", "cat food", "pet food",
    "treat", "kibble",
    # Прочий нецелевой мусор
    "gift card", "e-gift", "voucher", "mattress", "pillow", "bedding",
    "sheet set", "comforter", "blanket", "towel", "curtain", "rug",
    "carpet", "sofa", "couch", "chair", "desk", "table", "bookshelf",
    "cabinet", "wardrobe", "cookware", "pan ", "pot ", "skillet",
    "knife set", "cutlery", "plate", "bowl", "mug", "tumbler", "stanley",
    "diaper", "stroller", "car seat", "motor oil", "tire", "brake",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
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
                    data.setdefault("seen_sale_events", [])
                    data.setdefault("last_update_id", 0)
                    return data
        except Exception as e:
            print(f"[WARN] Ошибка чтения {STATE_FILE}: {e}")
    return {"seen_ids": [], "seen_sale_events": [], "last_update_id": 0}


def save_state(state: dict) -> None:
    state["seen_ids"] = state.get("seen_ids", [])[-3500:]
    state["seen_sale_events"] = state.get("seen_sale_events", [])[-500:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def make_deal_id(url: str, title: str) -> str:
    raw = f"{url.strip()}|{title.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def is_valid_fashion_deal(title: str, brand: str, url: str, details: str = "") -> bool:
    """
    Строгая фильтрация:
    1) Отсекает любые арабские бренды парфюмерии (Afnan, Lattafa, Armaf, Al Haramain и т.д.)
    2) Отсекает игры, технику, электронику, еду, БАДы и бытовой мусор
    3) Пропускает только бренды-бестселлеры из ALLOWED_BRANDS
    4) Проверяет, что сайт — только из проверенных магазинов США (ALLOWED_DOMAINS)
    """
    combined = f"{brand} {title} {details} {url}".lower()

    for arabic_word in BANNED_ARABIC_PERFUME_BRANDS:
        if arabic_word in combined:
            return False

    for bad_word in BANNED_KEYWORDS:
        if bad_word in combined:
            return False

    title_and_brand = f"{brand} {title}".lower()
    if not any(b.lower() in title_and_brand for b in ALLOWED_BRANDS):
        return False

    if not any(d in url.lower() for d in ALLOWED_DOMAINS):
        return False

    return True


# ==============================================================================
# 1. НАДЁЖНАЯ ОТПРАВКА КАРТИНОК И СООБЩЕНИЙ В TELEGRAM
# ==============================================================================
def send_telegram_photo(
    chat_id: str,
    photo_url_or_file_id: str,
    caption: str,
    reply_to_message_id: int | None = None,
) -> bool:
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    if not photo_url_or_file_id.startswith("http"):
        payload = {
            "chat_id": chat_id,
            "photo": photo_url_or_file_id,
            "caption": caption[:1024],
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        resp = requests.post(api_url, json=payload, timeout=15)
        return resp.status_code == 200 and resp.json().get("ok", False)

    try:
        img_resp = requests.get(photo_url_or_file_id, headers=HEADERS, timeout=15)
        if img_resp.status_code == 200 and len(img_resp.content) > 1000:
            data = {
                "chat_id": chat_id,
                "caption": caption[:1024],
            }
            if reply_to_message_id:
                data["reply_to_message_id"] = str(reply_to_message_id)
            files = {"photo": ("product.jpg", img_resp.content, "image/jpeg")}
            tg_resp = requests.post(api_url, data=data, files=files, timeout=20)
            if tg_resp.status_code == 200 and tg_resp.json().get("ok", False):
                return True
    except Exception as e:
        print(f"[WARN] Не удалось загрузить фото байтами ({photo_url_or_file_id}): {e}")

    try:
        payload = {
            "chat_id": chat_id,
            "photo": photo_url_or_file_id,
            "caption": caption[:1024],
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        resp = requests.post(api_url, json=payload, timeout=15)
        return resp.status_code == 200 and resp.json().get("ok", False)
    except Exception:
        return False


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


# ==============================================================================
# 2. ОБРАБОТКА ТВОИХ ОТВЕТОВ (REPLY) С ЦЕНОЙ В ГРН В TELEGRAM
# ==============================================================================
def process_telegram_price_replies(state: dict) -> int:
    if not TELEGRAM_BOT_TOKEN:
        return 0

    processed_count = 0
    last_update_id = state.get("last_update_id", 0)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"offset": last_update_id + 1, "timeout": 2}

    try:
        resp = requests.get(url, params=params, timeout=12)
        data = resp.json()
        if not data.get("ok"):
            return 0

        updates = data.get("result", [])
        for update in updates:
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

            price_match = re.search(r"(\d[\d\s.,]*)", user_text)
            if not price_match:
                continue

            clean_price = re.sub(r"[^\d]", "", price_match.group(1))
            if not clean_price:
                continue

            original_text = reply_to.get("caption") or reply_to.get("text") or ""
            if not original_text:
                continue

            post_body = original_text.split("────────────")[0].strip()

            updated_post = re.sub(
                r"💰\s*Ціна:.*",
                f"💰 Ціна: {clean_price} грн",
                post_body,
            )
            if f"💰 Ціна: {clean_price} грн" not in updated_post:
                updated_post += f"\n\n💰 Ціна: {clean_price} грн"

            photos = reply_to.get("photo")
            if photos:
                best_photo_id = photos[-1]["file_id"]
                send_telegram_photo(
                    chat_id=chat_id,
                    photo_url_or_file_id=best_photo_id,
                    caption=updated_post,
                    reply_to_message_id=msg["message_id"],
                )
            else:
                send_telegram_text(
                    chat_id=chat_id,
                    text=updated_post,
                    reply_to_message_id=msg["message_id"],
                )

            processed_count += 1
            print(f"[INFO] Отправлен готовый пост с ценой {clean_price} грн!")

    except Exception as e:
        print(f"[WARN] Ошибка при обработке ответов Telegram: {e}")

    return processed_count


# ==============================================================================
# 3. ДЕТЕКТОР КРУПНЫХ РАСПРОДАЖ И МЕГА-СЕЙЛОВ (BLACK FRIDAY / CYBER MONDAY / CLEARANCE)
#    Сканирует 18 топовых американских сайтов-бестселлеров Украины на наличие
#    больших баннеров распродаж (>= 40-85% OFF), промокодов и дат проведения акции!
# ==============================================================================
MEGA_SALE_SITES = [
    ("Karl Lagerfeld Paris Official", "Karl Lagerfeld", "https://www.karllagerfeldparis.com/collections/clearance"),
    ("DKNY Official US", "DKNY", "https://www.dkny.com/collections/clearance"),
    ("Calvin Klein US Official", "Calvin Klein", "https://www.calvinklein.us/en/sale"),
    ("Tommy Hilfiger US Official", "Tommy Hilfiger", "https://usa.tommy.com/en/sale"),
    ("GUESS US Official", "Guess", "https://www.guess.com/us/en/sale/"),
    ("GUESS Factory Outlet US", "Guess Factory", "https://www.guessfactory.com/us/en/sale/"),
    ("Michael Kors US Official", "Michael Kors", "https://www.michaelkors.com/sale/view-all-sale/"),
    ("Coach Outlet US", "Coach", "https://www.coachoutlet.com/shop/deal-event"),
    ("Kate Spade Outlet US", "Kate Spade", "https://www.katespadeoutlet.com/shop/sale"),
    ("Diesel US Official", "Diesel", "https://shop.diesel.com/en/sale/"),
    ("Lacoste US Official", "Lacoste", "https://www.lacoste.com/us/lacoste/sale/"),
    ("Jomashop Sales & Events", "Jomashop", "https://www.jomashop.com/coupons-and-promocodes.html"),
    ("Nordstrom Rack Clearance", "Nordstrom Rack", "https://www.nordstromrack.com/clearance"),
    ("Joe's New Balance Outlet", "New Balance", "https://www.joesnewbalanceoutlet.com/"),
    ("U.S. Polo Assn. Official", "U.S. Polo Assn.", "https://uspoloassn.com/collections/clearance-all"),
    ("Champion US Official", "Champion", "https://www.champion.com/collections/clearance"),
    ("Juicy Couture Official", "Juicy Couture", "https://juicycouture.com/collections/sale"),
    ("Steve Madden US Official", "Steve Madden", "https://www.stevemadden.com/collections/womens-sale"),
    ("Nine West US Official", "Nine West", "https://ninewest.com/collections/sale"),
    ("Victoria's Secret US Sale", "Victoria's Secret", "https://www.victoriassecret.com/us/vs/sale"),
    ("Levi's US Official Sale", "Levi's", "https://www.levi.com/US/en_US/sale/c/levi_clothing_sale_us"),
    ("Puma US Official Sale", "Puma", "https://us.puma.com/us/en/sale/all-sale"),
    ("ShopSimon Designer Outlets", "ShopSimon", "https://shopsimon.com/collections/sale"),
]

DATE_EXTRACTION_REGEX = re.compile(
    r"("
    r"(?:valid\s+|offer\s+ends\s+|ends\s+|thru\s+|through\s+|until\s+|from\s+)?"
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|\d{1,2}/\d{1,2})"
    r"[\w\s,./\-–—]{1,35}"
    r")",
    re.IGNORECASE,
)

PROMO_BANNER_REGEX = re.compile(
    r"((?:black\s+friday|cyber\s+monday|cyber\s+week|holiday\s+sale|clearance|flash\s+sale|doorbuster|sitewide|extra\s+\d{2}%\s+off|up\s+to\s+\d{2}%\s+off)[^.\n<>]{0,120})",
    re.IGNORECASE,
)


def check_and_notify_mega_sales(state: dict) -> None:
    """
    Проверяет топ американских сайтов на запуск крупных сейлов (Black Friday, Cyber Week,
    Extra 40-75% Off, Sitewide Sale). Если находит новую крупную акцию — отправляет
    отдельное заметное сообщение 🚨🔥 МЕГА-СЕЙЛ со ссылкой и сроками действия!
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    seen_events = set(state.get("seen_sale_events", []))
    alerts_sent = 0

    for site_name, brand_name, sale_url in MEGA_SALE_SITES:
        if alerts_sent >= MAX_MEGA_SALE_ALERTS_PER_RUN:
            break
        try:
            resp = requests.get(sale_url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            # Собираем текст из шапки, промо-баров, заголовков и мета-описания
            promo_texts = []
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                promo_texts.append(meta_desc["content"])

            for tag in soup.select(
                "header, [class*='promo'], [class*='banner'], [class*='announcement'], "
                "[class*='ticker'], [class*='hero'], h1, h2"
            )[:25]:
                t = tag.get_text(" ", strip=True)
                if 10 <= len(t) <= 300:
                    promo_texts.append(t)

            full_promo_blob = " | ".join(promo_texts)
            if not full_promo_blob:
                continue

            # Ищем упоминание скидки от 40% до 90% или Black Friday / Cyber Monday / Clearance
            pct_matches = [int(p) for p in re.findall(r"(\d{2})\s*%\s*off", full_promo_blob, re.IGNORECASE)]
            max_pct = max(pct_matches) if pct_matches else 0
            has_big_event = bool(re.search(r"black\s+friday|cyber\s+monday|cyber\s+week|doorbuster|sitewide|extra\s+\d{2}%\s*off", full_promo_blob, re.IGNORECASE))

            if max_pct < 40 and not has_big_event:
                continue

            # Выделяем главный слоган акции
            banner_match = PROMO_BANNER_REGEX.search(full_promo_blob)
            headline = banner_match.group(1).strip(" |.,;-") if banner_match else f"Up to {max_pct}% OFF Sale"
            headline = re.sub(r"\s+", " ", headline)[:140]

            # Проверяем, не отправляли ли уже именно этот сейл
            event_id = make_deal_id(sale_url, f"{brand_name}|{max_pct}|{headline[:50].lower()}")
            if event_id in seen_events:
                continue

            # Ищем даты проведения акции (с какого по какое число актуально)
            date_matches = DATE_EXTRACTION_REGEX.findall(full_promo_blob)
            clean_dates = []
            for dm in date_matches:
                d_str = re.sub(r"\s+", " ", dm).strip(" |.,;-")
                if any(ch.isdigit() for ch in d_str) and len(d_str) >= 5:
                    clean_dates.append(d_str)

            dates_info = clean_dates[0] if clean_dates else "Актуально сейчас (лимитированный сейл / пока товары в наличии)"

            # Ищем промокод, если он указан на баннере (например: USE CODE: CYBER30)
            code_match = re.search(r"(?:code|промокод|use code)[:\s]+([A-Z0-9]{4,15})", full_promo_blob, re.IGNORECASE)
            promo_code_line = f"\n🎟 **Промокод на сайте:** `{code_match.group(1).upper()}`" if code_match else ""

            pct_badge = f"до -{max_pct}%" if max_pct > 0 else "Крупная распродажа"

            alert_message = (
                f"🚨🚨🚨 **МЕГА-СЕЙЛ НА САЙТЕ: {brand_name.upper()} ({pct_badge})** 🚨🚨🚨\n\n"
                f"🏬 **Магазин:** {site_name}\n"
                f"🔥 **Что за акция:** {headline}"
                f"{promo_code_line}\n"
                f"📅 **Сроки проведения:** {dates_info}\n\n"
                f"🔗 **Прямая ссылка на раздел распродажи:**\n{sale_url}"
            )

            if send_telegram_text(TELEGRAM_CHAT_ID, alert_message):
                state["seen_sale_events"].append(event_id)
                seen_events.add(event_id)
                alerts_sent += 1
                print(f"[INFO] Отправлен алерт о МЕГА-СЕЙЛЕ: {site_name} ({headline})")
                time.sleep(2)

        except Exception as e:
            print(f"[WARN] Ошибка проверки мега-сейла {site_name}: {e}")


# ==============================================================================
# 4. ПРЯМОЙ ПАРСИНГ ТОП-15+ ОФИЦИАЛЬНЫХ САЙТОВ И БУТИКОВ США (БЕСТСЕЛЛЕРЫ УКРАИНЫ)
# ==============================================================================
def fetch_top15_us_brand_sites() -> list[dict]:
    """
    Напрямую парсит официальные американские сайты брендов-бестселлеров Украины
    (Karl Lagerfeld Paris, DKNY, Champion, U.S. Polo Assn., Juicy Couture,
    Steve Madden, Nine West, Rebecca Minkoff, а также 24 брендовых бутика в ShopSimon).
    Берёт только товары В НАЛИЧИИ со скидкой >= 50% и прямыми фото!
    """
    deals = []

    # 1. Официальные американские монобрендовые сайты с открытым JSON-каталогом распродаж
    direct_brand_stores = [
        # Официальный сайт Karl Lagerfeld Paris (США)
        ("Karl Lagerfeld Paris Official (karllagerfeldparis.com)", "Karl Lagerfeld", "https://www.karllagerfeldparis.com/collections/clearance/products.json?limit=45"),
        ("Karl Lagerfeld Paris Bags Sale", "Karl Lagerfeld", "https://www.karllagerfeldparis.com/collections/sale-handbags/products.json?limit=45"),
        # Официальный сайт DKNY (США)
        ("DKNY Official US (dkny.com)", "DKNY", "https://www.dkny.com/collections/clearance/products.json?limit=45"),
        ("DKNY Official Bags Sale", "DKNY", "https://www.dkny.com/collections/sale/products.json?limit=45"),
        # Официальный сайт Champion (США)
        ("Champion Official US (champion.com)", "Champion", "https://www.champion.com/collections/clearance/products.json?limit=45"),
        # Официальный сайт U.S. Polo Assn. (США)
        ("U.S. Polo Assn. Official US (uspoloassn.com)", "U.S. Polo Assn", "https://uspoloassn.com/collections/clearance-all/products.json?limit=45"),
        ("U.S. Polo Assn. Under $30 Clearance", "U.S. Polo Assn", "https://uspoloassn.com/collections/clearance-30-under/products.json?limit=45"),
        # Официальный сайт Juicy Couture (США)
        ("Juicy Couture Official US (juicycouture.com)", "Juicy Couture", "https://juicycouture.com/collections/sale/products.json?limit=45"),
        ("Juicy Couture Handbags Sale", "Juicy Couture", "https://juicycouture.com/collections/sale-handbags/products.json?limit=45"),
        # Официальный сайт Steve Madden (США)
        ("Steve Madden Official US (stevemadden.com)", "Steve Madden", "https://www.stevemadden.com/collections/clearance/products.json?limit=45"),
        ("Steve Madden Women's Sale", "Steve Madden", "https://www.stevemadden.com/collections/womens-sale/products.json?limit=45"),
        # Официальный сайт Nine West (США)
        ("Nine West Official US (ninewest.com)", "Nine West", "https://ninewest.com/collections/sale/products.json?limit=45"),
        # Официальный сайт Rebecca Minkoff (США)
        ("Rebecca Minkoff Official US (rebeccaminkoff.com)", "Rebecca Minkoff", "https://www.rebeccaminkoff.com/collections/sale/products.json?limit=45"),
        # Официальные американские аутлет-витрины брендов-бестселлеров Украины на ShopSimon
        ("Calvin Klein US Outlet", "Calvin Klein", "https://shopsimon.com/collections/calvin-klein/products.json?limit=40"),
        ("Tommy Hilfiger US Outlet", "Tommy Hilfiger", "https://shopsimon.com/collections/tommy-hilfiger/products.json?limit=40"),
        ("Guess Official US Outlet", "Guess", "https://shopsimon.com/collections/guess/products.json?limit=40"),
        ("Karl Lagerfeld Outlet", "Karl Lagerfeld", "https://shopsimon.com/collections/karl-lagerfeld-paris/products.json?limit=40"),
        ("Michael Kors US Outlet", "Michael Kors", "https://shopsimon.com/collections/michael-kors/products.json?limit=40"),
        ("Adidas Official US Outlet", "Adidas", "https://shopsimon.com/collections/adidas/products.json?limit=40"),
        ("Diesel US Outlet", "Diesel", "https://shopsimon.com/collections/diesel/products.json?limit=40"),
        ("Lacoste US Outlet", "Lacoste", "https://shopsimon.com/collections/lacoste/products.json?limit=40"),
        ("Coach US Outlet", "Coach", "https://shopsimon.com/collections/coach/products.json?limit=40"),
        ("Polo Ralph Lauren Outlet", "Polo Ralph Lauren", "https://shopsimon.com/collections/polo-ralph-lauren/products.json?limit=40"),
        ("New Balance US Outlet", "New Balance", "https://shopsimon.com/collections/new-balance/products.json?limit=40"),
        ("Puma Official US Outlet", "Puma", "https://shopsimon.com/collections/puma/products.json?limit=40"),
        ("Timberland US Outlet", "Timberland", "https://shopsimon.com/collections/timberland/products.json?limit=40"),
        ("Levi's US Outlet", "Levi's", "https://shopsimon.com/collections/levis/products.json?limit=40"),
        ("Marc Jacobs US Outlet", "Marc Jacobs", "https://shopsimon.com/collections/marc-jacobs/products.json?limit=40"),
        ("Tory Burch US Outlet", "Tory Burch", "https://shopsimon.com/collections/tory-burch/products.json?limit=40"),
        ("Kate Spade New York Outlet", "Kate Spade", "https://shopsimon.com/collections/kate-spade-new-york/products.json?limit=40"),
        ("DKNY US Outlet", "DKNY", "https://shopsimon.com/collections/dkny/products.json?limit=40"),
        ("Hugo Boss US Outlet", "Hugo Boss", "https://shopsimon.com/collections/boss/products.json?limit=40"),
        ("Converse US Outlet", "Converse", "https://shopsimon.com/collections/converse/products.json?limit=40"),
        ("Under Armour US Outlet", "Under Armour", "https://shopsimon.com/collections/under-armour/products.json?limit=40"),
        ("Furla US Outlet", "Furla", "https://shopsimon.com/collections/furla/products.json?limit=40"),
    ]

    for source_name, brand, feed_url in direct_brand_stores:
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=12)
            if resp.status_code != 200 or "application/json" not in resp.headers.get("Content-Type", ""):
                continue
            products = resp.json().get("products", [])
            for prod in products:
                title = (prod.get("title") or "").strip()
                handle = (prod.get("handle") or "").strip()
                variants = prod.get("variants", [])
                if not title or not handle or not variants:
                    continue

                avail_variants = [v for v in variants if v.get("available", True)]
                if not avail_variants:
                    continue

                v = avail_variants[0]
                sale_price = float(v.get("price") or 0)
                orig_price = float(v.get("compare_at_price") or 0)
                if sale_price <= 0 or orig_price <= sale_price:
                    continue

                discount = round((1 - sale_price / orig_price) * 100)
                if discount < MIN_DISCOUNT_PERCENT:
                    continue

                images = prod.get("images", [])
                image_url = images[0].get("src", "") if images else ""
                if not image_url:
                    continue
                if image_url.startswith("//"):
                    image_url = "https:" + image_url

                body_html = prod.get("body_html") or ""
                clean_desc = BeautifulSoup(body_html, "html.parser").get_text(" ", strip=True)

                avail_options = [var.get("title", "") for var in avail_variants if var.get("title")]
                base_domain = "/".join(feed_url.split("/")[:3])
                product_url = f"{base_domain}/products/{handle}"

                if not is_valid_fashion_deal(title, brand, product_url, clean_desc):
                    continue

                deals.append({
                    "source": source_name,
                    "brand": brand,
                    "title": f"{brand} {title}" if brand.lower() not in title.lower() else title,
                    "sale_price": sale_price,
                    "original_price": orig_price,
                    "discount_pct": discount,
                    "url": product_url,
                    "image_url": image_url,
                    "details": f"{clean_desc[:500]}. In-stock variants: {', '.join(avail_options[:8])}",
                })
        except Exception as e:
            print(f"[WARN] Ошибка магазина {source_name}: {e}")

    # 2. Дополнительно парсим Joe's New Balance Outlet (официальный аутлет New Balance в США)
    joes_urls = [
        "https://www.joesnewbalanceoutlet.com/men/shoes/all-shoes/",
        "https://www.joesnewbalanceoutlet.com/women/shoes/all-shoes/",
        "https://www.joesnewbalanceoutlet.com/final-sale/",
    ]
    for j_url in joes_urls:
        try:
            resp = requests.get(j_url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for tile in soup.select("div.product-tile, div.product, div[data-pid]"):
                link_tag = tile.select_one("a.pname, a.tile-img-link, a[href*='/pd/']")
                if not link_tag:
                    continue
                href = link_tag.get("href", "")
                if href.startswith("/"):
                    href = f"https://www.joesnewbalanceoutlet.com{href}"
                title_text = link_tag.get_text(" ", strip=True) or tile.get_text(" ", strip=True)[:80]
                tile_text = tile.get_text(" ", strip=True)
                prices = [
                    float(p.replace(",", ""))
                    for p in re.findall(r"\$\s*(\d+(?:\.\d{2})?)", tile_text)
                ]
                if len(prices) < 2:
                    continue
                sale_p = min(prices)
                orig_p = max(prices)
                if sale_p <= 0 or orig_p <= sale_p:
                    continue
                disc = round((1 - sale_p / orig_p) * 100)
                if disc < MIN_DISCOUNT_PERCENT:
                    continue
                img_tag = tile.select_one("img")
                img_url = ""
                if img_tag:
                    img_url = img_tag.get("src") or img_tag.get("data-src") or ""
                if not img_url or not img_url.startswith("http"):
                    continue
                deals.append({
                    "source": "Joe's New Balance Outlet (US Official)",
                    "brand": "New Balance",
                    "title": f"New Balance {title_text}" if "new balance" not in title_text.lower() else title_text,
                    "sale_price": sale_p,
                    "original_price": orig_p,
                    "discount_pct": disc,
                    "url": href,
                    "image_url": img_url,
                    "details": f"Official Joe's New Balance Outlet USA. {tile_text[:250]}",
                })
        except Exception as e:
            print(f"[WARN] Joe's New Balance Outlet: {e}")

    print(f"[INFO] Найдено товаров на ТОП-15+ официальных сайтах и аутлетах США: {len(deals)}")
    return deals


# ==============================================================================
# 5. ПРЯМОЙ ПАРСИНГ JOMASHOP (ЧАСЫ, СУМКИ, ОЧКИ, ЕВРО/США ПАРФЮМЫ — БЕЗ АРАБСКИХ)
# ==============================================================================
def fetch_jomashop_deals() -> list[dict]:
    deals = []

    graphql_url = "https://www.jomashop.com/graphql"
    search_queries = [
        ("Diesel", "Diesel watch"),
        ("Calvin Klein", "Calvin Klein watch"),
        ("Calvin Klein", "Calvin Klein handbag"),
        ("Calvin Klein", "Calvin Klein perfume"),
        ("Tommy Hilfiger", "Tommy Hilfiger watch"),
        ("Guess", "Guess watch"),
        ("Guess", "Guess handbag"),
        ("Michael Kors", "Michael Kors watch"),
        ("Michael Kors", "Michael Kors handbag"),
        ("Karl Lagerfeld", "Karl Lagerfeld handbag"),
        ("Lacoste", "Lacoste watch"),
        ("Lacoste", "Lacoste fragrance"),
        ("Coach", "Coach handbag"),
        ("Coach", "Coach watch"),
        ("Marc Jacobs", "Marc Jacobs handbag"),
        ("Tory Burch", "Tory Burch handbag"),
        ("Furla", "Furla handbag"),
        ("Tissot", "Tissot watch"),
        ("Versace", "Versace watch"),
        ("Versace", "Versace fragrance"),
        ("Hugo Boss", "Hugo Boss watch"),
        ("Emporio Armani", "Emporio Armani watch"),
        ("Burberry", "Burberry handbag"),
    ]

    gql_query = """
    query ProductSearch($search: String!) {
      products(search: $search, pageSize: 18) {
        items {
          name
          sku
          url_key
          stock_status
          small_image {
            url
          }
          price_range {
            minimum_price {
              regular_price {
                value
              }
              final_price {
                value
              }
              discount {
                percent_off
              }
            }
          }
        }
      }
    }
    """

    for brand, q_text in search_queries:
        try:
            gql_headers = {
                **HEADERS,
                "Content-Type": "application/json",
                "Origin": "https://www.jomashop.com",
                "Referer": "https://www.jomashop.com/",
            }
            resp = requests.post(
                graphql_url,
                json={"query": gql_query, "variables": {"search": q_text}},
                headers=gql_headers,
                timeout=15,
            )
            if resp.status_code == 200 and "application/json" in resp.headers.get("Content-Type", ""):
                items = (
                    resp.json()
                    .get("data", {})
                    .get("products", {})
                    .get("items", [])
                ) or []
                for item in items:
                    stock_status = (item.get("stock_status") or "IN_STOCK").upper()
                    if "OUT_OF_STOCK" in stock_status:
                        continue

                    name = (item.get("name") or "").strip()
                    url_key = (item.get("url_key") or "").strip()
                    if not name or not url_key:
                        continue

                    min_price = (
                        item.get("price_range", {})
                        .get("minimum_price", {})
                    ) or {}
                    reg_val = float(min_price.get("regular_price", {}).get("value") or 0)
                    fin_val = float(min_price.get("final_price", {}).get("value") or 0)
                    pct_off = float(min_price.get("discount", {}).get("percent_off") or 0)

                    if fin_val <= 0:
                        continue
                    if pct_off == 0 and reg_val > fin_val:
                        pct_off = (1 - fin_val / reg_val) * 100

                    discount = round(pct_off)
                    if discount < MIN_DISCOUNT_PERCENT:
                        continue

                    img_url = (item.get("small_image") or {}).get("url") or ""
                    if not img_url:
                        continue

                    prod_url = f"https://www.jomashop.com/{url_key}.html"
                    if not is_valid_fashion_deal(name, brand, prod_url):
                        continue

                    deals.append({
                        "source": "Jomashop.com",
                        "brand": brand,
                        "title": f"{brand} {name}" if brand.lower() not in name.lower() else name,
                        "sale_price": fin_val,
                        "original_price": reg_val if reg_val > fin_val else round(fin_val / (1 - discount / 100.0), 2),
                        "discount_pct": discount,
                        "url": prod_url,
                        "image_url": img_url,
                        "details": f"Authentic {brand} from Jomashop US. SKU: {item.get('sku', '')}. {name}",
                    })
        except Exception as e:
            print(f"[WARN] Jomashop GraphQL ({q_text}): {e}")

    brand_pages = [
        ("Calvin Klein", "https://www.jomashop.com/calvin-klein-watches.html"),
        ("Diesel", "https://www.jomashop.com/diesel-watches.html"),
        ("Tommy Hilfiger", "https://www.jomashop.com/tommy-hilfiger-watches.html"),
        ("Guess", "https://www.jomashop.com/guess-watches.html"),
        ("Michael Kors", "https://www.jomashop.com/michael-kors-watches.html"),
        ("Lacoste", "https://www.jomashop.com/lacoste-watches.html"),
        ("Coach", "https://www.jomashop.com/coach-watches.html"),
        ("Tissot", "https://www.jomashop.com/tissot-watches.html"),
        ("Hugo Boss", "https://www.jomashop.com/hugo-boss-watches.html"),
        ("Emporio Armani", "https://www.jomashop.com/emporio-armani-watches.html"),
    ]

    for brand, page_url in brand_pages:
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            for card in soup.select("li.productItem, div.productItemBlock, div.product-item-info"):
                link_tag = card.select_one("a.productName-link, a.productImg-link, a[href*='.html']")
                if not link_tag:
                    continue
                href = link_tag.get("href", "")
                if href.startswith("/"):
                    href = f"https://www.jomashop.com{href}"
                if "jomashop.com" not in href:
                    continue

                title_text = link_tag.get("title") or link_tag.get_text(" ", strip=True)
                card_text = card.get_text(" ", strip=True)

                now_match = re.search(r"Now:\s*\$\s*([\d,]+(?:\.\d{1,2})?)", card_text)
                reg_match = re.search(r"Reg\.\s*\$\s*([\d,]+(?:\.\d{1,2})?)", card_text)
                pct_match = re.search(r"(\d{2})\s*%\s*Off", card_text, re.IGNORECASE)

                if not now_match:
                    continue

                sale_p = float(now_match.group(1).replace(",", ""))
                orig_p = float(reg_match.group(1).replace(",", "")) if reg_match else 0.0
                disc = int(pct_match.group(1)) if pct_match else 0

                if disc == 0 and orig_p > sale_p > 0:
                    disc = round((1 - sale_p / orig_p) * 100)
                elif orig_p == 0 and disc > 0 and sale_p > 0:
                    orig_p = round(sale_p / (1 - disc / 100.0), 2)

                if disc < MIN_DISCOUNT_PERCENT:
                    continue

                img_tag = card.select_one("img")
                img_url = ""
                if img_tag:
                    img_url = (
                        img_tag.get("src")
                        or img_tag.get("data-src")
                        or img_tag.get("data-original")
                        or ""
                    )
                    if img_url.startswith("//"):
                        img_url = "https:" + img_url

                if not img_url or not title_text or not is_valid_fashion_deal(title_text, brand, href):
                    continue

                deals.append({
                    "source": "Jomashop.com",
                    "brand": brand,
                    "title": f"{brand} {title_text}" if brand.lower() not in title_text.lower() else title_text,
                    "sale_price": sale_p,
                    "original_price": orig_p,
                    "discount_pct": disc,
                    "url": href,
                    "image_url": img_url,
                    "details": f"Authentic {brand} item on Jomashop. {title_text}",
                })
        except Exception as e:
            print(f"[WARN] Jomashop HTML ({brand}): {e}")

    print(f"[INFO] Найдено товаров на Jomashop: {len(deals)}")
    return deals


# ==============================================================================
# 6. ОФИЦИАЛЬНЫЙ КАТАЛОГ NIKE US SALE
# ==============================================================================
def fetch_nike_us_clearance() -> list[dict]:
    deals = []
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
        "%26count%3D45"
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
        ) or []
        for item in products:
            if item.get("inStock") is False:
                continue

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

            image_url = (
                item.get("images", {}).get("squarishURL")
                or item.get("images", {}).get("portraitURL")
                or ""
            )
            if not image_url:
                continue

            colors_count = len(item.get("colorways", []) or [])
            color_desc = item.get("colorDescription", "")
            details_str = f"Color: {color_desc}. Total available colorways: {colors_count}. Category: {subtitle}"

            if not is_valid_fashion_deal(full_title, "Nike", raw_url, details_str):
                continue

            deals.append({
                "source": "Nike.com (US Official)",
                "brand": "Nike",
                "title": full_title,
                "sale_price": current_price,
                "original_price": full_price,
                "discount_pct": discount,
                "url": raw_url,
                "image_url": image_url,
                "details": details_str,
            })
    except Exception as e:
        print(f"[WARN] Nike US API: {e}")

    print(f"[INFO] Найдено товаров на Nike.com: {len(deals)}")
    return deals


# ==============================================================================
# 7. ГЕНЕРАЦИЯ УКРАИНСКОГО ПОСТА ПО ТВОЕМУ ШАБЛОНУ ЧЕРЕЗ GEMINI API
# ==============================================================================
def generate_ukrainian_post(deal: dict) -> str:
    prompt = f"""Ти — досвідчений фешн-копірайтер для українського Telegram/Instagram-каналу байєра брендових речей зі США.
Створи готовий пост українською мовою СТРОГО за наведеним нижче шаблоном і структурою.

ВХІДНІ ДАНІ ПРО ТОВАР:
- Бренд: {deal['brand']}
- Назва: {deal['title']}
- Деталі та характеристики (англ.): {deal['details']}

ПРАВИЛА ОФОРМЛЕННЯ:
1. Перший рядок: 🔥 [Оригінальна англійська назва бренду та моделі без зайвого сміття]
2. Другий абзац: Живий, привабливий опис моделі українською мовою (2-3 речення: силует, фактура, деталі, з чим носити або чому це крута пропозиція).
3. Абзац про колір: 🎨 Опиши колір на фото та інші доступні кольори/варіанти під викуп.
4. Блок "Характеристики:":
   - Матеріали / Склад (або Механізм/Скло/Корпус для годинників, Ноти/Об'єм для парфумів)
   - Габарити / Розміри (ВАЖЛИВО: якщо в англійському описі є дюйми (inches / "), ОБОВ'ЯЗКОВО переведи їх у сантиметри за формулою 1 inch = 2.54 см, формат: 28,5 × 9,7 × 10 см. Якщо габаритів немає — вкажи розмір корпусу годинника в мм або доступну розмірну сітку).
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
            print(f"[WARN] Ошибка Gemini API: {e}")

    return (
        f"🔥 {deal['title']}\n\n"
        f"Оригінальна брендова позиція від {deal['brand']} напряму зі США за акційною ціною.\n\n"
        f"🎨 Актуальне виконання на фото, деталі щодо інших кольорів та розмірів уточнюйте в особистих.\n\n"
        f"Характеристики:\n"
        f"Бренд: {deal['brand']}\n"
        f"Особливості: {deal['details'][:220]}\n\n"
        f"💎 Тільки 100% оригінал.\n\n"
        f"💰 Ціна: [Вкажи ціну] грн\n\n"
        f"📩 З усіх питань, за фото інших кольорів та для швидкого оформлення замовлення - {CONTACT_HANDLE}"
    )


def format_buyer_card(post_text: str, deal: dict) -> str:
    sale_str = f"${deal['sale_price']:.2f}" if deal["sale_price"] > 0 else "см. на сайте"
    orig_str = f"${deal['original_price']:.2f}" if deal["original_price"] > 0 else "—"
    buyer_info = (
        f"\n\n────────────────────\n"
        f"🛒 Магазин: {deal['source']}\n"
        f"💵 Цена в США: {sale_str} (была {orig_str} | -{deal['discount_pct']}%)\n"
        f"🔗 Ссылка: {deal['url']}\n"
        f"💡 Сделай Reply (Ответить) на это сообщение и напиши цену (например: 6000)"
    )
    return post_text + buyer_info


# ==============================================================================
# ГЛАВНЫЙ ЦИКЛ
# ==============================================================================
def main() -> None:
    state = load_state()

    # Шаг 1: Проверяем и обрабатываем твои ответы (Reply) с ценой в гривнах
    process_telegram_price_replies(state)

    # Шаг 2: Проверяем запуск крупных МЕГА-СЕЙЛОВ (Black Friday, Cyber Week, Clearance)
    # на 20+ топовых сайтах США и шлём заметный алерт со ссылкой и датами акции
    check_and_notify_mega_sales(state)

    # Шаг 3: Собираем отдельные товары со скидкой >= 50% по всем ТОП-15+ сайтам США
    all_deals = []
    all_deals.extend(fetch_top15_us_brand_sites())
    all_deals.extend(fetch_jomashop_deals())
    all_deals.extend(fetch_nike_us_clearance())

    print(f"[INFO] Всего найдено релевантных товаров со скидкой >= {MIN_DISCOUNT_PERCENT}%: {len(all_deals)}")

    seen_set = set(state.get("seen_ids", []))
    new_deals = []

    for d in all_deals:
        if not d.get("image_url"):
            continue
        deal_id = make_deal_id(d["url"], d["title"])
        if deal_id not in seen_set:
            d["id"] = deal_id
            new_deals.append(d)

    # Чередуем бренды и магазины, чтобы в каждом запуске приходили разные бренды
    new_deals.sort(key=lambda x: x.get("discount_pct", 0), reverse=True)
    diversified_batch = []
    brand_counts = {}
    for d in new_deals:
        b = d["brand"]
        if brand_counts.get(b, 0) < 2:
            diversified_batch.append(d)
            brand_counts[b] = brand_counts.get(b, 0) + 1
        if len(diversified_batch) >= MAX_NEW_DEALS_PER_RUN:
            break

    if len(diversified_batch) < MAX_NEW_DEALS_PER_RUN:
        used_ids = {x["id"] for x in diversified_batch}
        for d in new_deals:
            if d["id"] not in used_ids:
                diversified_batch.append(d)
            if len(diversified_batch) >= MAX_NEW_DEALS_PER_RUN:
                break

    print(f"[INFO] Новых уникальных товаров с фото для отправки: {len(diversified_batch)}")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        save_state(state)
        return

    for deal in diversified_batch:
        post_text = generate_ukrainian_post(deal)
        full_caption = format_buyer_card(post_text, deal)

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
