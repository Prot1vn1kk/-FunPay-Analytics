"""
FunPay Analytics — Flask сервер
Запуск: python app.py
Открыть: http://localhost:5000
"""
from flask import Flask, jsonify, render_template_string, request
import threading
import time
import logging
from parser import analyze_category, get_categories, analyze_seller

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("FunPayAnalyst")

app = Flask(__name__)

# Кэш результатов (ключ = url_currency)
_cache: dict = {}
_cache_lock = threading.Lock()

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FunPay Analytics</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {
    --bg:       #1e1e2e;
    --surface:  #313244;
    --border:   #45475a;
    --accent:   #89b4fa;
    --accent-hover: #b4befe;
    --accent2:  #cba6f7;
    --accent3:  #a6e3a1;
    --red:      #f38ba8;
    --yellow:   #f9e2af;
    --text:     #cdd6f4;
    --muted:    #a6adc8;
    --card-bg:  #181825;
    --row-hover: #313244;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    min-height: 100vh;
    overflow-x: hidden;
  }

  /* ── Хэдер ── */
  header {
    position: relative; z-index: 10;
    display: flex; align-items: center; justify-content: space-between;
    padding: 20px 40px;
    border-bottom: 1px solid var(--border);
    backdrop-filter: blur(10px);
    background: rgba(10,12,16,0.85);
  }
  .logo { display: flex; align-items: center; gap: 12px; }
  .logo-icon {
    width: 36px; height: 36px;
    background: var(--accent);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
  }
  .logo-text { font-size: 18px; font-weight: 700; letter-spacing: -0.3px; }
  .logo-text span { color: var(--accent); }
  .header-meta { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--muted); }
  .status-dot {
    display: inline-block; width: 6px; height: 6px;
    border-radius: 50%; background: var(--accent3);
    margin-right: 6px; animation: pulse 2s infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

  /* ── Лэйаут ── */
  .container { max-width: 1400px; margin: 0 auto; padding: 32px 40px; }

  /* ── Поиск ── */
  .search-section { margin-bottom: 36px; }
  .search-label { font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; margin-bottom: 10px; }
  .search-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .search-input {
    background: var(--card-bg); border: 1px solid var(--border);
    color: var(--text); border-radius: 8px; padding: 11px 16px;
    font-size: 14px; font-family: inherit; outline: none; flex: 1; min-width: 200px;
    transition: border-color .2s;
  }
  .search-input:focus { border-color: var(--accent); }

  /* ── Кнопки ── */
  .btn {
    padding: 10px 22px; border-radius: 8px; border: none; cursor: pointer;
    font-size: 13px; font-weight: 600; font-family: inherit;
    transition: background .2s, opacity .2s; white-space: nowrap;
  }
  .btn-primary { background: var(--accent); color: #1e1e2e; }
  .btn-primary:hover { background: var(--accent-hover); }
  .btn-primary:disabled { opacity: .5; cursor: not-allowed; }
  .btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text); }
  .btn-ghost:hover { border-color: var(--accent); color: var(--accent); }
  .btn-green { background: var(--accent3); color: #1e1e2e; }
  .btn-green:hover { opacity: .85; }

  /* ── Быстрые категории ── */
  .quick-cats { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .cat-chip {
    padding: 6px 14px; border-radius: 20px;
    border: 1px solid var(--border); background: var(--card-bg);
    font-size: 12px; cursor: pointer; color: var(--muted); transition: all .2s;
  }
  .cat-chip:hover { border-color: var(--accent); color: var(--accent); }
  .cat-chip.active { opacity: .7; }

  /* ── Цвета групп ── */
  :root {
    --cat-mobile:  #34d399;
    --cat-pc:      #60a5fa;
    --cat-console: #fbbf24;
    --cat-social:  #a78bfa;
    --cat-store:   #fb923c;
    --cat-other:   #94a3b8;
  }
  .cat-groups-wrapper { margin-top: 14px; }
  .cat-group { margin-bottom: 10px; }
  .cat-group-label {
    font-size: 11px; font-weight: 600; letter-spacing: .5px;
    text-transform: uppercase; display: block; margin-bottom: 6px;
  }
  .cat-row {
    display: flex; gap: 7px; overflow-x: auto; padding-bottom: 4px;
    scrollbar-width: none; -ms-overflow-style: none; flex-wrap: nowrap;
  }
  .cat-row::-webkit-scrollbar { display: none; }
  .cat-chip--mobile  { border-color: var(--cat-mobile);  color: var(--cat-mobile);  background: transparent; }
  .cat-chip--pc      { border-color: var(--cat-pc);      color: var(--cat-pc);      background: transparent; }
  .cat-chip--console { border-color: var(--cat-console); color: var(--cat-console); background: transparent; }
  .cat-chip--social  { border-color: var(--cat-social);  color: var(--cat-social);  background: transparent; }
  .cat-chip--store   { border-color: var(--cat-store);   color: var(--cat-store);   background: transparent; }
  .cat-chip--other   { border-color: var(--cat-other);   color: var(--cat-other);   background: transparent; }
  .cat-chip--mobile:hover  { background: rgba(52,211,153,.12); border-color: var(--cat-mobile); color: var(--cat-mobile); }
  .cat-chip--pc:hover      { background: rgba(96,165,250,.12); border-color: var(--cat-pc); color: var(--cat-pc); }
  .cat-chip--console:hover { background: rgba(251,191,36,.12); border-color: var(--cat-console); color: var(--cat-console); }
  .cat-chip--social:hover  { background: rgba(167,139,250,.12); border-color: var(--cat-social); color: var(--cat-social); }
  .cat-chip--store:hover   { background: rgba(251,146,60,.12); border-color: var(--cat-store); color: var(--cat-store); }
  .cat-chip--other:hover   { background: rgba(148,163,184,.12); border-color: var(--cat-other); color: var(--cat-other); }
  .cat-show-more {
    margin-top: 4px; padding: 5px 14px; border-radius: 20px;
    border: 1px dashed var(--border); background: transparent;
    font-size: 12px; cursor: pointer; color: var(--muted); transition: all .2s;
  }
  .cat-show-more:hover { border-color: var(--accent); color: var(--accent); }
  .cat-hint { margin-top: 8px; font-size: 11px; color: var(--muted); opacity: .6; }
  .subcat-dropdown {
    position: absolute; z-index: 100;
    background: var(--card-bg); border: 1px solid var(--border);
    border-radius: 10px; padding: 8px 10px;
    display: flex; flex-wrap: wrap; gap: 6px; max-width: 340px;
    box-shadow: 0 8px 24px rgba(0,0,0,.4);
  }
  .subcat-dropdown .sub-chip {
    padding: 4px 10px; border-radius: 14px; font-size: 11px; cursor: pointer;
    border: 1px solid var(--border); color: var(--muted); background: transparent;
    white-space: nowrap; transition: all .15s;
  }
  .subcat-dropdown .sub-chip:hover { border-color: var(--accent); color: var(--accent); }

  /* ── KPI ── */
  .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 28px; }
  .kpi-card {
    background: var(--card-bg); border: 1px solid var(--border);
    border-radius: 12px; padding: 20px 22px;
  }
  .kpi-card.blue  { border-left: 3px solid var(--accent); }
  .kpi-card.green { border-left: 3px solid var(--accent3); }
  .kpi-card.yellow{ border-left: 3px solid var(--yellow); }
  .kpi-card.red   { border-left: 3px solid var(--red); }
  .kpi-card.purple{ border-left: 3px solid var(--accent2); }
  .kpi-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .07em; margin-bottom: 8px; }
  .kpi-value { font-size: 28px; font-weight: 700; letter-spacing: -0.5px; line-height: 1.1; }
  .kpi-sub   { font-size: 11px; color: var(--muted); margin-top: 6px; }

  /* ── Секции ── */
  .section-title {
    font-size: 13px; font-weight: 600; color: var(--muted);
    text-transform: uppercase; letter-spacing: .08em;
    margin: 24px 0 14px;
  }

  /* ── Графики ── */
  .charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 28px; }
  .charts-grid-3 { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 28px; }
  .chart-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
  .chart-title { font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 14px; text-transform: uppercase; letter-spacing: .07em; }
  .chart-wrap { height: 220px; position: relative; }

  /* ── Таблица ── */
  .table-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; margin-bottom: 28px; }
  .table-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border); }
  .table-header-title { font-size: 13px; font-weight: 600; }
  table { width: 100%; border-collapse: collapse; }
  th { padding: 10px 16px; text-align: left; font-size: 11px; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: .07em; border-bottom: 1px solid var(--border); }
  td { padding: 11px 16px; font-size: 13px; border-bottom: 1px solid #1e2236; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: var(--row-hover); }
  .rank { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--muted); }
  .rank.top { font-size: 16px; }
  .seller-name-cell { cursor: pointer; max-width: 240px; overflow: hidden; }
  .seller-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .price-cell { font-family: 'JetBrains Mono', monospace; color: var(--accent3); font-weight: 600; }
  .lots-badge { display: inline-block; padding: 2px 8px; border-radius: 12px; background: var(--surface); font-size: 11px; }
  .reviews-bar-wrap { display: flex; align-items: center; gap: 8px; }
  .reviews-bar { height: 4px; border-radius: 2px; background: var(--accent); min-width: 2px; }
  .reviews-num { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--muted); }

  /* ── Онлайн/оффлайн ── */
  .online-badge  { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--accent3); margin-right: 5px; }
  .offline-badge { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--muted); margin-right: 5px; }

  /* ── Карточки отзывов ── */
  .reviews-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; margin-bottom: 28px; }
  .review-card {
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 16px;
  }
  .review-card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
  .review-stars { color: var(--yellow); font-size: 13px; }
  .review-date { font-size: 11px; color: var(--muted); font-family: 'JetBrains Mono', monospace; }
  .review-item-label { font-size: 11px; color: var(--accent); margin-bottom: 6px; font-weight: 500; }
  .review-text { font-size: 12px; color: var(--text); line-height: 1.5; }

  /* ── Рыночные ниши ── */
  .niche-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 28px; }
  .niche-card {
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px 18px;
  }
  .niche-rank { font-size: 11px; color: var(--muted); margin-bottom: 6px; }
  .niche-range { font-size: 20px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--accent3); margin-bottom: 4px; }
  .niche-meta { font-size: 11px; color: var(--muted); }
  .niche-badge {
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-size: 10px; font-weight: 600; margin-top: 8px;
  }
  .niche-badge.low    { background: rgba(166,227,161,.15); color: var(--accent3); }
  .niche-badge.medium { background: rgba(249,226,175,.15); color: var(--yellow); }
  .niche-badge.high   { background: rgba(243,139,168,.15); color: var(--red); }

  /* ── Спиннер / пустое состояние ── */
  .empty-state { text-align: center; padding: 80px 20px; color: var(--muted); }
  .empty-icon { font-size: 48px; margin-bottom: 16px; }
  .loading-state { display: flex; align-items: center; justify-content: center; gap: 16px; padding: 80px 20px; color: var(--muted); }
  .spinner { width: 28px; height: 28px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .8s linear infinite; }
  @keyframes spin { to{transform:rotate(360deg)} }
  .error-banner { background: rgba(243,139,168,.12); border: 1px solid var(--red); border-radius: 10px; padding: 16px 20px; color: var(--red); margin-top: 20px; }

  /* ── Планшет/мобил ── */
  @media(max-width:900px){
    header { padding: 14px 20px; }
    .container { padding: 20px; }
    .charts-grid, .charts-grid-3 { grid-template-columns: 1fr; }
    .niche-cards { grid-template-columns: 1fr; }
    .kpi-grid { grid-template-columns: 1fr 1fr; }
  }
  @media(max-width:600px){
    .kpi-grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-icon">📊</div>
    <div class="logo-text">FunPay <span>Analytics</span></div>
  </div>
  <div class="header-meta">
    <span class="status-dot"></span>live · funpay.com
  </div>
</header>

<div class="container">

  <!-- Поиск -->
  <div class="search-section">
    <div class="search-label">URL категории, продавца или ID раздела</div>
    <div class="search-row">
      <input class="search-input" id="catUrl"
             placeholder="https://funpay.com/lots/610/ · /users/12345/ · 610">
      <select id="currency" class="search-input" style="max-width:120px; flex:none;" onchange="runAnalysis()">
        <option value="RUB">RUB (₽)</option>
        <option value="USD">USD ($)</option>
        <option value="EUR">EUR (€)</option>
        <option value="UAH">UAH (₴)</option>
      </select>
      <button class="btn btn-primary" id="analyzeBtn" onclick="runAnalysis()">Анализировать</button>
    </div>
    <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-top:14px; margin-bottom:10px;">
      <input type="number" id="minReviews" class="search-input"
             placeholder="Мин. отзывов" style="max-width:150px; padding:8px 14px; font-size:13px;"
             oninput="applyFilter()">
    </div>

    <div class="cat-groups-wrapper" style="position:relative;">

      <div class="cat-group">
        <span class="cat-group-label" style="color:var(--cat-mobile)">📱 Мобильные</span>
        <div class="cat-row">
          <span class="cat-chip cat-chip--mobile" onclick="openSubcats(event,'pubg-mobile',this)">PUBG Mobile</span>
          <span class="cat-chip cat-chip--mobile" onclick="openSubcats(event,'brawl-stars',this)">Brawl Stars</span>
          <span class="cat-chip cat-chip--mobile" onclick="openSubcats(event,'clash-royale',this)">Clash Royale</span>
          <span class="cat-chip cat-chip--mobile" onclick="openSubcats(event,'free-fire',this)">Free Fire</span>
          <span class="cat-chip cat-chip--mobile" onclick="openSubcats(event,'mobile-legends',this)">Mobile Legends</span>
          <span class="cat-chip cat-chip--mobile" onclick="openSubcats(event,'genshin',this)">Genshin Impact</span>
          <span class="cat-chip cat-chip--mobile" onclick="openSubcats(event,'honkai',this)">Honkai: Star Rail</span>
        </div>
      </div>

      <div class="cat-group">
        <span class="cat-group-label" style="color:var(--cat-pc)">🖥 ПК игры</span>
        <div class="cat-row">
          <span class="cat-chip cat-chip--pc" onclick="openSubcats(event,'dota2',this)">Dota 2</span>
          <span class="cat-chip cat-chip--pc" onclick="openSubcats(event,'cs2',this)">CS2</span>
          <span class="cat-chip cat-chip--pc" onclick="openSubcats(event,'wow',this)">World of Warcraft</span>
          <span class="cat-chip cat-chip--pc" onclick="openSubcats(event,'lost-ark',this)">Lost Ark</span>
          <span class="cat-chip cat-chip--pc" onclick="openSubcats(event,'poe',this)">Path of Exile</span>
          <span class="cat-chip cat-chip--pc" onclick="openSubcats(event,'valorant',this)">Valorant</span>
          <span class="cat-chip cat-chip--pc" onclick="openSubcats(event,'lol',this)">League of Legends</span>
          <span class="cat-chip cat-chip--pc" onclick="openSubcats(event,'gta',this)">GTA Online</span>
        </div>
      </div>

      <div id="extraCatGroups" style="display:none;">

        <div class="cat-group">
          <span class="cat-group-label" style="color:var(--cat-console)">🎮 Консоли</span>
          <div class="cat-row">
            <span class="cat-chip cat-chip--console" onclick="openSubcats(event,'playstation',this)">PlayStation</span>
            <span class="cat-chip cat-chip--console" onclick="openSubcats(event,'xbox',this)">Xbox</span>
            <span class="cat-chip cat-chip--console" onclick="openSubcats(event,'nintendo',this)">Nintendo</span>
          </div>
        </div>

        <div class="cat-group">
          <span class="cat-group-label" style="color:var(--cat-social)">💬 Соцсети</span>
          <div class="cat-row">
            <span class="cat-chip cat-chip--social" onclick="openSubcats(event,'vk',this)">ВКонтакте</span>
            <span class="cat-chip cat-chip--social" onclick="openSubcats(event,'telegram',this)">Telegram</span>
            <span class="cat-chip cat-chip--social" onclick="openSubcats(event,'instagram',this)">Instagram</span>
            <span class="cat-chip cat-chip--social" onclick="openSubcats(event,'youtube',this)">YouTube</span>
            <span class="cat-chip cat-chip--social" onclick="openSubcats(event,'tiktok',this)">TikTok</span>
          </div>
        </div>

        <div class="cat-group">
          <span class="cat-group-label" style="color:var(--cat-store)">🛒 Магазины</span>
          <div class="cat-row">
            <span class="cat-chip cat-chip--store" onclick="openSubcats(event,'steam',this)">Steam</span>
            <span class="cat-chip cat-chip--store" onclick="openSubcats(event,'appstore',this)">App Store</span>
            <span class="cat-chip cat-chip--store" onclick="openSubcats(event,'battlenet',this)">Battle.net</span>
            <span class="cat-chip cat-chip--store" onclick="openSubcats(event,'epicgames',this)">Epic Games</span>
          </div>
        </div>

        <div class="cat-group">
          <span class="cat-group-label" style="color:var(--cat-other)">⚡ Другое</span>
          <div class="cat-row">
            <span class="cat-chip cat-chip--other" onclick="openSubcats(event,'minecraft',this)">Minecraft</span>
            <span class="cat-chip cat-chip--other" onclick="openSubcats(event,'fortnite',this)">Fortnite</span>
            <span class="cat-chip cat-chip--other" onclick="openSubcats(event,'coc',this)">Clash of Clans</span>
          </div>
        </div>

      </div>

      <div id="subcatDropdown" class="subcat-dropdown" style="display:none;"></div>

      <button class="cat-show-more" id="catShowMoreBtn" onclick="toggleExtraGroups()">Показать все ▾</button>
      <div class="cat-hint">Не нашли нужную категорию? Скопируйте URL со страницы FunPay</div>

    </div>
  </div>

  <!-- Основной контент -->
  <div id="mainContent">
    <div class="empty-state">
      <div class="empty-icon">🔍</div>
      <div>Введите URL категории или профиля продавца FunPay</div>
      <div style="font-size:12px;opacity:.6;margin-top:6px">Например: https://funpay.com/lots/610/</div>
    </div>
  </div>

</div>

<script>
let charts = {};
let currentData = null;
let currentUrl = null;

const CURRENCY_SYMBOLS = { "RUB": "₽", "USD": "$", "EUR": "€", "UAH": "₴" };

function setUrl(url) {
  document.getElementById('catUrl').value = url;
}

const GAME_SUBCATS = {
  'pubg-mobile': [
    {n:'Аккаунты', u:'https://funpay.com/lots/346/'},
    {n:'UC', u:'https://funpay.com/lots/1013/'},
    {n:'Донат', u:'https://funpay.com/lots/1246/'},
    {n:'Буст', u:'https://funpay.com/lots/348/'},
    {n:'Достижения', u:'https://funpay.com/lots/709/'},
    {n:'Прочее', u:'https://funpay.com/lots/347/'},
  ],
  'brawl-stars': [
    {n:'Аккаунты', u:'https://funpay.com/lots/436/'},
    {n:'Гемы', u:'https://funpay.com/lots/967/'},
    {n:'Донат', u:'https://funpay.com/lots/1127/'},
    {n:'Brawl Pass', u:'https://funpay.com/lots/3126/'},
    {n:'Буст кубков', u:'https://funpay.com/lots/437/'},
    {n:'Буст рангов', u:'https://funpay.com/lots/1123/'},
    {n:'Прочее', u:'https://funpay.com/lots/908/'},
  ],
  'clash-royale': [
    {n:'Аккаунты', u:'https://funpay.com/lots/149/'},
    {n:'Гемы', u:'https://funpay.com/lots/973/'},
    {n:'Донат', u:'https://funpay.com/lots/1130/'},
    {n:'Pass Royale', u:'https://funpay.com/lots/3180/'},
    {n:'Предметы', u:'https://funpay.com/lots/150/'},
    {n:'Буст', u:'https://funpay.com/lots/156/'},
    {n:'Прочее', u:'https://funpay.com/lots/839/'},
  ],
  'free-fire': [
    {n:'Аккаунты', u:'https://funpay.com/lots/591/'},
    {n:'Алмазы', u:'https://funpay.com/lots/998/'},
    {n:'Донат', u:'https://funpay.com/lots/1307/'},
    {n:'Буст', u:'https://funpay.com/lots/592/'},
    {n:'Прочее', u:'https://funpay.com/lots/918/'},
  ],
  'mobile-legends': [
    {n:'Аккаунты', u:'https://funpay.com/lots/366/'},
    {n:'Алмазы', u:'https://funpay.com/lots/948/'},
    {n:'Донат', u:'https://funpay.com/lots/1232/'},
    {n:'Буст', u:'https://funpay.com/lots/367/'},
    {n:'Подарки', u:'https://funpay.com/lots/1297/'},
    {n:'Прочее', u:'https://funpay.com/lots/650/'},
  ],
  'genshin': [
    {n:'Аккаунты', u:'https://funpay.com/lots/696/'},
    {n:'Кристаллы', u:'https://funpay.com/lots/1000/'},
    {n:'Донат', u:'https://funpay.com/lots/1132/'},
    {n:'Прокачка', u:'https://funpay.com/lots/697/'},
    {n:'Фарм', u:'https://funpay.com/lots/1104/'},
    {n:'Квесты', u:'https://funpay.com/lots/2056/'},
    {n:'Прочее', u:'https://funpay.com/lots/1107/'},
  ],
  'honkai': [
    {n:'Аккаунты', u:'https://funpay.com/lots/1400/'},
    {n:'Донат', u:'https://funpay.com/lots/1401/'},
    {n:'Услуги', u:'https://funpay.com/lots/1402/'},
    {n:'Прочее', u:'https://funpay.com/lots/1403/'},
  ],
  'dota2': [
    {n:'Аккаунты', u:'https://funpay.com/lots/81/'},
    {n:'Предметы', u:'https://funpay.com/lots/210/'},
    {n:'Буст MMR', u:'https://funpay.com/lots/82/'},
    {n:'Калибровка', u:'https://funpay.com/lots/500/'},
    {n:'Обучение', u:'https://funpay.com/lots/502/'},
    {n:'Прочее', u:'https://funpay.com/lots/504/'},
  ],
  'cs2': [
    {n:'Аккаунты', u:'https://funpay.com/lots/1350/'},
    {n:'Скины', u:'https://funpay.com/lots/1906/'},
    {n:'Prime', u:'https://funpay.com/lots/1907/'},
    {n:'Буст', u:'https://funpay.com/lots/1836/'},
    {n:'Кейсы', u:'https://funpay.com/lots/3601/'},
    {n:'Прочее', u:'https://funpay.com/lots/1351/'},
  ],
  'wow': [
    {n:'Золото (RU/EU)', u:'https://funpay.com/chips/2/'},
    {n:'Аккаунты', u:'https://funpay.com/lots/13/'},
    {n:'Рейды', u:'https://funpay.com/lots/339/'},
    {n:'Прокачка', u:'https://funpay.com/lots/344/'},
    {n:'PvP', u:'https://funpay.com/lots/341/'},
    {n:'Прочее', u:'https://funpay.com/lots/345/'},
  ],
  'lost-ark': [
    {n:'Золото', u:'https://funpay.com/chips/91/'},
    {n:'Аккаунты', u:'https://funpay.com/lots/332/'},
    {n:'Предметы', u:'https://funpay.com/lots/333/'},
    {n:'Прокачка', u:'https://funpay.com/lots/334/'},
    {n:'Прочее', u:'https://funpay.com/lots/651/'},
  ],
  'poe': [
    {n:'Божественные сферы', u:'https://funpay.com/chips/173/'},
    {n:'Сферы хаоса', u:'https://funpay.com/chips/76/'},
    {n:'Аккаунты', u:'https://funpay.com/lots/27/'},
    {n:'Предметы', u:'https://funpay.com/lots/28/'},
    {n:'Прокачка', u:'https://funpay.com/lots/117/'},
    {n:'Прочее', u:'https://funpay.com/lots/667/'},
  ],
  'valorant': [
    {n:'Аккаунты', u:'https://funpay.com/lots/612/'},
    {n:'Points', u:'https://funpay.com/lots/1058/'},
    {n:'Донат', u:'https://funpay.com/lots/3388/'},
    {n:'Буст', u:'https://funpay.com/lots/614/'},
    {n:'Обучение', u:'https://funpay.com/lots/666/'},
    {n:'Прочее', u:'https://funpay.com/lots/613/'},
  ],
  'lol': [
    {n:'Riot Points', u:'https://funpay.com/lots/1315/'},
    {n:'Аккаунты', u:'https://funpay.com/lots/85/'},
    {n:'Буст', u:'https://funpay.com/lots/86/'},
    {n:'Квалификация', u:'https://funpay.com/lots/512/'},
    {n:'Обучение', u:'https://funpay.com/lots/513/'},
    {n:'Прочее', u:'https://funpay.com/lots/514/'},
  ],
  'gta': [
    {n:'Деньги', u:'https://funpay.com/chips/158/'},
    {n:'Аккаунты', u:'https://funpay.com/lots/87/'},
    {n:'Услуги', u:'https://funpay.com/lots/88/'},
    {n:'GTA+', u:'https://funpay.com/lots/3352/'},
    {n:'Прочее', u:'https://funpay.com/lots/879/'},
  ],
  'playstation': [
    {n:'Аккаунты', u:'https://funpay.com/lots/934/'},
    {n:'Пополнение', u:'https://funpay.com/lots/935/'},
    {n:'Plus', u:'https://funpay.com/lots/936/'},
    {n:'Ключи', u:'https://funpay.com/lots/937/'},
    {n:'Услуги', u:'https://funpay.com/lots/1270/'},
  ],
  'xbox': [
    {n:'Аккаунты', u:'https://funpay.com/lots/938/'},
    {n:'Пополнение', u:'https://funpay.com/lots/939/'},
    {n:'Game Pass', u:'https://funpay.com/lots/940/'},
    {n:'Ключи', u:'https://funpay.com/lots/941/'},
    {n:'Услуги', u:'https://funpay.com/lots/1314/'},
  ],
  'nintendo': [
    {n:'Аккаунты', u:'https://funpay.com/lots/1416/'},
    {n:'eShop', u:'https://funpay.com/lots/1417/'},
    {n:'Switch Online', u:'https://funpay.com/lots/1418/'},
    {n:'Прочее', u:'https://funpay.com/lots/1419/'},
  ],
  'vk': [
    {n:'Сообщества', u:'https://funpay.com/lots/699/'},
    {n:'Услуги', u:'https://funpay.com/lots/706/'},
  ],
  'telegram': [
    {n:'Каналы', u:'https://funpay.com/lots/702/'},
    {n:'Звёзды', u:'https://funpay.com/lots/2418/'},
    {n:'Premium', u:'https://funpay.com/lots/1391/'},
    {n:'Подарки', u:'https://funpay.com/lots/3064/'},
    {n:'Услуги', u:'https://funpay.com/lots/703/'},
    {n:'Игры', u:'https://funpay.com/lots/2422/'},
    {n:'Прочее', u:'https://funpay.com/lots/1392/'},
  ],
  'instagram': [
    {n:'Аккаунты', u:'https://funpay.com/lots/701/'},
    {n:'Услуги', u:'https://funpay.com/lots/704/'},
  ],
  'youtube': [
    {n:'Услуги', u:'https://funpay.com/lots/705/'},
    {n:'Каналы', u:'https://funpay.com/lots/700/'},
    {n:'Premium', u:'https://funpay.com/lots/1287/'},
    {n:'Прочее', u:'https://funpay.com/lots/2129/'},
  ],
  'tiktok': [
    {n:'Аккаунты', u:'https://funpay.com/lots/731/'},
    {n:'Монеты', u:'https://funpay.com/lots/2081/'},
    {n:'Услуги', u:'https://funpay.com/lots/732/'},
  ],
  'steam': [
    {n:'Пополнение', u:'https://funpay.com/lots/1086/'},
    {n:'Аккаунты с играми', u:'https://funpay.com/lots/89/'},
    {n:'Ключи', u:'https://funpay.com/lots/1008/'},
    {n:'Подарки', u:'https://funpay.com/lots/211/'},
    {n:'Услуги', u:'https://funpay.com/lots/1009/'},
    {n:'Оффлайн активации', u:'https://funpay.com/lots/1405/'},
    {n:'Смена региона', u:'https://funpay.com/lots/2044/'},
  ],
  'appstore': [
    {n:'Подарочные карты', u:'https://funpay.com/lots/1316/'},
  ],
  'battlenet': [
    {n:'Аккаунты с играми', u:'https://funpay.com/lots/632/'},
    {n:'Ключи', u:'https://funpay.com/lots/1065/'},
    {n:'Пополнение', u:'https://funpay.com/lots/889/'},
    {n:'Тайм карты', u:'https://funpay.com/lots/1167/'},
    {n:'Прочее', u:'https://funpay.com/lots/1089/'},
  ],
  'epicgames': [
    {n:'Аккаунты с играми', u:'https://funpay.com/lots/783/'},
    {n:'Ключи', u:'https://funpay.com/lots/1905/'},
    {n:'Пополнение', u:'https://funpay.com/lots/893/'},
    {n:'Оффлайн активации', u:'https://funpay.com/lots/2002/'},
    {n:'Прочее', u:'https://funpay.com/lots/2189/'},
  ],
  'minecraft': [
    {n:'Аккаунты', u:'https://funpay.com/lots/221/'},
    {n:'Ключи', u:'https://funpay.com/lots/1015/'},
    {n:'Minecoins', u:'https://funpay.com/lots/1016/'},
    {n:'Предметы', u:'https://funpay.com/lots/222/'},
    {n:'Услуги', u:'https://funpay.com/lots/223/'},
    {n:'Прочее', u:'https://funpay.com/lots/1099/'},
  ],
  'fortnite': [
    {n:'Аккаунты', u:'https://funpay.com/lots/248/'},
    {n:'В-баксы', u:'https://funpay.com/lots/928/'},
    {n:'Донат', u:'https://funpay.com/lots/1208/'},
    {n:'Услуги', u:'https://funpay.com/lots/249/'},
    {n:'Буст', u:'https://funpay.com/lots/1691/'},
    {n:'Прочее', u:'https://funpay.com/lots/1098/'},
  ],
  'coc': [
    {n:'Аккаунты', u:'https://funpay.com/lots/147/'},
    {n:'Гемы', u:'https://funpay.com/lots/972/'},
    {n:'Донат', u:'https://funpay.com/lots/1129/'},
    {n:'Gold Pass', u:'https://funpay.com/lots/3181/'},
    {n:'Услуги', u:'https://funpay.com/lots/155/'},
    {n:'Прочее', u:'https://funpay.com/lots/1097/'},
  ],
};

let _activeBtn = null;

function openSubcats(event, gameKey, btn) {
  event.stopPropagation();
  const cats = GAME_SUBCATS[gameKey] || [];
  if (cats.length <= 1) {
    if (cats[0]) setUrl(cats[0].u);
    return;
  }
  const dd = document.getElementById('subcatDropdown');
  if (_activeBtn === btn && dd.style.display !== 'none') {
    dd.style.display = 'none';
    btn.classList.remove('active');
    _activeBtn = null;
    return;
  }
  if (_activeBtn) _activeBtn.classList.remove('active');
  dd.innerHTML = cats.map(c =>
    `<span class="sub-chip" onclick="setUrl('${c.u}');closeSubcats()">${c.n}</span>`
  ).join('');
  const rect = btn.getBoundingClientRect();
  const wrapper = btn.closest('.cat-groups-wrapper');
  const wRect = wrapper.getBoundingClientRect();
  dd.style.left = (rect.left - wRect.left) + 'px';
  dd.style.top  = (rect.bottom - wRect.top + 4) + 'px';
  dd.style.display = 'flex';
  btn.classList.add('active');
  _activeBtn = btn;
}

function closeSubcats() {
  const dd = document.getElementById('subcatDropdown');
  dd.style.display = 'none';
  if (_activeBtn) { _activeBtn.classList.remove('active'); _activeBtn = null; }
}

function toggleExtraGroups() {
  const el = document.getElementById('extraCatGroups');
  const btn = document.getElementById('catShowMoreBtn');
  const hidden = el.style.display === 'none';
  el.style.display = hidden ? 'block' : 'none';
  btn.textContent = hidden ? 'Свернуть ▴' : 'Показать все ▾';
  if (!hidden) closeSubcats();
}

document.addEventListener('click', function(e) {
  if (!e.target.closest('#subcatDropdown') && !e.target.closest('.cat-chip')) {
    closeSubcats();
  }
});

function runAnalysis(overwriteUrl) {
  const raw = overwriteUrl || document.getElementById('catUrl').value.trim();
  if (!raw) return;

  let url = raw;
  if (/^\d+$/.test(raw)) url = `https://funpay.com/lots/${raw}/`;
  if (overwriteUrl) document.getElementById('catUrl').value = url;

  const currency = document.getElementById('currency').value;
  const btn = document.getElementById('analyzeBtn');
  btn.disabled = true;
  btn.textContent = 'Загружаю...';

  document.getElementById('mainContent').innerHTML = `
    <div class="loading-state">
      <div class="spinner"></div>
      <div>Парсим FunPay — это займёт 10–30 секунд...</div>
    </div>`;

  Object.values(charts).forEach(c => { try { c.destroy(); } catch(e){} });
  charts = {};

  fetch('/api/analyze', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url, currency})
  })
  .then(r => r.json())
  .then(data => {
    btn.disabled = false;
    btn.textContent = 'Анализировать';
    if (data.error) {
      document.getElementById('mainContent').innerHTML =
        `<div class="error-banner">❌ ${data.error}</div>`;
      return;
    }
    currentData = data;
    currentUrl = url;
    currentData.currencySymbol = CURRENCY_SYMBOLS[currency] || "₽";
    renderDashboard(currentData, currentUrl);
  })
  .catch(e => {
    btn.disabled = false;
    btn.textContent = 'Анализировать';
    document.getElementById('mainContent').innerHTML =
      `<div class="error-banner">❌ Ошибка запроса: ${e.message}</div>`;
  });
}

