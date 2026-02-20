"""
FunPay Analytics Parser
Парсит категории, продавцов, цены и отзывы с funpay.com
"""
import requests
from bs4 import BeautifulSoup
import time
import random
import logging
import datetime
from typing import Optional
import re
from collections import Counter

logger = logging.getLogger("FunPayAnalyst")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
BASE_URL = "https://funpay.com"
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Словари для нормализации дат
_MONTHS_RU = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4,
    "май": 5, "мая": 5, "июн": 6, "июл": 7, "август": 8,
    "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}
_MONTHS_SHORT = {
    1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр", 5: "Май", 6: "Июн",
    7: "Июл", 8: "Авг", 9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек",
}


def _get(url: str, retries: int = 3, currency: str = "RUB") -> Optional[BeautifulSoup]:
    for attempt in range(retries):
        try:
            time.sleep(random.uniform(0.8, 2.0))  # вежливая задержка
            # Явно выставляем куку валюты в сессии — перебивает любые Set-Cookie от сервера
            SESSION.cookies.set("cy", currency, domain="funpay.com")
            r = SESSION.get(url, timeout=15)
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            logger.warning(f"[Parser] Попытка {attempt+1}/{retries} для {url}: {e}")
            time.sleep(3)
    return None


def _parse_funpay_date_to_month(date_str: str) -> str:
    """Нормализует строку даты FunPay в формат 'Янв 2025'."""
    now = datetime.datetime.now()
    s = date_str.strip().lower()

    if "этом месяце" in s or "этот месяц" in s:
        return f"{_MONTHS_SHORT[now.month]} {now.year}"
    if "прошлом месяце" in s or "прошлый месяц" in s:
        prev = (now.replace(day=1) - datetime.timedelta(days=1))
        return f"{_MONTHS_SHORT[prev.month]} {prev.year}"
    if "сегодня" in s:
        return f"{_MONTHS_SHORT[now.month]} {now.year}"
    if "вчера" in s:
        yesterday = now - datetime.timedelta(days=1)
        return f"{_MONTHS_SHORT[yesterday.month]} {yesterday.year}"

    # Ищем год явно
    year_match = re.search(r"\b(20\d{2})\b", s)
    year = int(year_match.group(1)) if year_match else now.year

    # Ищем месяц по ключевым частям русских названий
    for prefix, month_num in _MONTHS_RU.items():
        if prefix in s:
            return f"{_MONTHS_SHORT[month_num]} {year}"

    return date_str  # fallback — возвращаем как есть


def _parse_review_stars(rev_el) -> int:
    """Извлекает количество звёзд из элемента отзыва (класс ratingN)."""
    rating_container = rev_el.select_one(".review-item-rating, .review-item-user .rating")
    if not rating_container:
        return 0
    for tag in rating_container.find_all(True):
        for cls in tag.get("class", []):
            m = re.match(r"rating(\d)$", cls)
            if m:
                return int(m.group(1))
    return 0


def get_categories() -> list[dict]:
    """Получает список всех игровых категорий с главной страницы."""
    soup = _get(f"{BASE_URL}/")
    if not soup:
        return []
    categories = []
    for item in soup.select("div.promo-game-item"):
        link = item.select_one("a")
        name = item.select_one(".game-title")
        if link and name:
            href = link.get("href", "")
            cat_id_match = re.search(r"/(\d+)/", href)
            categories.append({
                "id": cat_id_match.group(1) if cat_id_match else None,
                "name": name.get_text(strip=True),
                "url": href if href.startswith("http") else BASE_URL + href,
            })
    return categories


