import streamlit as st
import pandas as pd
import requests
import time
import math
import urllib.parse
import matplotlib.pyplot as plt

# --- CONFIGURATION & SECRETS ---
# Streamlit will look for these in Settings -> Secrets
try:
    GOOGLE_KEY = st.secrets["GOOGLE_KEY"]
    WAVE_KEY = st.secrets["WAVE_KEY"]
except:
    st.error("API Keys missing! Please add GOOGLE_KEY and WAVE_KEY to Streamlit Secrets.")
    st.stop()

st.set_page_config(page_title="Lyreco Accessibility Monitor", layout="wide")

# --- CUSTOM CSS FOR STYLING ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .report-card { padding: 20px; border-radius: 10px; color: white; margin-bottom: 20px; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- CORE LOGIC ---
def calculate_lyreco_score(lh_pct, w_err, w_con):
    con_penalty = math.log1p(w_con) * 2.5
    err_penalty = math.sqrt(w_err) * 4.5
    wave_base = 100 - err_penalty - con_penalty
    if lh_pct > 0:
        return round((lh_pct * 0.4) + (wave_base * 0.6), 1)
    return round(wave_base, 1)

def run_audit(url):
    lh_val, err, con, issues = 0, 0, 0, "N/A"
    try:
        # Lighthouse
        url_enc = urllib.parse.quote(url)
        lh_api = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url_enc}&category=accessibility&onlyCategories=accessibility&strategy=desktop&key={GOOGLE_KEY}"
        r_lh = requests.get(lh_api, timeout=40)
        if r_lh.status_code == 200:
            d = r_lh.json()
            lh_val = d['lighthouseResult']['categories']['accessibility']['score'] * 100
            audits = d['lighthouseResult']['audits']
            issues = ", ".join([a['title'] for a in audits.values() if a.get('score', 1) < 1][:3])
        
        # WAVE
        r_w = requests.get(f"https://wave.webaim.org/api/request?key={WAVE_KEY}&url={url}", timeout=30