function applyFilter() {
  if (currentData) renderDashboard(currentData, currentUrl);
}

/* ════════════════════════════════════════════════
   ЭКСПОРТ В CSV
════════════════════════════════════════════════ */
function exportCSV() {
  if (!currentData) return;
  let rows = [], filename = 'funpay_export.csv';

  if (currentData.type === 'seller') {
    filename = `seller_${currentData.user_id}_lots.csv`;
    rows = [['Название', 'Цена', 'URL']];
    (currentData.lots || []).forEach(l => {
      rows.push([`"${(l.title||'').replace(/"/g,'""')}"`, l.price, l.url]);
    });
  } else {
    filename = 'category_sellers.csv';
    rows = [['Продавец', 'Отзывов', 'Ср. цена', 'Мин. цена', 'Макс. цена', 'Лотов', 'Онлайн', 'URL лота']];
    (currentData.top_sellers || []).forEach(s => {
      rows.push([
        `"${(s.name||'').replace(/"/g,'""')}"`,
        s.reviews, s.avg_price, s.min_price, s.max_price,
        s.lots_count, s.online ? 'Да' : 'Нет',
        s.first_lot_url
      ]);
    });
  }

  const csv = rows.map(r => r.join(',')).join('\n');
  const blob = new Blob(['\uFEFF' + csv], {type: 'text/csv;charset=utf-8;'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}

/* ════════════════════════════════════════════════
   РЕНДЕР: КАТЕГОРИЯ
════════════════════════════════════════════════ */
function renderDashboard(d, url) {
  if (d.type === 'seller') { renderSellerDashboard(d, url); return; }

  const curSym = d.currencySymbol || "₽";
  const minRevFilter = parseInt(document.getElementById('minReviews').value) || 0;
  document.getElementById('minReviews').style.display = 'inline-block';

  const filteredSellers = (d.top_sellers || []).filter(s => s.reviews >= minRevFilter);
  const maxRev = Math.max(...filteredSellers.map(s => s.reviews), 1);

  // Рыночные ниши
  const opps = d.market_opportunities || [];
  const nichesHTML = opps.length > 0 ? `
    <div class="section-title">Рыночные ниши — наименьшая конкуренция</div>
    <div class="niche-cards">
      ${opps.map((o, i) => {
        const label = o.competition_pct < 20 ? 'Низкая конкуренция' : o.competition_pct < 50 ? 'Средняя конкуренция' : 'Высокая конкуренция';
        const cls   = o.competition_pct < 20 ? 'low' : o.competition_pct < 50 ? 'medium' : 'high';
        return `
          <div class="niche-card">
            <div class="niche-rank">#${i+1} по потенциалу входа</div>
            <div class="niche-range">${o.range} ${curSym}</div>
            <div class="niche-meta">${o.count} лотов в диапазоне · рекомендуемая цена ${o.recommended_price} ${curSym}</div>
            <span class="niche-badge ${cls}">${label} (${o.competition_pct}%)</span>
          </div>`;
      }).join('')}
    </div>` : '';

  document.getElementById('mainContent').innerHTML = `
    <div class="kpi-grid">
      <div class="kpi-card yellow">
        <div class="kpi-label">Всего лотов</div>
        <div class="kpi-value">${d.total_lots.toLocaleString()}</div>
        <div class="kpi-sub">активных предложений</div>
      </div>
      <div class="kpi-card blue">
        <div class="kpi-label">Продавцов</div>
        <div class="kpi-value">${d.total_sellers.toLocaleString()}</div>
        <div class="kpi-sub">${d.online_sellers} онлайн прямо сейчас</div>
      </div>
      <div class="kpi-card green">
        <div class="kpi-label">Средняя цена</div>
        <div class="kpi-value">${d.price_avg} ${curSym}</div>
        <div class="kpi-sub">медиана ${d.price_median} ${curSym}</div>
      </div>
      <div class="kpi-card red">
        <div class="kpi-label">Диапазон цен</div>
        <div class="kpi-value">${d.price_min}–${d.price_max}</div>
        <div class="kpi-sub">${curSym} мин / макс</div>
      </div>
    </div>

    ${nichesHTML}

    <div class="section-title">Распределение рынка</div>
    <div class="charts-grid">
      <div class="chart-card">
        <div class="chart-title">Гистограмма цен</div>
        <div class="chart-wrap"><canvas id="priceChart"></canvas></div>
      </div>
      <div class="chart-card">
        <div class="chart-title">Топ-10 продавцов по отзывам</div>
        <div class="chart-wrap"><canvas id="sellersChart"></canvas></div>
      </div>
    </div>

    <div class="section-title" style="display:flex;justify-content:space-between;align-items:center;">
      <span>Топ продавцов</span>
      <button class="btn btn-green" style="font-size:11px;padding:6px 14px;" onclick="exportCSV()">⬇ Экспорт CSV</button>
    </div>
    <div class="table-card">
      <div class="table-header">
        <div class="table-header-title">Рейтинг по отзывам</div>
        <div style="font-size:11px;color:var(--muted)">${d.total_sellers} продавцов · ${d.total_lots} лотов</div>
      </div>
      <table>
        <thead>
          <tr>
            <th>#</th><th>Продавец</th><th>Отзывов</th>
            <th>Ср. цена</th><th>Лотов</th><th>Действие</th>
          </tr>
        </thead>
        <tbody>
          ${filteredSellers.length === 0
            ? '<tr><td colspan="6" style="text-align:center;color:var(--muted)">Нет продавцов, подходящих под фильтры</td></tr>'
            : filteredSellers.map((s,i) => `
              <tr>
                <td class="rank ${i<3?'top':''}">${i<3?['🥇','🥈','🥉'][i]:'#'+(i+1)}</td>
                <td class="seller-name-cell" title="${s.name}" onclick="window.open('${s.first_lot_url}','_blank')">
                  ${s.online ? '<span class="online-badge"></span>' : '<span class="offline-badge"></span>'}
                  <span class="seller-name" style="color:var(--text)">${s.name}</span>
                </td>
                <td>
                  <div class="reviews-bar-wrap">
                    <div class="reviews-bar" style="width:${Math.round(s.reviews/maxRev*100)}px"></div>
                    <span class="reviews-num">${s.reviews.toLocaleString()}</span>
                  </div>
                </td>
                <td class="price-cell">${s.avg_price} ${curSym}</td>
                <td><span class="lots-badge">${s.lots_count}</span></td>
                <td>
                  <button class="btn btn-ghost" style="padding:5px 12px;font-size:11px;"
                    onclick="event.stopPropagation();runAnalysis('${s.first_lot_url}')">
                    Анализ профиля
                  </button>
                </td>
              </tr>
            `).join('')}
        </tbody>
      </table>
    </div>
  `;

  if (charts.price) charts.price.destroy();
  if (charts.sellers) charts.sellers.destroy();

  const pb = d.price_buckets || [];
  charts.price = new Chart(document.getElementById('priceChart').getContext('2d'), {
    type: 'bar',
    data: {
      labels: pb.map(b => b.range),
      datasets: [{
        label: 'Лотов', data: pb.map(b => b.count),
        backgroundColor: 'rgba(240,192,64,0.75)', borderColor: '#f0c040',
        borderWidth: 1, borderRadius: 4,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#6b7280', font:{size:10} }, grid: { color: '#1e2230' } },
        y: { ticks: { color: '#6b7280', font:{size:10} }, grid: { color: '#1e2230' } },
      }
    }
  });

  const top10 = (d.top_sellers || []).slice(0,10);
  charts.sellers = new Chart(document.getElementById('sellersChart').getContext('2d'), {
    type: 'bar',
    data: {
      labels: top10.map(s => s.name.length>14 ? s.name.slice(0,14)+'…' : s.name),
      datasets: [{
        label: 'Отзывов', data: top10.map(s => s.reviews),
        backgroundColor: top10.map((_,i) =>
          i===0?'#f0c040':i===1?'#94a3b8':i===2?'#cd7f32':'rgba(137,180,250,0.6)'
        ),
        borderRadius: 4,
      }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#6b7280', font:{size:10} }, grid: { color: '#1e2230' } },
        y: { ticks: { color: '#e8eaf0', font:{size:11} }, grid: { display: false } },
      }
    }
  });
}

/* ════════════════════════════════════════════════
   РЕНДЕР: ПРОФИЛЬ ПРОДАВЦА
════════════════════════════════════════════════ */
function renderSellerDashboard(d, url) {
  document.getElementById('minReviews').style.display = 'none';

  const curSym = d.currencySymbol || "₽";
  const onlineDiv = d.online
    ? '<div style="display:flex;align-items:center;gap:6px"><span class="online-badge" style="margin:0"></span><span style="color:var(--accent3);font-size:11px;font-weight:600">ОНЛАЙН</span></div>'
    : '<div style="display:flex;align-items:center;gap:6px"><span class="offline-badge" style="margin:0"></span><span style="color:var(--muted);font-size:11px;font-weight:600">ОФФЛАЙН</span></div>';

  const starsHTML = '★'.repeat(Math.round(d.rating)) + '☆'.repeat(5 - Math.round(d.rating));
  const profileUrl = `https://funpay.com/users/${d.user_id}/`;
  const parsedBadge = d.reviews_parsed > 0
    ? `<span style="font-size:11px;color:var(--accent);background:rgba(137,180,250,.1);padding:2px 8px;border-radius:8px;margin-left:8px">проанализировано ${d.reviews_parsed} отзывов</span>`
    : '';

  // Карточки отзывов
  const textsHTML = (d.review_texts || []).length > 0 ? `
    <div class="section-title">Что говорят покупатели ${parsedBadge}</div>
    <div class="reviews-cards">
      ${d.review_texts.map(r => {
        const filled = '★'.repeat(r.stars || 0) + '☆'.repeat(5-(r.stars||0));
        return `
          <div class="review-card">
            <div class="review-card-header">
              <span class="review-stars">${filled}</span>
              <span class="review-date">${r.date}</span>
            </div>
            ${r.item ? `<div class="review-item-label">📦 ${r.item}</div>` : ''}
            <div class="review-text">${r.text}</div>
          </div>`;
      }).join('')}
    </div>` : '';

  // Хронология по месяцам
  const hasSalesByMonth = (d.sales_by_month || []).length > 0;
  const monthChartHTML = hasSalesByMonth ? `
    <div class="chart-card" style="margin-bottom:28px">
      <div class="chart-title">Хронология отзывов по месяцам</div>
      <div class="chart-wrap" style="height:240px"><canvas id="monthChart"></canvas></div>
    </div>` : '';

  // Распределение звёзд
  const hasRatingDist = (d.rating_dist || []).some(r => r.count > 0);
  const ratingDistHTML = hasRatingDist ? `
    <div class="chart-card" style="margin-bottom:28px">
      <div class="chart-title">Распределение оценок в отзывах</div>
      <div class="chart-wrap" style="height:240px"><canvas id="starsChart"></canvas></div>
    </div>` : '';

  const chartsCols = hasRatingDist && hasSalesByMonth
    ? `<div class="section-title">Аналитика по отзывам</div>
       <div class="charts-grid-3">
         ${monthChartHTML.replace('style="margin-bottom:28px"','')}
         ${ratingDistHTML.replace('style="margin-bottom:28px"','')}
       </div>`
    : (hasSalesByMonth ? `<div class="section-title">Аналитика по отзывам</div>${monthChartHTML}` : (hasRatingDist ? `<div class="section-title">Аналитика по отзывам</div>${ratingDistHTML}` : ''));

  document.getElementById('mainContent').innerHTML = `
    <div class="kpi-grid">
      <div class="kpi-card blue">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div class="kpi-label">Продавец</div>${onlineDiv}
        </div>
        <div class="kpi-value" style="font-size:22px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${d.name}">${d.name}</div>
        <div class="kpi-sub">ID: ${d.user_id} · <a href="${profileUrl}" target="_blank" style="color:var(--accent);text-decoration:none">открыть на FunPay ↗</a></div>
      </div>
      <div class="kpi-card yellow">
        <div class="kpi-label">Отзывов всего</div>
        <div class="kpi-value">${(d.total_reviews||0).toLocaleString()}</div>
        <div class="kpi-sub">за всё время работы</div>
      </div>
      <div class="kpi-card green">
        <div class="kpi-label">Рейтинг</div>
        <div class="kpi-value">${d.rating > 0 ? d.rating.toFixed(1) : '—'}</div>
        <div class="kpi-sub" style="color:var(--yellow)">${d.rating > 0 ? starsHTML : 'нет данных'}</div>
      </div>
      <div class="kpi-card red">
        <div class="kpi-label">Активные лоты</div>
        <div class="kpi-value">${d.lots_count}</div>
        <div class="kpi-sub">на данный момент</div>
      </div>
    </div>

    ${chartsCols}

    ${textsHTML}

    <div class="section-title">Часто продаваемые товары (по отзывам)</div>
    <div class="table-card">
      <div class="table-header">
        <div class="table-header-title">Топ товаров</div>
        <button class="btn btn-green" style="font-size:11px;padding:5px 12px;" onclick="exportCSV()">⬇ Экспорт CSV</button>
      </div>
      <table>
        <thead><tr><th>#</th><th>Название товара / описание</th><th>Продаж в отзывах</th></tr></thead>
        <tbody>
          ${(d.top_sold_items||[]).length === 0
            ? '<tr><td colspan="3" style="text-align:center;color:var(--muted)">Нет данных о продажах в недавних отзывах</td></tr>'
            : (d.top_sold_items||[]).map((item,i) => `
              <tr>
                <td class="rank ${i<3?'top':''}">${i<3?['🥇','🥈','🥉'][i]:'#'+(i+1)}</td>
                <td class="seller-name">${item.title}</td>
                <td><span class="lots-badge">${item.count}</span></td>
              </tr>
            `).join('')}
        </tbody>
      </table>
    </div>

    <div class="section-title" style="display:flex;justify-content:space-between;align-items:center;">
      <span>Активные лоты продавца</span>
      <div style="display:flex;gap:8px;">
        <input type="text" id="lotSearch" class="search-input" placeholder="Поиск лотов..."
               style="padding:6px 12px;font-size:11px;max-width:200px;" oninput="filterLots()">
        <input type="number" id="lotMinPrice" class="search-input" placeholder="Мин. цена"
               style="padding:6px 12px;font-size:11px;max-width:90px;" oninput="filterLots()">
        <input type="number" id="lotMaxPrice" class="search-input" placeholder="Макс. цена"
               style="padding:6px 12px;font-size:11px;max-width:90px;" oninput="filterLots()">
      </div>
    </div>
    <div class="table-card">
      <div class="table-header">
        <div class="table-header-title">Список лотов (<span id="lotsCount">${(d.lots||[]).length}</span>)</div>
      </div>
      <table>
        <thead><tr><th>Название</th><th>Цена</th></tr></thead>
        <tbody id="lotsTableBody">
          ${(d.lots||[]).length === 0
            ? '<tr><td colspan="2" style="text-align:center;color:var(--muted)">Нет активных лотов</td></tr>'
            : (d.lots||[]).map(lot => `
              <tr class="lot-row"
                  data-title="${lot.title.toLowerCase()}"
                  data-price="${lot.price}"
                  onclick="window.open('${lot.url}','_blank')" style="cursor:pointer">
                <td class="seller-name-cell" title="${lot.title}">
                  <span class="seller-name" style="color:var(--text);max-width:500px;white-space:normal">${lot.title}</span>
                </td>
                <td class="price-cell">${lot.price_text || (lot.price + ' ' + curSym)}</td>
              </tr>
            `).join('')}
        </tbody>
      </table>
    </div>
  `;

  // ── График хронологии по месяцам ──
  if (hasSalesByMonth) {
    Object.values(charts).forEach(c => { try{c.destroy();}catch(e){} });
    charts = {};
    const months = d.sales_by_month;
    charts.month = new Chart(document.getElementById('monthChart').getContext('2d'), {
      type: 'bar',
      data: {
        labels: months.map(m => m.month),
        datasets: [{
          label: 'Отзывов',
          data: months.map(m => m.count),
          backgroundColor: months.map((_, i) =>
            i === months.length-1 ? 'rgba(137,180,250,0.9)' : 'rgba(137,180,250,0.45)'
          ),
          borderColor: '#89b4fa',
          borderWidth: 1,
          borderRadius: 4,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => ` ${ctx.parsed.y} отзывов`
            }
          }
        },
        scales: {
          x: { ticks: { color: '#a6adc8', font:{size:11} }, grid: { color: '#313244' } },
          y: { ticks: { color: '#a6adc8', font:{size:10} }, grid: { color: '#313244' }, beginAtZero: true }
        }
      }
    });

    // ── Распределение звёзд ──
    if (hasRatingDist) {
      const dist = (d.rating_dist || []).sort((a,b) => b.stars - a.stars);
      charts.stars = new Chart(document.getElementById('starsChart').getContext('2d'), {
        type: 'bar',
        data: {
          labels: dist.map(r => '★'.repeat(r.stars)),
          datasets: [{
            data: dist.map(r => r.count),
            backgroundColor: dist.map(r =>
              r.stars === 5 ? 'rgba(166,227,161,0.8)' :
              r.stars === 4 ? 'rgba(137,180,250,0.7)' :
              r.stars === 3 ? 'rgba(249,226,175,0.7)' :
              r.stars === 2 ? 'rgba(250,179,135,0.7)' : 'rgba(243,139,168,0.7)'
            ),
            borderRadius: 4,
          }]
        },
        options: {
          indexAxis: 'y',
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: '#6b7280', font:{size:10} }, grid: { color: '#1e2230' } },
            y: { ticks: { color: '#f9e2af', font:{size:14} }, grid: { display: false } },
          }
        }
      });
    }
  }
}