def get_lots_in_category(category_url: str, max_pages: int = 2, currency: str = "RUB") -> list[dict]:
    """
    Парсит лоты в категории с пагинацией.
    Возвращает список лотов с ценами, продавцами и кол-вом отзывов.
    """
    lots = []
    base_url = category_url.rstrip("/").split("?")[0]

    for page in range(1, max_pages + 1):
        page_url = base_url + "/" if page == 1 else f"{base_url}/?page={page}"
        soup = _get(page_url, currency=currency)
        if not soup:
            break

        page_lots = []
        for offer in soup.select("a.tc-item"):
            try:
                seller_el  = offer.select_one(".media-user-name")
                price_el   = offer.select_one(".tc-price")
                reviews_el = offer.select_one(
                    ".media-user-reviews, .media-user-reviews-count, "
                    ".tc-reviews, .rating-mini-count, span[class*='review']"
                )
                title_el   = offer.select_one(".tc-desc-text, .tc-title")
                online_el  = offer.select_one(".media-user-status.online, .online")

                seller_raw = seller_el.get_text(separator=" ", strip=True) if seller_el else "Неизвестно"
                seller = seller_raw.replace("Онлайн", "").replace("онлайн", "").strip()

                price_raw = price_el.get_text(strip=True) if price_el else "0"
                price_num = re.sub(r"[^\d.,]", "", price_raw).replace(",", ".")
                try:
                    price = float(price_num) if price_num else 0.0
                except ValueError:
                    price = 0.0

                rev_raw = reviews_el.get_text(strip=True) if reviews_el else "0"
                rev_num = re.sub(r"[^\d]", "", rev_raw)
                reviews = int(rev_num) if rev_num else 0

                title = title_el.get_text(strip=True) if title_el else ""
                href = offer.get("href", "")
                lot_url = href if href.startswith("http") else BASE_URL + href

                page_lots.append({
                    "seller":  seller,
                    "title":   title,
                    "price":   price,
                    "reviews": reviews,
                    "online":  bool(online_el),
                    "url":     lot_url,
                })
            except Exception as e:
                logger.debug(f"Ошибка парсинга лота: {e}")
                continue

        if not page_lots:
            break  # нет лотов — дальше не идём
        lots.extend(page_lots)

        # Проверяем наличие следующей страницы
        next_btn = soup.select_one("a.pagination-next, a[rel='next'], li.next a")
        if not next_btn and page > 1:
            break

    return lots


def get_seller_profile(user_id: int, currency: str = "RUB") -> dict:
    """Парсит профиль продавца."""
    SESSION.cookies.set("cy", currency, domain="funpay.com")
    soup = _get(f"{BASE_URL}/users/{user_id}/", currency=currency)
    if not soup:
        return {}

    result = {"user_id": user_id, "lots": [], "reviews_sample": []}

    # Имя продавца
    name_el = soup.select_one(
        ".profile-header .media-user-name, .profile-header h1, "
        "h1.profile-name, .username, .mr4"
    )
    if name_el:
        name = name_el.get_text(separator=" ", strip=True)
        name = name.replace("Онлайн", "").replace("онлайн", "").strip()
        result["name"] = name
    else:
        result["name"] = str(user_id)

    # Статус онлайн — реальный HTML: <h1 class="mb40 online">
    online_el = soup.select_one(
        "h1.online, .profile-header .online, "
        ".media-user-status.online, .profile-header .media-user-status.online"
    )
    result["online"] = bool(online_el)

    # Общее кол-во отзывов — реальный HTML: <div class="rating-full-count"><a>Всего 175 056<br>отзывов</a>
    rev_el = soup.select_one(
        ".rating-full-count a, a[href*='#reviews'], "
        ".rating-full + span, .reviews-count, span[class*='review-count']"
    )
    if rev_el:
        rev_num = re.sub(r"[^\d]", "", rev_el.get_text())
        result["total_reviews"] = int(rev_num) if rev_num else 0
    else:
        result["total_reviews"] = 0

    # Рейтинг — реальный HTML: <div class="rating-value"><span class="big">4.8</span>...
    rating_el = soup.select_one(
        ".rating-value .big, .rating-value span.big, "
        ".rating-mini-value .big, .rating-full span.big"
    )
    if rating_el:
        try:
            result["rating"] = float(rating_el.get_text(strip=True).replace(",", "."))
        except ValueError:
            result["rating"] = 0.0
    else:
        result["rating"] = 0.0

    # Активные лоты
    for offer in soup.select("a.tc-item"):
        price_el = offer.select_one(".tc-price")
        title_el = offer.select_one(".tc-desc-text, .tc-title")
        if price_el and title_el:
            raw_text = price_el.get_text(strip=True)
            price_raw = re.sub(r"[^\d.,]", "", raw_text).replace(",", ".")
            try:
                price = float(price_raw) if price_raw else 0.0
            except ValueError:
                price = 0.0

            href = offer.get("href", "")
            lot_url = href if href.startswith("http") else BASE_URL + href

            result["lots"].append({
                "title":      title_el.get_text(strip=True),
                "price":      price,
                "price_text": raw_text,
                "url":        lot_url,
            })

    return result


