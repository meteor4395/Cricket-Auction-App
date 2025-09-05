# auction_app.py
import streamlit as st
import pandas as pd
import sqlite3
import os
import time
import re
import requests
import base64
from io import BytesIO
from PIL import Image, UnidentifiedImageError
import random

# ----------------- CONFIG -----------------
DB_FILE = "auction.db"
PLACEHOLDER = "assets/placeholder.png"
BELL = "assets/bell.mp3"

st.set_page_config(page_title="🏏 Cricket Auction App (DB)", layout="wide")
st.sidebar.markdown("[🌐 GitHub](https://github.com/meteor4395)  |  🧑‍💻 Enhanced by **meteor**")
st.sidebar.title("🏏 Cricket Auction System")

# ----------------- DATABASE HELPERS -----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # players table: store raw columns from Excel + auctioned flag
    c.execute("""
        CREATE TABLE IF NOT EXISTS players (
            player_id INTEGER PRIMARY KEY,
            full_name TEXT,
            department TEXT,
            year TEXT,
            role TEXT,
            photo TEXT,
            auctioned INTEGER DEFAULT 0
        )
    """)
    # teams table
    c.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            team TEXT PRIMARY KEY,
            budget INTEGER,
            initial_budget INTEGER,
            spent INTEGER DEFAULT 0
        )
    """)
    # results table (history)
    c.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            full_name TEXT,
            team TEXT,
            price INTEGER,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_players_df_to_db(df: pd.DataFrame):
    """
    Save players dataframe into the DB.
    Expects df columns: FULL NAME, DEPARTMENT, YEAR, PLAYER ROLE, UPLOAD YOUR PHOTO
    Will map them into players table and set player_id starting at 1.
    """
    # normalize columns
    df = df.rename(columns={
        'FULL NAME': 'full_name',
        'DEPARTMENT': 'department',
        'YEAR': 'year',
        'PLAYER ROLE': 'role',
        'UPLOAD YOUR PHOTO': 'photo'
    })
    df = df[['full_name', 'department', 'year', 'role', 'photo']].copy()
    df.reset_index(drop=True, inplace=True)
    df['player_id'] = df.index + 1
    df['auctioned'] = 0

    conn = sqlite3.connect(DB_FILE)
    # replace players table with new data
    df[['player_id', 'full_name', 'department', 'year', 'role', 'photo', 'auctioned']].to_sql(
        "players", conn, if_exists="replace", index=False
    )
    conn.commit()
    conn.close()

def load_players_df_from_db() -> pd.DataFrame:
    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql("SELECT * FROM players ORDER BY player_id", conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

def save_teams_to_db(teams: list):
    """
    teams: list of dicts with keys: 'Team' (name), 'Budget' (current), 'InitialBudget', 'Spent'
    We'll store 'team', 'budget', 'initial_budget', 'spent' columns.
    """
    df = pd.DataFrame([{
        'team': t['Team'],
        'budget': int(t.get('Budget', 0)),
        'initial_budget': int(t.get('InitialBudget', t.get('Budget', 0))),
        'spent': int(t.get('Spent', 0))
    } for t in teams])
    conn = sqlite3.connect(DB_FILE)
    df.to_sql("teams", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()

def load_teams_from_db() -> list:
    conn = sqlite3.connect(DB_FILE)
    try:
        df = pd.read_sql("SELECT * FROM teams", conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    if df.empty:
        return []
    out = []
    for _, row in df.iterrows():
        out.append({
            'Team': row['team'],
            'Budget': int(row['budget']),
            'InitialBudget': int(row['initial_budget']),
            'Spent': int(row['spent']),
            'Players': []  # we'll fill players list on demand from results
        })
    return out

def add_result_to_db(player_id:int, full_name:str, team:str, price:int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO results (player_id, full_name, team, price) VALUES (?, ?, ?, ?)",
              (player_id, full_name, team, price))
    # mark player auctioned
    c.execute("UPDATE players SET auctioned = 1 WHERE player_id = ?", (player_id,))
    # if team not UNSOLD, update team's spent and budget
    if team != "UNSOLD":
        c.execute("UPDATE teams SET spent = spent + ?, budget = budget - ? WHERE team = ?",
                  (price, price, team))
    conn.commit()
    conn.close()

# ----------------- EXTRA RESET FUNCTIONS -----------------
def clear_results():
    """Delete only results table (auction summary)."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM results")
    conn.commit()
    conn.close()