/* ════════════════════════════════════════════════
   ФИЛЬТРАЦИЯ ЛОТОВ
════════════════════════════════════════════════ */
window.filterLots = function() {
  const text  = document.getElementById('lotSearch').value.toLowerCase();
  const minP  = parseFloat(document.getElementById('lotMinPrice').value) || 0;
  const maxP  = parseFloat(document.getElementById('lotMaxPrice').value) || Infinity;
  const rows  = document.querySelectorAll('.lot-row');
  let visible = 0;
  rows.forEach(row => {
    const match = row.getAttribute('data-title').includes(text)
                  && parseFloat(row.getAttribute('data-price')||'0') >= minP
                  && parseFloat(row.getAttribute('data-price')||'0') <= maxP;
    row.style.display = match ? '' : 'none';
    if (match) visible++;
  });
  const el = document.getElementById('lotsCount');
  if (el) el.innerText = visible;
};

/* Enter для запуска */
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('catUrl').addEventListener('keydown', e => {
    if (e.key === 'Enter') runAnalysis();
  });
});
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    currency = data.get("currency", "RUB").strip().upper()
    if currency not in ["RUB", "USD", "EUR", "UAH"]:
        currency = "RUB"
    max_reviews = int(data.get("max_reviews", 200))
    max_reviews = max(1, min(max_reviews, 1000))

    if not url:
        return jsonify({"error": "URL не указан"}), 400

    if url.isdigit():
        url = f"https://funpay.com/lots/{url}/"

    cache_key = f"{url}_{currency}"

    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and time.time() - cached["ts"] < 300:
            return jsonify(cached["data"])

    # Ссылка на конкретный лот → достаём профиль продавца
    if "/lots/offer" in url or "?id=" in url:
        try:
            from parser import _get
            soup = _get(url, currency=currency)
            if soup:
                user_link_el = soup.select_one("a[href*='/users/'], div[data-href*='/users/']")
                if user_link_el:
                    user_url = user_link_el.get("href") or user_link_el.get("data-href")
                    if user_url:
                        url = user_url if user_url.startswith("http") else "https://funpay.com" + user_url
        except Exception as e:
            logger.error(f"Failed to extract seller from lot: {e}")

    if "/users/" in url:
        result = analyze_seller(url, currency=currency, max_reviews=max_reviews)
    else:
        result = analyze_category(url, currency=currency)

    if "error" not in result:
        with _cache_lock:
            _cache[cache_key] = {"data": result, "ts": time.time()}

    return jsonify(result)


@app.route("/api/categories")
def api_categories():
    cats = get_categories()
    return jsonify(cats)


if __name__ == "__main__":
    print("=" * 50)
    print("  FunPay Analytics Dashboard")
    print("  http://localhost:5000")
    print("=" * 50)
    app.run(debug=False, host="0.0.0.0", port=5000)
