import streamlit as st
import pandas as pd
import requests
import math
import urllib.parse
import plotly.express as px
from datetime import datetime
import json

# --- CONFIGURATION ---
st.set_page_config(page_title="Lyreco Accessibility Monitor", layout="wide")

try:
    GOOGLE_KEY = st.secrets["GOOGLE_KEY"]
    WAVE_KEY = st.secrets["WAVE_KEY"]
    ANTHROPIC_API_KEY = st.secrets.get("ANTHROPIC_API_KEY", "")  # Optional for AI
except:
    st.error("⚠️ API Keys missing! Add GOOGLE_KEY and WAVE_KEY to Streamlit Secrets.")
    st.stop()

# --- COUNTRIES ---
COUNTRIES = {
    "France": {
        "home": "https://shop.lyreco.fr/fr",
        "category": "https://shop.lyreco.fr/fr/list/001001/papier-et-enveloppes/papier-blanc",
        "product": "https://shop.lyreco.fr/fr/product/157.796/papier-blanc-a4-lyreco-multi-purpose-80-g-ramette-500-feuilles"  
    },
    "UK": {
        "home": "https://shop.lyreco.co.uk/", 
        "category": "https://shop.lyreco.co.uk/en/list/001001/paper-envelopes/white-office-paper",
        "product": "https://shop.lyreco.co.uk/en/product/159.543/lyreco-white-a4-80gsm-copier-paper-box-of-5-reams-5x500-sheets-of-paper"
    },
    "Ireland": {
        "home": "https://shop.lyreco.ie/en",
        "category": "https://shop.lyreco.ie/en/list/001001/paper-envelopes/white-office-paper",
        "product": "https://shop.lyreco.ie/en/product/159.543/lyreco-white-a4-80gsm-copier-paper-box-of-5-reams-5x500-sheets-of-paper"
    },
    "Italy": {
        "home": "https://shop.lyreco.it/it",
        "category": "https://shop.lyreco.it/it/list/001001/carte-e-buste/carta-bianca",
        "product": "https://shop.lyreco.it/it/product/4.016.865/carta-bianca-lyreco-a4-75-g-mq-risma-500-fogli"
    },
    "Poland": {
        "home": "https://shop.lyreco.pl/pl",
        "category": "https://shop.lyreco.pl/pl/list/001001/papier-i-koperty/papiery-biale-uniwersalne",
        "product": "https://shop.lyreco.pl/pl/product/159.543/papier-do-drukarki-lyreco-copy-a4-80-g-m-5-ryz-po-500-arkuszy"
    },
    "Denmark": {
        "home": "https://shop.lyreco.dk/da",
        "category": "https://shop.lyreco.dk/da/list/001001/papir-kuverter/printerpapir-kopipapir",
        "product": "https://shop.lyreco.dk/da/product/159.543/kopipapir-til-sort-hvid-print-lyreco-copy-a4-80-g-pakke-a-5-x-500-ark"
    }
}

SSO_LOGIN = "https://welcome.lyreco.com/lyreco-customers/login?scope=openid+lyreco.contacts.personalInfo%3Awrite%3Aself&client_id=2ddf9463-3e1e-462a-9f94-633e1e062ae8&response_type=code&state=4102a88f-fec5-46d1-b8d9-ea543ba0a385&redirect_uri=https%3A%2F%2Fshop.lyreco.fr%2Foidc-login-callback%2FaHR0cHMlM0ElMkYlMkZzaG9wLmx5cmVjby5mciUyRmZy&ui_locales=fr-FR&logo_uri=https%3A%2F%2Fshop.lyreco.fr"

# --- HELPER FUNCTIONS ---
def safe_int(value):
    try:
        return int(value) if value is not None else 0
    except:
        return 0

def safe_float(value):
    try:
        return float(value) if value is not None else 0.0
    except:
        return 0.0