def reset_summary_session():
    """Clear only summary-related session state values."""
    if "auction_results" in st.session_state:
        st.session_state.auction_results = []
    if "current_player" in st.session_state:
        st.session_state.current_player = None
    if "start_time" in st.session_state:
        st.session_state.start_time = None

def load_results_from_db():
    """Load auction results as a DataFrame."""
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql("SELECT * FROM results", conn)
    conn.close()
    return df


def export_results_to_excel(results_df: pd.DataFrame, teams: list, filename="auction_results.xlsx"):
    # results_df is a dataframe of results
    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        if not results_df.empty:
            results_df.to_excel(writer, index=False, sheet_name="Results")
        # team sheets
        for t in teams:
            team_name = t['Team'][:31] if t['Team'] else "Team"
            # fetch players for this team from results
            team_res = results_df[results_df['team'] == t['Team']]
            if team_res.empty:
                continue
            # We want cols: player_id, full_name, maybe price
            team_res[['player_id', 'full_name', 'price']].rename(
                columns={'player_id': 'Player ID', 'full_name': 'FULL NAME', 'price': 'Price'}
            ).to_excel(writer, index=False, sheet_name=team_name)

# ----------------- DRIVE IMAGE HELPERS -----------------
def extract_drive_file_id(link: str):
    """Extract Google Drive file id from various link formats or return None."""
    if not link or pd.isna(link):
        return None
    s = str(link).strip()

    # Common patterns: id=..., /d/<id>/, or just the id
    m = re.search(r'id=([a-zA-Z0-9_\-]+)', s)
    if m:
        fid = m.group(1)
    else:
        m = re.search(r'/d/([a-zA-Z0-9_\-]+)', s)
        if m:
            fid = m.group(1)
        else:
            # maybe just pasted the id
            m = re.fullmatch(r'[a-zA-Z0-9_\-]{8,}', s)
            if m:
                fid = s
            else:
                return None
    fid = fid.strip().rstrip(' _.,?&')
    return fid if fid else None

def make_drive_download_url(fid: str):
    # export=download tends to return raw bytes
    return f"https://drive.google.com/uc?export=download&id={fid}"

@st.cache_data(show_spinner=False)
def download_image_bytes(url: str):
    """Download bytes for an image URL (cached). Returns bytes or raises."""
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=12)
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "")

def show_player_image(photo_link, caption=""):
    """Display player image from local photos folder. Fallback to placeholder if not found."""
    placeholder_exists = os.path.exists(PLACEHOLDER)
    # photo_link is not used anymore, we need player_id from context
    # Expect photo_link to be player_id or dict with player_id
    player_id = None
    if isinstance(photo_link, dict):
        player_id = photo_link.get('player_id')
    elif isinstance(photo_link, int):
        player_id = photo_link
    elif isinstance(photo_link, str):
        # Try to parse player_id from string
        try:
            player_id = int(photo_link)
        except Exception:
            player_id = None
    # Build local photo path
    img_path = None
    if player_id is not None:
        img_path = os.path.join("photos", f"photo_{player_id-1}.jpg")
        abs_img_path = os.path.join(os.path.dirname(__file__), img_path)
        if os.path.exists(abs_img_path):
            try:
                img = Image.open(abs_img_path)
                st.image(img, width=400, caption=caption)
                return
            except Exception:
                pass
    # Fallback to placeholder
    if placeholder_exists:
        st.image(PLACEHOLDER, width=200, caption=caption)
    else:
        st.write("(image not available)")
    if caption:
        st.caption(caption)

