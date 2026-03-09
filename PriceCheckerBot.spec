# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\Users\\prsed\\AppData\\Local\\Programs\\Python\\Python313\\tcl\\tcl8', '_tcl_data'), ('C:\\Users\\prsed\\AppData\\Local\\Programs\\Python\\Python313\\tcl\\tk8.6', '_tk_data')]
binaries = []
hiddenimports = ['price_tracker', 'price_tracker.core', 'price_tracker.core.price_extractor', 'price_tracker.core.heuristics', 'price_tracker.core.jsonld_parser', 'price_tracker.core.store_detector', 'price_tracker.scrapers', 'price_tracker.scrapers.kabum', 'price_tracker.scrapers.pichau', 'price_tracker.scrapers.terabyte', 'price_tracker.scrapers.amazon', 'price_tracker.scrapers.universal', 'price_tracker.utils', 'price_tracker.utils.html_fetcher', 'price_tracker.utils.price_parser', 'cloudscraper', 'gspread', 'oauth2client', 'oauth2client.service_account', 'bs4', 'lxml', 'lxml.etree', 'tldextract', 'playwright', 'playwright.sync_api', 'playwright_stealth', 'charset_normalizer', 'chardet']
tmp_ret = collect_all('playwright')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('cloudscraper')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('price_tracker')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('gspread')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tldextract')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('charset_normalizer')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PriceCheckerBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PriceCheckerBot',
)
