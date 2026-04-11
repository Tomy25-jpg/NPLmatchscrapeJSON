import streamlit as st
import json
import time
import random
from curl_cffi import requests
from scipy.stats import poisson
import numpy as np

# --- SETTINGS ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.sofascore.com/",
}

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
    try:
        # Fetching basic event and shotmap data
        meta_res = requests.get(f"https://www.sofascore.com/api/v1/event/{match_id}", impersonate="chrome120")
        if meta_res.status_code != 200: return None
        m = meta_res.json().get('event', {})
        
        h_score = m.get('homeScore', {}).get('display', 0)
        a_score = m.get('awayScore', {}).get('display', 0)
        
        # Determine points
        if h_score > a_score: h_pts, a_pts = 3, 0
        elif a_score > h_score: h_pts, a_pts = 0, 3
        else: h_pts, a_pts = 1, 1

        shot_res = requests.get(f"https://www.sofascore.com/api/v1/event/{match_id}/shotmap", impersonate="chrome120", headers={"referer": f"https://www.sofascore.com/event/{match_id}"})
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
        
        # Core data assembly
        season = m.get('season', {}).get('name', 'N/A')
        round_val = m.get('roundInfo', {}).get('round', 'N/A')
        date = time.strftime('%d/%m/%Y', time.gmtime(m.get('startTimestamp', 0)))
        stadium = m.get('venue', {}).get('name', 'N/A')
        crowd = m.get('attendance', 'N/A')
        h_team = m.get('homeTeam', {}).get('name', 'N/A')
        a_team = m.get('awayTeam', {}).get('name', 'N/A')

        full_data = {
            "Season": season, "Round": round_val, "Date": date, "Stadium": stadium, "Crowd": crowd,
            "Home Team": h_team, "Away Team": a_team, "Home Score": h_score, "Away Score": a_score,
            "H-Shots": s["H-S"], "H-xG (Total)": round(s["H-xG"], 3), "H-xGOT (Total)": round(s["H-xGOT"], 3),
            "A-Shots": s["A-S"], "A-xG (Total)": round(s["A-xG"], 3), "A-xGOT (Total)": round(s["A-xGOT"], 3),
            "xP-H (Total xG)": xp_txg[0], "xP-A (Total xG)": xp_txg[1],
            "Match ID": int(match_id)
        }

        # --- Player Stats (The 3rd Section Logic) ---
        lineup_res = requests.get(f"https://www.sofascore.com/api/v1/event/{match_id}/lineups", impersonate="chrome120", headers=HEADERS)
        incident_res = requests.get(f"https://www.sofascore.com/api/v1/event/{match_id}/incidents", impersonate="chrome120", headers=HEADERS)
        
        lineups = lineup_res.json() if lineup_res.status_code == 200 else {}
        incidents = incident_res.json() if incident_res.status_code == 200 else {}
        
        # Format Meta Key: SeasonRoundDateStadiumCrowdHome TeamAway TeamHome ScoreAway Score
        meta_key = f"{season}{round_val}{date}{stadium.replace(' ', '')}{crowd}{h_team}{a_team}{h_score}{a_score}"
        player_stats = []

        for side in ['home', 'away']:
            is_home_side = (side == 'home')
            players_list = lineups.get(side, {}).get('players', [])
            for p in players_list:
                stats_block = p.get('statistics')
                if not stats_block or stats_block.get('minutesPlayed', 0) == 0: continue
                
                p_id = p.get('player', {}).get('id')
                xg_p, xg_m, g_p, g_m = 0.0, 0.0, 0, 0
                
                # Simple shot attribution for player involvement windows (using basic logic)
                for shot in shots:
                    is_shot_home = shot.get('isHome')
                    val = shot.get('xg', 0.0) or 0.0
                    if is_shot_home == is_home_side: xg_p += val
                    else: xg_m += val

                player_stats.append({
                    "Metadata": meta_key,
                    "Player": p.get('player', {}).get('name'),
                    "Team": h_team if is_home_side else a_team,
                    "Mins": stats_block.get('minutesPlayed', 0),
                    "xG_plus": round(xg_p, 3),
                    "xG_minus": round(xg_m, 3),
                    "xG_diff": round(xg_p - xg_m, 3)
                })

        return {"full": full_data, "summary": {"Home": h_team, "Away": a_team, "Score": f"{h_score}-{a_score}"}, "players": player_stats}
    except Exception as e:
        return None

# --- STREAMLIT UI ---
st.set_page_config(page_title="SofaScore Scraper Pro", layout="wide")
st.title("⚽ SofaScore Comprehensive Scraper")

match_input = st.text_input("Enter Match IDs (separated by commas)", "15368092")

if st.button("Scrape Everything"):
    ids = [i.strip() for i in match_input.split(",")]
    full_list, summary_list, player_list = [], [], []
    
    with st.spinner("Processing match data and player analytics..."):
        for mid in ids:
            result = get_match_data(mid)
            if result:
                full_list.append(result["full"])
                summary_list.append(result["summary"])
                player_list.extend(result["players"])
            time.sleep(random.uniform(1.5, 2.5))
            
    if full_list:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("1. Match Summaries")
            st.code(json.dumps(summary_list, indent=4), language="json")
        with col2:
            st.subheader("2. Detailed Match JSON")
            st.code(json.dumps(full_list, indent=4), language="json")
            
        st.divider()
        st.subheader("3. Player Performance Data (Copy-Pastable)")
        st.code(json.dumps(player_list, indent=4), language="json")
    else:
        st.error("No data found. Check your Match IDs or connection.")