# ----------------- SOUND -----------------
def play_sound():
    if os.path.exists(BELL):
        try:
            with open(BELL, "rb") as f:
                audio_bytes = f.read()
            st.audio(audio_bytes, format="audio/mp3")
        except Exception:
            # fallback to inline base64
            try:
                with open(BELL, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                st.markdown(f"""
                    <audio autoplay>
                      <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
                    </audio>
                """, unsafe_allow_html=True)
            except Exception:
                pass

# ----------------- APP INIT -----------------
init_db()
if "auctioned_ids" not in st.session_state:
    st.session_state.auctioned_ids = set()

with st.sidebar:
    if st.button("🗑️ Reset Auction Summary"):
        clear_results()
        reset_summary_session()
        st.session_state.auctioned_ids.clear()  # 🔹 FIX: reset tracker too
        st.success("✅ Auction results and unsold players cleared from summary! Team details remain unchanged.")
        st.rerun()

# Load persisted data into session_state on first run
if "db_loaded" not in st.session_state:
    # load players and teams into session state for UI convenience
    st.session_state.players_df = load_players_df_from_db()
    st.session_state.teams = load_teams_from_db()
    st.session_state.auction_results = load_results_from_db().to_dict(orient="records") if not load_results_from_db().empty else []
    st.session_state.current_player = None
    st.session_state.start_time = None
    st.session_state.db_loaded = True

# ----------------- FIX: Unique random player picker -----------------
def pick_unique_random_player():
    """Pick a random unauctioned player not seen before."""
    fresh_players = load_players_df_from_db()
    unauctioned_df = fresh_players[fresh_players['auctioned'] == 0]

    # ✅ FIX: Only filter by auctioned flag, not session tracker if DB is fresh
    if unauctioned_df.empty:
        return None

    # Exclude players already chosen in this session (extra safeguard)
    unauctioned_df = unauctioned_df[~unauctioned_df['player_id'].isin(st.session_state.auctioned_ids)]

    if unauctioned_df.empty:
        return None

    picked = unauctioned_df.sample(1).iloc[0].to_dict()
    st.session_state.auctioned_ids.add(picked['player_id'])  # track this ID
    return picked

# ----------------- UI: Tabs -----------------
tabs = st.tabs(["📅 Upload Players", "👥 Team Setup", "🎯 Auction Panel", "📊 Summary & Export"])

# 1️⃣ Upload Players
with tabs[0]:
    st.title("📅 Upload Player List")
    uploaded_file = st.file_uploader("Upload Excel file (xlsx)", type=["xlsx"])
    required_columns = ["FULL NAME", "DEPARTMENT", "YEAR", "PLAYER ROLE", "UPLOAD YOUR PHOTO"]

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file)
            df.columns = [str(c).strip() for c in df.columns]  # normalize headers
            if not all(col in df.columns for col in required_columns):
                missing = list(set(required_columns) - set(df.columns))
                st.error(f"Missing columns: {', '.join(missing)}")
            else:
                # Save into DB
                save_players_df_to_db(df)
                st.session_state.players_df = load_players_df_from_db()
                st.success("✅ Players uploaded and saved to database.")
                st.dataframe(st.session_state.players_df.head(20))
        except Exception as e:
            st.error(f"Error reading file: {e}")
    else:
        if st.session_state.players_df is None or st.session_state.players_df.empty:
            st.info("Upload an Excel file with columns: FULL NAME, DEPARTMENT, YEAR, PLAYER ROLE, UPLOAD YOUR PHOTO")
        else:
            st.info("Players already loaded from DB.")
            st.dataframe(st.session_state.players_df.head(10))

# 2️⃣ Team Setup
with tabs[1]:
    st.title("👥 Team Setup")
    existing_teams = st.session_state.teams if st.session_state.teams else []
    num_teams = st.number_input("Number of teams", min_value=2, max_value=12, value=max(2, len(existing_teams) or 4), step=1)

    with st.form("team_setup_form"):
        st.subheader("Enter Team Details")
        teams_input = []
        # if we have existing teams, prefill them
        for i in range(num_teams):
            col1, col2 = st.columns([2, 1])
            default_name = existing_teams[i]['Team'] if i < len(existing_teams) else ""
            default_budget = existing_teams[i]['Budget'] if i < len(existing_teams) else 1000
            name = col1.text_input(f"Team {i+1} Name", value=default_name, key=f"team_name_{i}")
            budget = col2.number_input(f"Budget (₹)", min_value=0, step=10, value=int(default_budget), key=f"budget_{i}")
            teams_input.append({"Team": name.strip(), "Budget": int(budget), "InitialBudget": int(budget), "Spent": 0, "Players": []})
        submit = st.form_submit_button("✅ Save Teams")

    if submit:
        if all(t["Team"] for t in teams_input):
            st.session_state.teams = teams_input
            # persist to DB
            save_teams_to_db(teams_input)
            st.success("✅ Teams saved successfully!")
        else:
            st.error("❌ All team names are required.")

    # display summary
    if st.session_state.teams:
        st.subheader("📋 Team Summary")
        for t in st.session_state.teams:
            st.markdown(f"### 🏏 {t['Team']}")
            init = t.get("InitialBudget", t.get("Budget", 1)) or 1
            progress_val = min(t.get("Spent", 0) / init, 1.0)
            st.progress(progress_val)
            st.write(f"💰 Budget Left: ₹{t['Budget']}  |  🛒 Spent: ₹{t['Spent']}")