def get_seller_reviews_paginated(user_id: int, currency: str = "RUB", max_reviews: int = 500) -> list:
    """
    Загружает отзывы продавца через skip-пагинацию (?skip=0, ?skip=25, ...).
    Возвращает список сырых элементов BeautifulSoup (дедуплицированных).
    """
    SESSION.cookies.set("cy", currency, domain="funpay.com")
    all_reviews = []
    seen_keys = set()
    base = f"{BASE_URL}/users/{user_id}/"
    skip = 0
    page = 0

    while len(all_reviews) < max_reviews:
        page += 1
        url = base if skip == 0 else f"{base}?skip={skip}"
        soup = _get(url, currency=currency)
        if not soup:
            break

        reviews = soup.select(".review-item")
        if not reviews:
            break

        new_count = 0
        all_dupe = True
        for rev in reviews:
            date_el = rev.select_one(".review-item-date")
            text_el = rev.select_one(".review-item-text")
            key = (
                date_el.get_text(strip=True) if date_el else "",
                (text_el.get_text(strip=True)[:50] if text_el else ""),
            )
            if key not in seen_keys:
                seen_keys.add(key)
                all_reviews.append(rev)
                new_count += 1
                all_dupe = False

        logger.info(f"Страница {page} (skip={skip}): +{new_count} отзывов, всего {len(all_reviews)}")

        if len(reviews) < 25 or all_dupe:
            break

        skip += 25

    return all_reviews


