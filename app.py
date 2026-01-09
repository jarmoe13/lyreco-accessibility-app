import streamlit as st
import pandas as pd
import requests
import time
import math
import urllib.parse
import matplotlib.pyplot as plt

# --- CONFIGURATION & SECRETS ---
try:
    GOOGLE_KEY = st.secrets["GOOGLE_KEY"]
    WAVE_KEY = st.secrets["WAVE_KEY"]
except:
    st.error("API Keys missing! Please add GOOGLE_KEY and WAVE_KEY to Streamlit Secrets.")
    st.stop()

st.set_page_config(page_title="Lyreco Accessibility Monitor", layout="wide")

# --- CUSTOM CSS ---
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
        # 1. Lighthouse Analysis
        url_enc = urllib.parse.quote(url)
        lh_api = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url_enc}&category=accessibility&onlyCategories=accessibility&strategy=desktop&key={GOOGLE_KEY}"
        r_lh = requests.get(lh_api, timeout=45)
        if r_lh.status_code == 200:
            d = r_lh.json()
            lh_val = d['lighthouseResult']['categories']['accessibility']['score'] * 100
            audits = d['lighthouseResult']['audits']
            issues = ", ".join([a['title'] for a in audits.values() if a.get('score', 1) < 1][:3])
        
        # 2. WAVE Analysis
        wave_api = f"https://wave.webaim.org/api/request?key={WAVE_KEY}&url={url}"
        r_w = requests.get(wave_api, timeout=35)
        if r_w.status_code == 200:
            dw = r_w.json()
            err = dw['categories']['error']['count']
            con = dw['categories']['contrast']['count']
            
    except Exception as e:
        issues = f"Audit connection issue: {str(e)}"
    
    score = calculate_lyreco_score(lh_val, err, con)
    return {"score": score, "lh": lh_val, "err": err, "con": con, "issues": issues}

# --- UI SIDEBAR ---
with st.sidebar:
    st.title("🛡️ Lyreco Agent")
    st.info("Global Accessibility Monitoring")
    mode = st.radio("Select Mode", ["Platform Comparison (Demo)", "Single Country Audit"])
    st.divider()
    st.caption("Final Version 5.5")

# --- MAIN INTERFACE ---
st.title("🌍 Lyreco Accessibility Dashboard")

if mode == "Platform Comparison (Demo)":
    st.subheader("Head-to-Head: France (Old Webshop vs NextGen)")
    
    if st.button("🚀 Start Comparison Audit"):
        # Demo links for France
        platforms = {
            "Old Webshop": "https://www.lyreco.com/webshop/FRFR/index.html?lc=FRFR",
            "NextGen": "https://shop.lyreco.fr/fr"
        }
        
        results = {}
        for name, url in platforms.items():
            with st.status(f"Analyzing {name}...", expanded=True) as status:
                results[name] = run_audit(url)
                status.update(label=f"Finished {name}!", state="complete")
        
        # Display Summary Cards
        old_s = results["Old Webshop"]["score"]
        new_s = results["NextGen"]["score"]
        improvement = round(((new_s - old_s) / old_s) * 100, 1) if old_s > 0 else 0
        
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            st.markdown(f'<div class="report-card" style="background:#e74c3c"><h4>Old Webshop</h4><h1>{old_s}</h1></div>', unsafe_allow_html=True)
        with col_c2:
            st.markdown(f'<div class="report-card" style="background:#27ae60"><h4>NextGen Platform</h4><h1>{new_s}</h1></div>', unsafe_allow_html=True)
        with col_c3:
            st.markdown(f'<div class="report-card" style="background:#2980b9"><h4>Improvement</h4><h1>+{improvement}%</h1></div>', unsafe_allow_html=True)
        
        # Comparison Chart
        st.divider()
        chart_df = pd.DataFrame({
            'Metric': ['Overall Score', 'Lighthouse %', 'WAVE Errors'],
            'Old Webshop': [old_s, results["Old Webshop"]["lh"], results["Old Webshop"]["err"]],
            'NextGen': [new_s, results["NextGen"]["lh"], results["NextGen"]["err"]]
        }).set_index('Metric')
        
        st.bar_chart(chart_df)
        
        # Technical Insights
        with st.expander("See Detailed Technical Issues"):
            st.write("**Old Webshop Issues:**", results["Old Webshop"]["issues"])
            st.write("**NextGen Issues:**", results["NextGen"]["issues"])

else:
    st.subheader("Custom Country Audit")
    target_url = st.text_input("Enter Lyreco URL", "https://shop.lyreco.it/it")
    if st.button("Run Audit"):
        with st.spinner("Analyzing..."):
            res = run_audit(target_url)
            st.metric("Final Lyreco Score", res['score'])
            st.write("### Technical Details")
            st.json(res)