# 3️⃣ Auction Panel
with tabs[2]:
    st.title("🎯 Auction Panel")
    players_df = load_players_df_from_db()
    if players_df.empty:
        st.warning("⚠️ Upload the player list first in the 'Upload Players' tab.")
    else:
        unauctioned_df = players_df[players_df['auctioned'] == 0]
        col_left, col_right = st.columns([1, 2])

        # Show currently selected player if any
        if st.session_state.current_player:
            player = st.session_state.current_player
            with col_left:
                st.subheader("Player Photo")

                pid = player.get("player_id")
                name = player.get("full_name", "")
                img_path = None

                # Try local photo
                candidate = os.path.join("photos", f"photo_{max(int(pid)-1,0)}.jpg") if pid else None
                if candidate and os.path.exists(candidate):
                    img_path = candidate
                elif os.path.exists(PLACEHOLDER):
                    img_path = PLACEHOLDER

                if img_path:
                    try:
                        with open(img_path, "rb") as f:
                            img_bytes = f.read()
                        mime = "image/jpeg" if img_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
                        b64 = base64.b64encode(img_bytes).decode()
                        img_div = (
                            f'<div style="width:450px;height:450px;display:flex;align-items:center;justify-content:center;'
                            f'background:black;overflow:hidden;margin:auto;">'
                            f'<img src="data:{mime};base64,{b64}" '
                            f'style="max-width:100%;max-height:100%;object-fit:contain;display:block;" '
                            f'alt="{name}" />'
                            f'</div>'
                        )
                    except Exception:
                        img_div = '<div style="width:450px;height:450px;background:black;color:white;display:flex;align-items:center;justify-content:center;">(no image)</div>'
                else:
                    img_div = '<div style="width:450px;height:450px;background:black;color:white;display:flex;align-items:center;justify-content:center;">(no image)</div>'

                st.markdown(img_div, unsafe_allow_html=True)
            with col_right:
                st.subheader("🔥 Player on Auction")
                st.markdown(f"<span style='font-size:2rem; font-weight:bold;'>Name: {player.get('full_name')}</span>", unsafe_allow_html=True)
                st.markdown(f"<span style='font-size:1.5rem;'>Role: {player.get('role')}</span>", unsafe_allow_html=True)
                st.markdown(f"<span style='font-size:1.5rem;'>Dept: {player.get('department')}</span>", unsafe_allow_html=True)
                st.markdown(f"<span style='font-size:1.5rem;'>Year: {player.get('year')}</span>", unsafe_allow_html=True)
                st.markdown(f"<span style='font-size:1.5rem; color:#2E86C1;'>Player ID: {player.get('player_id')}</span>", unsafe_allow_html=True)
                st.markdown("---")
                teams_list = [t['Team'] for t in st.session_state.teams] if st.session_state.teams else []
                bid_col1, bid_col2 = st.columns([2, 1])
                with bid_col1:
                    selected_team = st.selectbox("🏷️ Select Team", ["Select Team"] + teams_list)
                    sold_price = st.number_input("💰 Sold Price (₹)", min_value=0, step=5, value=20)
                with bid_col2:
                    sold_btn = st.button("✅ Mark as Sold", key="sold_btn")
                    unsold_btn = st.button("❌ Mark as Unsold", key="unsold_btn")

                if sold_btn and sold_price > 0:
                    if selected_team == "Select Team":
                        st.error("⚠️ Please select a team before selling.")
                    else:
                        # Get the team's current budget
                        team_row = next((t for t in st.session_state.teams if t['Team'] == selected_team), None)
                        if team_row:
                            current_budget = team_row['Budget']

                            if sold_price > current_budget:
                                # 🚨 Block sale and show warning popup
                                st.error(f"🚨 {selected_team} does not have enough budget! "
                                         f"Remaining: ₹{current_budget}, Tried: ₹{sold_price}")
                            else:
                                # ✅ Commit sale to DB
                                add_result_to_db(int(player['player_id']), player['full_name'],
                                                 selected_team, int(sold_price))
                                # update session_state players_df
                                st.session_state.players_df = load_players_df_from_db()
                                # update teams in session from DB
                                st.session_state.teams = load_teams_from_db()
                                st.session_state.current_player = None
                                st.session_state.start_time = None
                                st.success(f"🎉 {player['full_name']} sold to {selected_team} for ₹{sold_price}!")
                                play_sound()
                                st.rerun()

                if unsold_btn:
                    add_result_to_db(int(player['player_id']), player['full_name'], "UNSOLD", 0)
                    st.session_state.players_df = load_players_df_from_db()
                    st.session_state.current_player = None
                    st.session_state.start_time = None
                    st.info("🚫 Player marked as UNSOLD.")
                    st.rerun()


        # 🔹 Sold button fix with strict budget check
        if st.button("✅ Sold"):
            player_id = st.session_state.current_player["player_id"]
            team_name = st.session_state.current_player.get("selected_team")
            bid_price = st.session_state.current_player.get("bid_price", 0)

            if team_name is None:
                st.error("⚠️ Please select a team before selling.")
            else:
                team_budget = st.session_state.teams.loc[
                    st.session_state.teams["team_name"] == team_name, "budget"
                ].values[0]

                # 🚨 Block sale if budget insufficient
                if bid_price > team_budget:
                    st.error("🚨 INSUFFICIENT FUND: CANT AFFORD PLAYER AT THIS PRICE")
                else:
                    # Deduct safely without negatives
                    new_budget = team_budget - bid_price
                    st.session_state.teams.loc[
                        st.session_state.teams["team_name"] == team_name, "budget"
                    ] = new_budget

                    add_result_to_db(player_id, team_name, bid_price, status="Sold")
                    st.session_state.current_player = None
                    st.rerun()

        if st.button("❌ Unsold"):
            player_id = st.session_state.current_player["player_id"]
            add_result_to_db(player_id, None, 0, status="Unsold")
            st.session_state.current_player = None
            st.rerun()

        # 🔹 Pick Random Player (disabled until resolved)
        st.markdown("---")
        pick_disabled = st.session_state.current_player is not None
        if st.button("🎲 Pick Random Player", disabled=pick_disabled):
            picked = pick_unique_random_player()
            if picked is None:
                st.info("✅ All players have been auctioned.")
            else:
                st.session_state.current_player = picked
                st.session_state.start_time = time.time()
                st.rerun()

