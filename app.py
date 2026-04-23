import streamlit as st
import json
import time
import random
from curl_cffi import requests
from scipy.stats import poisson
import numpy as np

# --- BOT PROTECTION CONFIG ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
]

def calculate_xp(home_val, away_val):
    if home_val == 0 and away_val == 0: return 1.0, 1.0
    home_probs = [poisson.pmf(i, home_val) for i in range(11)]
    away_probs = [poisson.pmf(i, away_val) for i in range(11)]
    match_matrix = np.outer(home_probs, away_probs)
    p_home_win = np.sum(np.tril(match_matrix, -1))
    p_draw = np.sum(np.diag(match_matrix))
    p_away_win = np.sum(np.triu(match_matrix, 1))
    return round((p_home_win * 3) + (p_draw * 1), 3), round((p_away_win * 3) + (p_draw * 1), 3)

def get_complete_match_data(match_id):
    # Enhanced browser headers
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"https://www.sofascore.com/event/{match_id}",
        "Origin": "https://www.sofascore.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    
    try:
        with requests.Session() as s:
            # Step 1: Core Event Data
            meta_res = s.get(f"https://www.sofascore.com/api/v1/event/{match_id}", impersonate="chrome124", headers=headers, timeout=15)
            
            if meta_res.status_code != 200:
                st.warning(f"Match {match_id} failed with Status: {meta_res.status_code}")
                return None
                
            m = meta_res.json().get('event', {})
            time.sleep(random.uniform(1.2, 2.0)) # Increased pacing for stability
            
            # Step 2: Stats & Shotmap & Lineups
            shot_res = s.get(f"https://www.sofascore.com/api/v1/event/{match_id}/shotmap", impersonate="chrome124", headers=headers)
            lineup_res = s.get(f"https://www.sofascore.com/api/v1/event/{match_id}/lineups", impersonate="chrome124", headers=headers)
            incident_res = s.get(f"https://www.sofascore.com/api/v1/event/{match_id}/incidents", impersonate="chrome124", headers=headers)
            
            shots = shot_res.json().get('shotmap', []) if shot_res.status_code == 200 else []
            lineups = lineup_res.json() if lineup_res.status_code == 200 else {}
            incidents = incident_res.json().get('incidents', []) if incident_res.status_code == 200 else []

        # --- PROCESS MATCH METRICS ---
        h_score = m.get('homeScore', {}).get('display', 0)
        a_score = m.get('awayScore', {}).get('display', 0)
        h_team = m.get('homeTeam', {}).get('name', 'N/A')
        a_team = m.get('awayTeam', {}).get('name', 'N/A')

        ms = {"H-S": 0, "A-S": 0, "H-xG": 0.0, "H-xGOT": 0.0, "A-xG": 0.0, "A-xGOT": 0.0,
              "H-RG": 0.0, "H-RGOT": 0.0, "A-RG": 0.0, "A-RGOT": 0.0, "H-SP": 0.0, "H-C": 0.0, "A-SP": 0.0, "A-C": 0.0}

        for shot in shots:
            side = "H" if shot.get("isHome") else "A"
            sit = shot.get("situation", "regular")
            xg, xgot = (shot.get("xg") or 0.0), (shot.get("xgot") or 0.0)
            ms[f"{side}-S"] += 1
            ms[f"{side}-xG"] += xg
            ms[f"{side}-xGOT"] += xgot
            if sit == "regular": ms[f"{side}-RG"] += xg; ms[f"{side}-RGOT"] += xgot
            elif sit == "set-piece": ms[f"{side}-SP"] += xg
            elif sit == "corner": ms[f"{side}-C"] += xg

        xp_total_xg = calculate_xp(ms["H-xG"], ms["A-xG"])
        xp_total_xgot = calculate_xp(ms["H-xGOT"], ms["A-xGOT"])
        xp_reg_xg = calculate_xp(ms["H-RG"], ms["A-RG"])
        xp_reg_xgot = calculate_xp(ms["H-RGOT"], ms["A-RGOT"])

        match_date = time.strftime('%d/%m/%Y', time.gmtime(m.get('startTimestamp', 0)))

        # 1. H2H JSON FORMAT
        h2h_data = {
            "Home Team": h_team,
            "Away Team": a_team,
            "Date": match_date,
            "Home Goals": h_score,
            "Away Goals": a_score
        }

        # 2. DETAILED MATCH JSON FORMAT
        match_data = {
            "Season": m.get('season', {}).get('name', 'N/A'),
            "Round": m.get('roundInfo', {}).get('round', 'N/A'),
            "Date": match_date,
            "Stadium": m.get('venue', {}).get('name', 'N/A'),
            "Crowd": m.get('attendance', 'N/A'),
            "Home Team": h_team,
            "Away Team": a_team,
            "Home Score": h_score,
            "Away Score": a_score,
            "H-Shots": ms["H-S"],
            "H-xG (Total)": round(ms["H-xG"], 3),
            "H-xGOT (Total)": round(ms["H-xGOT"], 3),
            "A-Shots": ms["A-S"],
            "A-xG (Total)": round(ms["A-xG"], 3),
            "A-xGOT (Total)": round(ms["A-xGOT"], 3),
            "H-xG (Reg)": round(ms["H-RG"], 3),
            "H-xGOT (Reg)": round(ms["H-RGOT"], 3),
            "A-xG (Reg)": round(ms["A-RG"], 3),
            "A-xGOT (Reg)": round(ms["A-RGOT"], 3),
            "H-xG (SetPiece)": round(ms["H-SP"], 3),
            "H-xG (Corner)": round(ms["H-C"], 3),
            "A-xG (SetPiece)": round(ms["A-SP"], 3),
            "A-xG (Corner)": round(ms["A-C"], 3),
            "xP-H (Total xG)": xp_total_xg[0],
            "xP-A (Total xG)": xp_total_xg[1],
            "xP-H (Total xGOT)": xp_total_xgot[0],
            "xP-A (Total xGOT)": xp_total_xgot[1],
            "xP-H (Reg xG)": xp_reg_xg[0],
            "xP-A (Reg xG)": xp_reg_xg[1],
            "xP-H (Reg xGOT)": xp_reg_xgot[0],
            "xP-A (Reg xGOT)": xp_reg_xgot[1],
            "Match ID": int(match_id),
            "Home Points": 3 if h_score > a_score else (1 if h_score == a_score else 0),
            "Away Points": 3 if a_score > h_score else (1 if h_score == a_score else 0)
        }

        # 3. PLAYER PERFORMANCE DATA JSON
        player_performance = []
        for side in ['home', 'away']:
            is_home_side = (side == 'home')
            team_label = h_team if is_home_side else a_team
            players = lineups.get(side, {}).get('players', [])
            
            for p in players:
                stats = p.get('statistics')
                if not stats or stats.get('minutesPlayed', 0) == 0: continue
                
                xg_p, xg_m, xgot_p, xgot_m, g_p, g_m = 0.0, 0.0, 0.0, 0.0, 0, 0
                
                for shot in shots:
                    is_h = shot.get('isHome')
                    if is_h == is_home_side:
                        xg_p += (shot.get('xg') or 0.0)
                        xgot_p += (shot.get('xgot') or 0.0)
                    else:
                        xg_m += (shot.get('xg') or 0.0)
                        xgot_m += (shot.get('xgot') or 0.0)

                for inc in incidents:
                    if inc.get('incidentType') == 'goal':
                        is_h = inc.get('isHome')
                        is_og = inc.get('incidentClass') == 'ownGoal'
                        if (is_h == is_home_side and not is_og) or (is_h != is_home_side and is_og):
                            g_p += 1
                        else:
                            g_m += 1

                player_performance.append({
                    "Match ID": int(match_id),
                    "Player ID": p.get('player', {}).get('id'),
                    "Player": p.get('player', {}).get('name'),
                    "Team": team_label,
                    "Mins": stats.get('minutesPlayed', 0),
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

        return {"h2h": h2h_data, "match": match_data, "players": player_performance}
    except Exception as e:
        st.error(f"Error processing match {match_id}: {str(e)}")
        return None

# --- STREAMLIT UI ---
st.set_page_config(page_title="NPL Data Hub", layout="wide")
st.title("⚽ Advanced SofaScore Data Extractor")

match_input = st.text_input("Enter Match IDs (separated by commas)", "15368050")

if st.button("Extract All Data"):
    ids = [i.strip() for i in match_input.split(",")]
    h2h_list, match_list, player_list = [], [], []
    
    progress_bar = st.progress(0)
    for index, mid in enumerate(ids):
        result = get_complete_match_data(mid)
        if result:
            h2h_list.append(result["h2h"])
            match_list.append(result["match"])
            player_list.extend(result["players"])
        
        # Increased random sleep between different match IDs
        time.sleep(random.uniform(3.5, 6.0))
        progress_bar.progress((index + 1) / len(ids))
            
    if h2h_list:
        st.subheader("1. H2H Format JSON")
        st.code(json.dumps(h2h_list, indent=4), language="json")
        
        st.divider()
        st.subheader("2. Detailed Match JSON")
        st.code(json.dumps(match_list, indent=4), language="json")
        
        st.divider()
        st.subheader("3. Player Performance JSON")
        st.code(json.dumps(player_list, indent=4), language="json")
    else:
        st.error("No data could be retrieved. If running on Streamlit Cloud, you may need a residential proxy.")