def analyze_category(category_url: str, currency: str = "RUB") -> dict:
    """
    Полный анализ категории:
    - топ продавцов по кол-ву отзывов
    - распределение цен
    - онлайн-активность
    - рыночные возможности (ценовые ниши)
    """
    lots = get_lots_in_category(category_url, currency=currency)
    if not lots:
        return {"error": "Не удалось получить данные", "lots": []}

    # Агрегация по продавцам
    sellers: dict[str, dict] = {}
    for lot in lots:
        s = lot["seller"]
        if s not in sellers:
            sellers[s] = {
                "name":          s,
                "lots_count":    0,
                "first_lot_url": lot["url"],
                "reviews":       lot["reviews"],
                "min_price":     lot["price"],
                "max_price":     lot["price"],
                "prices":        [],
                "online":        lot["online"],
            }
        sellers[s]["lots_count"] += 1
        sellers[s]["prices"].append(lot["price"])
        if lot["price"] > 0:
            sellers[s]["min_price"] = min(sellers[s]["min_price"], lot["price"])
            sellers[s]["max_price"] = max(sellers[s]["max_price"], lot["price"])

    for s in sellers.values():
        valid = [p for p in s["prices"] if p > 0]
        s["avg_price"] = round(sum(valid) / len(valid), 2) if valid else 0
        del s["prices"]

    sellers_list = sorted(sellers.values(), key=lambda x: x["reviews"], reverse=True)
    prices = [l["price"] for l in lots if l["price"] > 0]

    # Рыночные ниши: ценовые диапазоны с наименьшей конкуренцией
    buckets = _price_buckets(prices)
    opportunity = _find_market_opportunities(buckets, prices)

    return {
        "total_lots":     len(lots),
        "total_sellers":  len(sellers),
        "online_sellers": sum(1 for s in sellers.values() if s["online"]),
        "price_min":      round(min(prices), 2) if prices else 0,
        "price_max":      round(max(prices), 2) if prices else 0,
        "price_avg":      round(sum(prices) / len(prices), 2) if prices else 0,
        "price_median":   round(sorted(prices)[len(prices) // 2], 2) if prices else 0,
        "top_sellers":    sellers_list[:20],
        "all_lots":       lots,
        "price_buckets":  buckets,
        "market_opportunities": opportunity,
    }


def _price_buckets(prices: list[float], buckets: int = 8) -> list[dict]:
    """Распределение цен по диапазонам для гистограммы."""
    if not prices:
        return []
    mn, mx = min(prices), max(prices)
    if mn == mx:
        return [{"range": f"{mn:.0f}", "count": len(prices)}]
    step = (mx - mn) / buckets
    result = []
    for i in range(buckets):
        lo = mn + i * step
        hi = mn + (i + 1) * step
        count = sum(1 for p in prices if lo <= p < hi)
        if i == buckets - 1:
            count = sum(1 for p in prices if lo <= p <= hi)
        result.append({"range": f"{lo:.0f}–{hi:.0f}", "count": count, "lo": round(lo, 2), "hi": round(hi, 2)})
    return result


def _find_market_opportunities(buckets: list[dict], prices: list[float]) -> list[dict]:
    """
    Находит ценовые ниши с наименьшей конкуренцией.
    Возвращает топ-3 диапазона, где мало лотов (низкая конкуренция).
    """
    if not buckets:
        return []
    max_count = max(b["count"] for b in buckets) or 1
    # Ниши: непустые диапазоны с низкой конкуренцией
    niches = [
        {
            "range":           b["range"],
            "count":           b["count"],
            "competition_pct": round(b["count"] / max_count * 100),
            "recommended_price": round((b.get("lo", 0) + b.get("hi", 0)) / 2, 2),
        }
        for b in buckets
        if b["count"] > 0
    ]
    # Сортируем по наименьшей конкуренции
    niches.sort(key=lambda x: x["count"])
    return niches[:3]


def analyze_seller(target: str, currency: str = "RUB", deep: bool = True, max_reviews: int = 500) -> dict:
    """
    Полный анализ продавца:
    - Базовый профиль (имя, рейтинг, кол-во отзывов)
    - Хронология отзывов по месяцам
    - Топ продаваемых товаров
    - Распределение звёзд в отзывах
    - Последние отзывы покупателей
    """
    if target.isdigit():
        user_id = int(target)
    else:
        match = re.search(r"users/(\d+)/", target)
        if match:
            user_id = int(match.group(1))
        else:
            return {"error": "Неверная ссылка на продавца", "type": "seller"}

    profile = get_seller_profile(user_id, currency=currency)
    if not profile:
        return {"error": "Не удалось получить данные продавца", "type": "seller"}

    # Загружаем отзывы с пагинацией
    raw_reviews = get_seller_reviews_paginated(user_id, currency=currency, max_reviews=max_reviews)

    items_sold = []
    dates_sold = []          # список строк "Мес ГГГГ"
    star_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    review_texts = []        # последние отзывы с текстом

    for rev in raw_reviews:
        # Описание лота из отзыва
        desc = rev.select_one(".review-item-detail, .review-item-desc, .review-item-title")
        if desc:
            items_sold.append(desc.get_text(strip=True))

        # Дата → нормализуем в месяц
        date_el = rev.select_one(".review-item-date")
        if date_el:
            month_str = _parse_funpay_date_to_month(date_el.get_text(strip=True))
            dates_sold.append(month_str)

        # Звёзды
        stars = _parse_review_stars(rev)
        if stars in star_counts:
            star_counts[stars] += 1

        # Текст отзыва покупателя
        text_el = rev.select_one(".review-item-text")
        if text_el and len(review_texts) < 20:
            text = text_el.get_text(strip=True)
            if text:
                review_texts.append({
                    "text":  text,
                    "stars": stars,
                    "date":  date_el.get_text(strip=True) if date_el else "",
                    "item":  desc.get_text(strip=True) if desc else "",
                })

    # Топ продаваемых товаров
    top_items = []
    if items_sold:
        counter = Counter(items_sold)
        top_items = [{"title": k, "count": v} for k, v in counter.most_common(10)]

    # Хронология по месяцам (от старых к новым)
    sales_by_month = []
    if dates_sold:
        month_counter = Counter(dates_sold)
        # Сохраняем порядок появления (от новых к старым), потом переворачиваем
        unique_months = list(dict.fromkeys(dates_sold))
        unique_months.reverse()
        sales_by_month = [{"month": m, "count": month_counter[m]} for m in unique_months]

    # Убираем нулевые звёзды из статистики (неопределённые)
    rating_dist = [{"stars": k, "count": v} for k, v in star_counts.items() if k > 0]

    return {
        "type":           "seller",
        "name":           profile.get("name", str(user_id)),
        "user_id":        profile.get("user_id"),
        "total_reviews":  profile.get("total_reviews", 0),
        "rating":         profile.get("rating", 0.0),
        "lots_count":     len(profile.get("lots", [])),
        "online":         profile.get("online", False),
        "lots":           profile.get("lots", []),
        "top_sold_items": top_items,
        "sales_by_month": sales_by_month,
        "rating_dist":    rating_dist,
        "review_texts":   review_texts,
        "reviews_parsed": len(raw_reviews),
    }