# 4️⃣ Summary & Export
with tabs[3]:
    st.title("📊 Auction Summary & Export")

    results_df = load_results_from_db()
    teams_db = load_teams_from_db()

    if results_df.empty:
        st.warning("⚠️ No auction results yet.")
    else:
        st.subheader("🏁 Results")
        st.dataframe(results_df)

        # CSV download
        csv_bytes = results_df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download Results CSV", csv_bytes, file_name="auction_results.csv")

        # Excel export combining team sheets
        excel_file = "auction_results.xlsx"
        try:
            export_results_to_excel(results_df, teams_db, filename=excel_file)
            with open(excel_file, "rb") as f:
                st.download_button("⬇️ Download Combined Excel", f.read(), file_name=excel_file)
        except Exception as e:
            st.error(f"Could not create Excel file: {e}")

    # Unsold players export: build from players table
    players_df = load_players_df_from_db()
    if not players_df.empty:
        unsold_df = players_df[players_df['auctioned'] == 1].copy()
        # Find those marked UNSOLD in results
        res_df = results_df
        if not res_df.empty:
            unsold_ids = res_df[res_df['team'] == "UNSOLD"]['player_id'].unique().tolist()
            if unsold_ids:
                unsold_players_df = players_df[players_df['player_id'].isin(unsold_ids)]
                if not unsold_players_df.empty:
                    st.markdown("---")
                    st.subheader("🚫 Unsold Players")
                    st.dataframe(unsold_players_df[['player_id', 'full_name', 'department', 'year', 'role']])
                    # download button
                    csv_u = unsold_players_df.to_csv(index=False).encode()
                    st.download_button("⬇️ Download Unsold Players (CSV)", csv_u, file_name="unsold_players.csv")

        

    # Team wise details (200x200 black frame with white text below)
    st.markdown("---")
    st.subheader("👥 Team Details")
    teams_display = load_teams_from_db()

    for t in teams_display:
        res = results_df[results_df['team'] == t['Team']] if not results_df.empty else pd.DataFrame()
        bought_count = len(res)
        left_to_buy = max(13 - bought_count, 0)

        with st.expander(f"{t['Team']} (💰 Left: ₹{t['Budget']} | 🏏 Bought: {bought_count} | 🎯 Left to Buy: {left_to_buy})"):
            if res.empty:
                st.info("No players bought yet.")
            else:
                res_local = res.copy()
                if 'full_name' in res_local.columns:
                    res_local = res_local.rename(columns={'full_name': 'full_name_res'})

                players_subset = players_df[['player_id', 'full_name', 'department', 'year', 'role', 'photo']] if not players_df.empty else pd.DataFrame()
                merged = res_local.merge(players_subset, on='player_id', how='left')

                # ---- 5x4 Grid Layout ----
                max_cols = 5
                max_rows = 4
                cards_per_page = max_cols * max_rows

                for page_start in range(0, len(merged), cards_per_page):
                    page_df = merged.iloc[page_start: page_start + cards_per_page]

                    for row_start in range(0, len(page_df), max_cols):
                        row_df = page_df.iloc[row_start: row_start + max_cols]
                        cols = st.columns(max_cols)

                        for idx, row in enumerate(row_df.itertuples()):
                            col = cols[idx]

                            # determine display name
                            name = ''
                            if hasattr(row, 'full_name_res') and pd.notna(row.full_name_res):
                                name = row.full_name_res
                            elif hasattr(row, 'full_name') and pd.notna(row.full_name):
                                name = row.full_name

                            pid = int(getattr(row, 'player_id', 0) or 0)

                            # choose image
                            img_path = None
                            photo_field = getattr(row, 'photo', None)
                            if isinstance(photo_field, str) and photo_field.strip():
                                if os.path.exists(photo_field):
                                    img_path = photo_field
                                else:
                                    candidate = os.path.join("photos", photo_field)
                                    if os.path.exists(candidate):
                                        img_path = candidate

                            if img_path is None:
                                candidate2 = os.path.join("photos", f"photo_{max(pid-1,0)}.jpg")
                                if os.path.exists(candidate2):
                                    img_path = candidate2

                            if img_path is None and os.path.exists(PLACEHOLDER):
                                img_path = PLACEHOLDER

                            # black frame 200x200
                            if img_path:
                                try:
                                    with open(img_path, "rb") as f:
                                        img_bytes = f.read()
                                    mime = "image/jpeg" if img_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
                                    b64 = base64.b64encode(img_bytes).decode()
                                    img_div = (
                                        f'<div style="width:200px;height:200px;display:flex;align-items:center;justify-content:center;'
                                        f'background:black;overflow:hidden;">'
                                        f'<img src="data:{mime};base64,{b64}" '
                                        f'style="max-width:100%;max-height:100%;object-fit:contain;display:block;" '
                                        f'alt="{name}" />'
                                        f'</div>'
                                    )
                                except Exception:
                                    img_div = '<div style="width:200px;height:200px;background:black;color:white;display:flex;align-items:center;justify-content:center;">(no image)</div>'
                            else:
                                img_div = '<div style="width:200px;height:200px;background:black;color:white;display:flex;align-items:center;justify-content:center;">(no image)</div>'

                            # white text details below
                            details_div = (
                                '<div style="padding:8px;text-align:center;font-size:0.85rem;line-height:1.3;background:black;color:white;">'
                                f'<div style="font-weight:600;margin-bottom:4px;white-space:normal;">{name}</div>'
                                f'<div style="font-size:0.8rem;">🆔 {pid} &nbsp;|&nbsp; {getattr(row, "role","")} &nbsp;|&nbsp; {getattr(row,"year","")}</div>'
                                f'<div style="margin-top:6px;font-weight:700;">₹{getattr(row, "price", 0)}</div>'
                                '</div>'
                            )

                            card_html = (
                                '<div style="width:200px;border:1px solid #333;border-radius:10px;overflow:hidden;'
                                'margin:8px auto;background:black;box-sizing:border-box;text-align:center;">'
                                f'{img_div}'
                                f'{details_div}'
                                '</div>'
                            )

                            col.markdown(card_html, unsafe_allow_html=True)

    # ------------- END --------------