# --- SCORING FUNCTIONS ---
def calculate_lyreco_score(lh_pct, w_err, w_con):
    lh_pct = safe_float(lh_pct)
    w_err = safe_int(w_err)
    w_con = safe_int(w_con)
    
    err_penalty = w_err * 1.2
    con_penalty = w_con * 0.5
    wave_base = max(0, 100 - err_penalty - con_penalty)
    
    if lh_pct > 0:
        final_score = (lh_pct * 0.5) + (wave_base * 0.5)
    else:
        final_score = wave_base
    
    return round(max(0, final_score), 1)

def get_color_emoji(score):
    score = safe_float(score)
    if score >= 95:
        return "🟢🟢"
    elif score >= 90:
        return "🟢"
    elif score >= 80:
        return "🟡🟢"
    elif score >= 60:
        return "🟡"
    else:
        return "🔴"

def generate_recommendations(score, lh_val, wave_err, contrast, aria_issues, alt_issues):
    score = safe_float(score)
    lh_val = safe_float(lh_val)
    wave_err = safe_int(wave_err)
    contrast = safe_int(contrast)
    aria_issues = safe_int(aria_issues)
    alt_issues = safe_int(alt_issues)
    
    recommendations = []
    
    if aria_issues > 0:
        recommendations.append(f"🔴 CRITICAL: Fix {aria_issues} ARIA issues (screen readers)")
    
    if alt_issues > 0:
        recommendations.append(f"🔴 CRITICAL: Add alt text to {alt_issues} images")
    
    if contrast > 10:
        recommendations.append(f"🟡 HIGH: Fix {contrast} contrast issues (WCAG AA)")
    elif contrast > 0:
        recommendations.append(f"🟡 MEDIUM: Improve {contrast} contrast ratios")
    
    if wave_err > 20:
        recommendations.append(f"🔴 HIGH: {wave_err} accessibility errors detected")
    elif wave_err > 5:
        recommendations.append(f"🟡 MEDIUM: {wave_err} errors need attention")
    
    if score < 60:
        recommendations.append("⚠️ ACTION REQUIRED: Critical barriers present")
    elif score < 80:
        recommendations.append("📋 PLAN: Schedule fixes in next sprint")
    elif score >= 90:
        recommendations.append("✅ MAINTAIN: Monitor for regressions")
    
    return recommendations if recommendations else ["✅ No major issues detected"]

