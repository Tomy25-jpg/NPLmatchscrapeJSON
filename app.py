import streamlit as st
import json
import time
import random
from curl_cffi import requests
from scipy.stats import poisson
import numpy as np

def calculate_xp(home_val, away_val):
    if home_val == 0 and away_val == 0: return 1.0, 1.0
    home_probs = [poisson.pmf(i, home_val) for i in range(11)]
    away_probs = [poisson.pmf(i, away_val) for i in range(11)]
    match_matrix = np.outer(home_probs, away_probs)
    p_home_win = np.sum(np.tril(match_matrix, -1))
    p_draw = np.sum(np.diag(match_matrix))
    p_away_win = np.sum(np.triu(match_matrix, 1))
    return round((p_home_win * 3) + (p_draw * 1), 3), round((p_away_win * 3) + (p_draw * 1), 3)

def get_match_data(match_id):
    headers = {"referer": f"https://www.sofascore.com/event/{match_id}"}
    try:
        meta_res = requests.get(f"https://www.sofascore.com/api/v1/event/{match_id}", impersonate="chrome120")
        if meta_res.status_code != 200: return None
        m = meta_res.json().get('event', {})
        h_score = m.get('homeScore', {}).get('display', 0)
        a_score = m.get('awayScore', {}).get('display', 0)
        
        if h_score > a_score: h_pts, a_pts = 3, 0
        elif a_score > h_score: h_pts, a_pts = 0, 3
        else: h_pts, a_pts = 1, 1

        shot_res = requests.get(f"https://www.sofascore.com/api/v1/event/{match_id}/shotmap", impersonate="chrome120", headers=headers)
        shots = shot_res.json().get('shotmap', []) if shot_res.status_code == 200 else []

        s = {"H-S": 0, "H-xG": 0.0, "H-xGOT": 0.0, "A-S": 0, "A-xG": 0.0, "A-xGOT": 0.0,
             "H-RG": 0.0, "H-RGOT": 0.0, "A-RG": 0.0, "A-RGOT": 0.0, "H-SP": 0.0, "H-C": 0.0, "A-SP": 0.0, "A-C": 0.0}

        for shot in shots:
            side = "H" if shot.get("isHome") else "A"
            sit = shot.get("situation", "regular")
            xg, xgot = shot.get("xg", 0.0) or 0.0, shot.get("xgot", 0.0) or 0.0
            s[f"{side}-S"] += 1
            s[f"{side}-xG"] += xg
            s[f"{side}-xGOT"] += xgot
            if sit == "regular": s[f"{side}-RG"] += xg; s[f"{side}-RGOT"] += xgot
            elif sit == "set-piece": s[f"{side}-SP"] += xg
            elif sit == "corner": s[f"{side}-C"] += xg

        xp_txg = calculate_xp(s["H-xG"], s["A-xG"])
        xp_tgot = calculate_xp(s["H-xGOT"], s["A-xGOT"])
        xp_rxg = calculate_xp(s["H-RG"], s["A-RG"])
        xp_rgot = calculate_xp(s["H-RGOT"], s["A-RGOT"])

        # FULL FORMAT
        full_data = {
            "Season": m.get('season', {}).get('name', 'N/A'),
            "Round": m.get('roundInfo', {}).get('round', 'N/A'),
            "Date": time.strftime('%d/%m/%Y', time.gmtime(m.get('startTimestamp', 0))),
            "Stadium": m.get('venue', {}).get('name', 'N/A'),
            "Crowd": m.get('attendance', 'N/A'),
            "Home Team": m.get('homeTeam', {}).get('name', 'N/A'),
            "Away Team": m.get('awayTeam', {}).get('name', 'N/A'),
            "Home Score": h_score,
            "Away Score": a_score,
            "H-Shots": s["H-S"],
            "H-xG (Total)": round(s["H-xG"], 3),
            "H-xGOT (Total)": round(s["H-xGOT"], 3),
            "A-Shots": s["A-S"],
            "A-xG (Total)": round(s["A-xG"], 3),
            "A-xGOT (Total)": round(s["A-xGOT"], 3),
            "H-xG (Reg)": round(s["H-RG"], 3),
            "H-xGOT (Reg)": round(s["H-RGOT"], 3),
            "A-xG (Reg)": round(s["A-RG"], 3),
            "A-xGOT (Reg)": round(s["A-RGOT"], 3),
            "H-xG (SetPiece)": round(s["H-SP"], 3),
            "H-xG (Corner)": round(s["H-C"], 3),
            "A-xG (SetPiece)": round(s["A-SP"], 3),
            "A-xG (Corner)": round(s["A-C"], 3),
            "xP-H (Total xG)": xp_txg[0],
            "xP-A (Total xG)": xp_txg[1],
            "xP-H (Total xGOT)": xp_tgot[0],
            "xP-A (Total xGOT)": xp_tgot[1],
            "xP-H (Reg xG)": xp_rxg[0],
            "xP-A (Reg xG)": xp_rxg[1],
            "xP-H (Reg xGOT)": xp_rgot[0],
            "xP-A (Reg xGOT)": xp_rgot[1],
            "Match ID": int(match_id),
            "Home Points": h_pts,
            "Away Points": a_pts
        }

        # SUMMARY FORMAT
        summary_data = {
            "Home Team": full_data["Home Team"],
            "Away Team": full_data["Away Team"],
            "Date": full_data["Date"],
            "Home Goals": full_data["Home Score"],
            "Away Goals": full_data["Away Score"]
        }

        return {"full": full_data, "summary": summary_data}
    except:
        return None

# --- STREAMLIT UI ---
st.set_page_config(page_title="SofaScore Scraper", layout="wide")
st.title("⚽ SofaScore Data Scraper")

match_input = st.text_input("Enter Match IDs (separated by commas)", "15368092")

if st.button("Scrape Data"):
    ids = [i.strip() for i in match_input.split(",")]
    full_list = []
    summary_list = []
    
    with st.spinner("Fetching data..."):
        for mid in ids:
            result = get_match_data(mid)
            if result:
                full_list.append(result["full"])
                summary_list.append(result["summary"])
            time.sleep(random.uniform(1.0, 2.0))
            
    if full_list:
        # Display Summary
        st.subheader("Match Summaries")
        st.code(json.dumps(summary_list, indent=4), language="json")
        
        # Display Full Data
        st.subheader("Detailed JSON Data")
        st.code(json.dumps(full_list, indent=4), language="json")
    else:
        st.error("No data found. Check your Match IDs.")
