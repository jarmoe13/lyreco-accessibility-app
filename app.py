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
    .score-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- CORE LOGIC ---
def calculate_lyreco_score(lh_pct, w_err, w_con):
    """
    Improved scoring formula:
    - Lighthouse: 50% weight
    - WAVE: 50% weight
    - Linear penalties for errors (more strict)
    """
    # Linear penalties (stricter than logarithmic)
    err_penalty = w_err * 1.2  # Critical errors have high impact
    con_penalty = w_con * 0.5  # Contrast issues have moderate impact
    
    # Calculate WAVE base score with cap
    wave_base = 100 - err_penalty - con_penalty
    wave_base = max(0, wave_base)  # Cannot go below 0
    
    # Final score: 50% Lighthouse + 50% WAVE
    if lh_pct > 0:
        final_score = (lh_pct * 0.5) + (wave_base * 0.5)
    else:
        final_score = wave_base
    
    return round(max(0, final_score), 1)  # Ensure non-negative

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
    st.caption("Version 6.0 - Updated Scoring")

# --- MAIN INTERFACE ---
st.title("🌍 Lyreco Accessibility Dashboard")

# --- SCORE EXPLANATION ---
with st.expander("📊 How We Calculate the Lyreco Accessibility Score"):
    st.markdown("""
    ### Understanding Your Accessibility Score (0-100)
    
    The **Lyreco Automated Accessibility Score** combines two industry-standard tools to give you a comprehensive view of web accessibility compliance:
    
    #### 🔍 What We Measure:
    
    **1. Google Lighthouse (50% of final score)**
    - Automated WCAG 2.1 compliance checks
    - Tests: color contrast, ARIA labels, keyboard navigation, semantic HTML, and more
    - Provides a baseline accessibility score from 0-100
    
    **2. WAVE by WebAIM (50% of final score)**
    - Identifies critical accessibility errors (missing alt text, empty links, etc.)
    - Detects color contrast failures
    - Penalties applied based on error count:
      - **Critical errors**: 1.2 points deducted per error
      - **Contrast issues**: 0.5 points deducted per issue
    
    #### 📈 How to Use This Over Time:
    
    - **Score 90-100**: Excellent - minimal issues detected
    - **Score 75-89**: Good - some improvements needed
    - **Score 60-74**: Fair - multiple accessibility barriers present
    - **Score <60**: Needs attention - significant accessibility issues
    
    **Track your progress**: Run audits regularly to see if code changes improve or reduce accessibility. Compare platforms (e.g., Old Webshop vs NextGen) to understand which performs better.
    
    ⚠️ *Note: Automated tools catch ~30-40% of accessibility issues. Manual testing with real users is essential for full WCAG compliance.*
    """)

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
            st.markdown(f'<div class="score-card"><h2>{old_s}</h2><p>Old Webshop</p></div>', unsafe_allow_html=True)
        with col_c2:
            st.markdown(f'<div class="score-card"><h2>{new_s}</h2><p>NextGen Platform</p></div>', unsafe_allow_html=True)
        with col_c3:
            emoji = "📈" if improvement > 0 else "📉"
            st.markdown(f'<div class="score-card"><h2>{improvement}%</h2><p>{emoji} Change</p></div>', unsafe_allow_html=True)
        
        # Detailed Table
        st.subheader("Detailed Breakdown")
        df = pd.DataFrame([
            {"Platform": "Old Webshop", "Score": old_s, "Lighthouse": results["Old Webshop"]["lh"], 
             "WAVE Errors": results["Old Webshop"]["err"], "Contrast Issues": results["Old Webshop"]["con"]},
            {"Platform": "NextGen", "Score": new_s, "Lighthouse": results["NextGen"]["lh"], 
             "WAVE Errors": results["NextGen"]["err"], "Contrast Issues": results["NextGen"]["con"]}
        ])
        st.dataframe(df, use_container_width=True)

else:
    st.subheader("Single Country Deep-Dive Audit")
    country_url = st.text_input("Enter Country Webshop URL", placeholder="https://shop.lyreco.fr/fr")
    
    if st.button("🔍 Run Single Audit"):
        if country_url:
            with st.status("Running accessibility audit...", expanded=True) as status:
                result = run_audit(country_url)
                status.update(label="Audit Complete!", state="complete")
            
            # Display Score
            st.metric("Lyreco Accessibility Score", result["score"], delta=None)
            
            # Details
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Lighthouse Score", f"{result['lh']}%")
                st.metric("WAVE Errors", result['err'])
            with col2:
                st.metric("Contrast Issues", result['con'])
            
            st.info(f"**Top Issues Found**: {result['issues']}")
        else:
            st.warning("Please enter a URL to audit.")