# --- AUDIT FUNCTION ---
def run_audit(url, page_type, country, deploy_version=""):
    lh_val = 0.0
    err = 0
    con = 0
    aria_issues = 0
    alt_issues = 0
    failed_audits = []
    
    # === LIGHTHOUSE ===
    try:
        url_enc = urllib.parse.quote(url)
        lh_api = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url_enc}&category=accessibility&onlyCategories=accessibility&strategy=desktop&key={GOOGLE_KEY}"
        r_lh = requests.get(lh_api, timeout=45)
        
        if r_lh.status_code == 200:
            d = r_lh.json()
            
            # Score
            score_value = d.get('lighthouseResult', {}).get('categories', {}).get('accessibility', {}).get('score')
            if score_value is not None:
                lh_val = float(score_value) * 100
            
            # Audits
            audits = d.get('lighthouseResult', {}).get('audits', {})
            for audit_id, audit_data in audits.items():
                score_val = audit_data.get('score', 1)
                if score_val is not None and score_val < 1:
                    title = audit_data.get('title', 'Unknown')
                    failed_audits.append(title)
                    
                    if 'aria' in audit_id.lower():
                        aria_issues += 1
                    
                    if 'image-alt' in audit_id or 'alt' in str(title).lower():
                        alt_issues += 1
                        
    except Exception as e:
        st.warning(f"⚠️ Lighthouse error for {country}-{page_type}: {str(e)[:80]}")
    
    # === WAVE ===
    try:
        wave_api = f"https://wave.webaim.org/api/request?key={WAVE_KEY}&url={url}"
        r_w = requests.get(wave_api, timeout=35)
        
        if r_w.status_code == 200:
            try:
                dw = r_w.json()
                
                # Safe extraction of errors
                if 'categories' in dw:
                    if 'error' in dw['categories']:
                        err_val = dw['categories']['error'].get('count')
                        if err_val is not None:
                            err = int(err_val)
                    
                    # Safe extraction of contrast
                    if 'contrast' in dw['categories']:
                        con_val = dw['categories']['contrast'].get('count')
                        if con_val is not None:
                            con = int(con_val)
                            
            except Exception as e:
                st.warning(f"⚠️ WAVE parsing error for {country}-{page_type}: {str(e)[:80]}")
        else:
            st.warning(f"⚠️ WAVE API returned status {r_w.status_code} for {country}-{page_type}")
            
    except Exception as e:
        st.warning(f"⚠️ WAVE request error for {country}-{page_type}: {str(e)[:80]}")
    
    # === CALCULATE SCORE (50/50) ===
    score = calculate_lyreco_score(lh_val, err, con)
    
    recommendations = generate_recommendations(score, lh_val, err, con, aria_issues, alt_issues)
    
    return {
        "Country": str(country),
        "Page Type": str(page_type),
        "URL": str(url),
        "Score": float(score),
        "Lighthouse": float(lh_val),
        "WAVE Errors": int(err),
        "Contrast Issues": int(con),
        "ARIA Issues": int(aria_issues),
        "Alt Text Issues": int(alt_issues),
        "Top Failed Audits": "; ".join(failed_audits[:3]) if failed_audits else "",
        "Recommendations": " | ".join(recommendations) if recommendations else "No data",
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Deploy_Version": str(deploy_version) if deploy_version else ""
    }

# --- AI ANALYSIS FUNCTION ---
def analyze_with_ai(df):
    """Send audit data to Claude for intelligent analysis"""
    
    if not ANTHROPIC_API_KEY:
        st.error("🤖 Claude API key not configured. Add ANTHROPIC_API_KEY to Streamlit Secrets.")
        return None
    
    # Prepare data summary for Claude
    summary = {
        "total_pages": len(df),
        "average_score": round(df['Score'].mean(), 1),
        "countries": df['Country'].unique().tolist(),
        "total_aria_issues": int(df['ARIA Issues'].sum()),
        "total_alt_issues": int(df['Alt Text Issues'].sum()),
        "total_contrast": int(df['Contrast Issues'].sum()),
        "total_wave_errors": int(df['WAVE Errors'].sum()),
        "worst_pages": df.nsmallest(3, 'Score')[['Country', 'Page Type', 'Score', 'ARIA Issues', 'WAVE Errors', 'Contrast Issues']].to_dict('records'),
        "best_pages": df.nlargest(3, 'Score')[['Country', 'Page Type', 'Score']].to_dict('records'),
        "by_country": df.groupby('Country').agg({
            'Score': 'mean',
            'ARIA Issues': 'sum',
            'Alt Text Issues': 'sum',
            'Contrast Issues': 'sum',
            'WAVE Errors': 'sum'
        }).round(1).to_dict('index')
    }
    
    # Claude prompt
    prompt = f"""You are an accessibility expert analyzing WCAG compliance audit results for Lyreco's e-commerce platforms across multiple countries.

**Audit Data:**
{json.dumps(summary, indent=2)}

**Your task:**
1. **Pattern Analysis**: Identify patterns across countries and page types. Are certain issues systemic?
2. **Root Cause**: What's likely causing the most critical issues? (e.g., shared components, design system issues)
3. **Priority Ranking**: Which fixes would have highest impact? Consider:
   - Severity (ARIA > Alt Text > Contrast)
   - Scope (affects multiple countries = higher priority)
   - Business impact (Product/Category pages > Login)
4. **Actionable Recommendations**: Give 3-5 specific, developer-ready actions

**Format your response in clear sections with emojis. Be concise but specific.**
"""
    
    # Call Claude API
    try:
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        data = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 2000,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['content'][0]['text']
        else:
            st.error(f"Claude API error: {response.status_code} - {response.text[:200]}")
            return None
            
    except Exception as e:
        st.error(f"Error calling Claude API: {str(e)}")
        return None

