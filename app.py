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
        # 1. Fetch Core Event Data
        meta_res = requests.get(f"https://www.sofascore.com/api/v1/event/{match_id}", impersonate="chrome120")
        if meta_res.status_code != 200: return None
        m = meta_res.json().get('event', {})
        
        # 2. Fetch Shotmap & Lineups
        shot_res = requests.get(f"https://www.sofascore.com/api/v1/event/{match_id}/shotmap", impersonate="chrome120", headers=HEADERS)
        lineup_res = requests.get(f"https://www.sofascore.com/api/v1/event/{match_id}/lineups", impersonate="chrome120", headers=HEADERS)
        incident_res = requests.get(f"https://www.sofascore.com/api/v1/event/{match_id}/incidents", impersonate="chrome120", headers=HEADERS)
        
        shots = shot_res.json().get('shotmap', []) if shot_res.status_code == 200 else []
        lineups = lineup_res.json() if lineup_res.status_code == 200 else {}
        incidents = incident_res.json().get('incidents', []) if incident_res.status_code == 200 else []

        # --- SECTION 1 & 2 DATA PREP ---
        h_score = m.get('homeScore', {}).get('display', 0)
        a_score = m.get('awayScore', {}).get('display', 0)
        h_team = m.get('homeTeam', {}).get('name', 'N/A')
        a_team = m.get('awayTeam', {}).get('name', 'N/A')

        # --- SECTION 3: PLAYER PERFORMANCE (FIXED IDs & FULL METRICS) ---
        player_stats = []
        for side in ['home', 'away']:
            is_home_side = (side == 'home')
            team_name = h_team if is_home_side else a_team
            players_list = lineups.get(side, {}).get('players', [])
            
            for p in players_list:
                stats_block = p.get('statistics')
                if not stats_block or stats_block.get('minutesPlayed', 0) == 0: continue
                
                p_id = p.get('player', {}).get('id')
                p_name = p.get('player', {}).get('name')
                
                # Metrics Accumulators
                xg_p, xg_m, xgot_p, xgot_m, g_p, g_m = 0.0, 0.0, 0.0, 0.0, 0, 0
                
                # Shot involvement (xG and xGOT)
                for shot in shots:
                    is_shot_home = shot.get('isHome')
                    val_xg = shot.get('xg', 0.0) or 0.0
                    val_xgot = shot.get('xgot', 0.0) or 0.0
                    
                    if is_shot_home == is_home_side:
                        xg_p += val_xg
                        xgot_p += val_xgot
                    else:
                        xg_m += val_xg
                        xgot_m += val_xgot

                # Goal involvement
                for inc in incidents:
                    if inc.get('incidentType') == 'goal':
                        is_goal_home = inc.get('isHome')
                        is_og = inc.get('incidentClass') == 'ownGoal'
                        # A goal for your side is either your team scoring or opposition OG
                        if (is_goal_home == is_home_side and not is_og) or (is_goal_home != is_home_side and is_og):
                            g_p += 1
                        else:
                            g_m += 1

                player_stats.append({
                    "Match ID": int(match_id),
                    "Player ID": p_id,
                    "Player": p_name,
                    "Team": team_name,
                    "Mins": stats_block.get('minutesPlayed', 0),
                    "xG_plus": round(xg_p, 3),
                    "xG_minus": round(xg_m, 3),
                    "xG_diff": round(xg_p - xg_m, 3),
                    "xGOT_plus": round(xgot_p, 3),
                    "xGOT_minus": round(xgot_m, 3),
                    "xGOT_diff": round(xgot_p - xgot_m, 3),
                    "G_plus": g_p,
                    "G_minus": g_m,
                    "G_diff": g_p - g_m
                })

        return {
            "summary": {"Match": f"{h_team} vs {a_team}", "Result": f"{h_score}-{a_score}", "Date": time.strftime('%d/%m/%Y', time.gmtime(m.get('startTimestamp', 0)))},
            "players": player_stats
        }
    except Exception as e:
        return None

# --- STREAMLIT UI ---
st.set_page_config(page_title="SofaScore Analytics", layout="wide")
st.title("⚽ SofaScore Player Performance Scraper")

match_input = st.text_input("Enter Match IDs", "15368116")

if st.button("Run Scraper"):
    ids = [i.strip() for i in match_input.split(",")]
    all_summaries, all_players = [], []
    
    with st.spinner("Crunching match stats..."):
        for mid in ids:
            result = get_match_data(mid)
            if result:
                all_summaries.append(result["summary"])
                all_players.extend(result["players"])
            time.sleep(random.uniform(1.5, 2.5))
            
    if all_players:
        st.subheader("Match Summaries")
        st.json(all_summaries)
        
        st.divider()
        st.subheader("Performance Data (xG, xGOT, Goals +/-)")
        st.info("Copy the JSON below for your database.")
        st.code(json.dumps(all_players, indent=4), language="json")
    else:
        st.error("Could not retrieve data. Please verify Match IDs.")