# --- DASHBOARD FUNCTIONS ---
def display_dashboard(df):
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Average Score", f"{df['Score'].mean():.1f}")
    with col2:
        st.metric("ARIA Issues", int(df['ARIA Issues'].sum()))
    with col3:
        st.metric("Alt Text Issues", int(df['Alt Text Issues'].sum()))
    with col4:
        st.metric("Contrast Issues", int(df['Contrast Issues'].sum()))
    
    st.divider()
    
    # Heatmap
    st.subheader("🗺️ Score Heatmap by Country & Page")
    
    def color_score(val):
        if pd.isna(val):
            return ''
        val = safe_float(val)
        if val >= 95:
            return 'background-color: #00cc66; color: white'
        elif val >= 90:
            return 'background-color: #66ff99'
        elif val >= 80:
            return 'background-color: #ffff66'
        elif val >= 60:
            return 'background-color: #ffcc66'
        else:
            return 'background-color: #ff6666; color: white'
    
    pivot_df = df.pivot_table(values='Score', index='Country', columns='Page Type', aggfunc='first')
    styled_df = pivot_df.style.applymap(color_score).format("{:.1f}", na_rep="N/A")
    st.dataframe(styled_df, use_container_width=True)
    
    st.divider()
    
    # Detailed Table
    st.subheader("📋 Detailed Results")
    
    country_filter = st.multiselect(
        "Filter by Country",
        options=df['Country'].unique().tolist(),
        default=df['Country'].unique().tolist()
    )
    
    filtered_df = df[df['Country'].isin(country_filter)]
    
    display_cols = ['Country', 'Page Type', 'Score', 'Lighthouse', 'WAVE Errors', 
                    'Contrast Issues', 'ARIA Issues', 'Alt Text Issues']
    st.dataframe(filtered_df[display_cols], use_container_width=True)
    
    st.divider()
    
    # Critical Issues
    st.subheader("🎯 Priority Actions")
    
    critical = df[df['Score'] < 80].sort_values('Score')
    
    if len(critical) > 0:
        for idx, row in critical.iterrows():
            with st.expander(f"⚠️ {row['Country']} - {row['Page Type']} (Score: {row['Score']:.1f})"):
                st.markdown(f"**URL:** {row['URL']}")
                st.markdown(f"**Lighthouse:** {row['Lighthouse']:.1f} | **WAVE Errors:** {safe_int(row['WAVE Errors'])} | **Contrast:** {safe_int(row['Contrast Issues'])}")
                
                st.markdown("**Recommendations:**")
                recs = str(row['Recommendations']).split(' | ')
                for i, rec in enumerate(recs, 1):
                    if rec and rec != 'nan':
                        st.markdown(f"{i}. {rec}")
                
                if pd.notna(row.get('Top Failed Audits')) and row['Top Failed Audits']:
                    st.markdown("**Failed Audits:**")
                    st.caption(row['Top Failed Audits'])
    else:
        st.success("✅ No critical issues! All pages score 80+")
    
    st.divider()
    
    # Chart
    st.subheader("📊 Score Distribution by Country")
    
    chart_df = df[df['Country'] != 'Global'].copy()
    if len(chart_df) > 0:
        fig = px.bar(
            chart_df,
            x='Country',
            y='Score',
            color='Page Type',
            barmode='group',
            title='Accessibility Scores by Country and Page Type'
        )
        fig.update_layout(yaxis_range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)
    
    # AI Analysis
    st.divider()
    st.subheader("🤖 AI-Powered Insights")
    
    if st.button("✨ Analyze Results with AI (Claude)", type="secondary"):
        with st.spinner("🤖 Claude is analyzing your accessibility data..."):
            analysis = analyze_with_ai(df)
            
            if analysis:
                st.markdown("### 📋 AI Analysis Report")
                st.markdown(analysis)
                
                # Option to download analysis
                st.download_button(
                    label="📥 Download AI Analysis",
                    data=analysis.encode('utf-8'),
                    file_name=f"ai_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain"
                )
    
    # Download CSV
    st.divider()
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Full Report (CSV)",
        data=csv,
        file_name=f"lyreco_audit_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

# --- MAIN UI ---
st.title("🌍 Lyreco Accessibility Monitor")
st.caption("Multi-country WCAG compliance tracking")

# Explanation
with st.expander("📊 How We Calculate Accessibility Score"):
    st.markdown("""
    ### Lyreco Accessibility Score (0-100)
    
    Combines two industry-standard tools:
    
    **🔍 Google Lighthouse (50%)**
    - Tests 40+ accessibility rules
    - Checks ARIA, semantic HTML, keyboard navigation
    
    **🌊 WAVE by WebAIM (50%)**
    - Detects critical errors (missing alt text, broken forms)
    - Identifies color contrast failures
    - Penalties: 1.2 points per error, 0.5 per contrast issue
    
    **Formula:**
    - WAVE base = 100 - (errors × 1.2) - (contrast × 0.5)
    - Final = (Lighthouse × 0.5) + (WAVE × 0.5)
    
    **📈 Score Ranges:**
    - 🟢🟢 95-100: Excellent
    - 🟢 90-95: Good
    - 🟡🟢 80-90: Fair
    - 🟡 60-80: Needs improvement
    - 🔴 <60: Critical issues
    
    ⚠️ *Automated tools catch ~40% of issues. Manual testing required for full compliance.*
    """)

st.divider()

# Mode Selection
tab1, tab2 = st.tabs(["🚀 Run New Audit", "📂 Upload Previous Results"])

with tab1:
    st.subheader("Run Multi-Country Audit")
    
    deploy_version = st.text_input("Deploy Version (optional)", placeholder="e.g., Sprint-15, v2.5")
    
    country_selection = st.multiselect(
        "Select Countries to Audit",
        options=list(COUNTRIES.keys()),
        default=list(COUNTRIES.keys())
    )
    
    if st.button("🚀 Start Audit", type="primary"):
        if not country_selection:
            st.warning("Please select at least one country")
        else:
            results = []
            
            # Progress
            total_audits = 1 + (len(country_selection) * 3)
            progress_bar = st.progress(0)
            status_text = st.empty()
            current = 0
            
            # SSO Login
            status_text.text("🔍 Auditing Global SSO Login...")
            results.append(run_audit(SSO_LOGIN, "Login (SSO)", "Global", deploy_version))
            current += 1
            progress_bar.progress(current / total_audits)
            
            # Countries
            for country in country_selection:
                pages = COUNTRIES[country]
                for page_type, url in pages.items():
                    status_text.text(f"🔍 Auditing {country} - {page_type.title()}...")
                    results.append(run_audit(url, page_type.title(), country, deploy_version))
                    current += 1
                    progress_bar.progress(current / total_audits)
            
            progress_bar.empty()
            status_text.empty()
            
            # Display results
            df = pd.DataFrame(results)
            st.success(f"✅ Audit complete! Tested {len(results)} pages")
            
            st.divider()
            display_dashboard(df)

with tab2:
    st.subheader("Upload Previous Audit Results")
    
    uploaded_file = st.file_uploader("Upload CSV from previous audit", type="csv")
    
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        st.success(f"✅ Loaded {len(df)} audit results")
        
        st.divider()
        display_dashboard(df)
    else:
        st.info("👆 Upload a CSV file to view historical results and compare over time")

# Footer
st.divider()
st.caption("Version 7.0 - AI-Powered Analysis | Lighthouse + WAVE + Claude")
