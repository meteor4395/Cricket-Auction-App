import streamlit as st
import pandas as pd

st.sidebar.markdown("[🌐 GitHub](https://github.com/deveshc20)  |  🧑‍💻 Created by **DC**")

st.set_page_config(page_title="Cricket Auction App", layout="wide")

# ---------- SIDEBAR NAVIGATION ----------
st.sidebar.title("🏏 Cricket Auction System")
page = st.sidebar.radio("Go to", ["1️⃣ Upload Players", "2️⃣ Team Setup", "3️⃣ Auction Panel", "4️⃣ Summary & Export"])

# ---------- SESSION INIT ----------
if 'player_index' not in st.session_state:
    st.session_state['player_index'] = 0
if 'teams' not in st.session_state:
    st.session_state['teams'] = []
if 'auction_results' not in st.session_state:
    st.session_state['auction_results'] = []
if 'players_df' not in st.session_state:
    st.session_state['players_df'] = None
if 'current_bid' not in st.session_state:
    st.session_state['current_bid'] = 20
if 'current_bid_team' not in st.session_state:
    st.session_state['current_bid_team'] = None

# ---------- 1️⃣ UPLOAD PLAYERS ----------
if page == "1️⃣ Upload Players":
    st.title("📥 Upload Player List")

    uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx"])
    required_columns = ["Player No", "Player Name", "Role"]

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file)

            if all(col in df.columns for col in required_columns):
                st.session_state['players_df'] = df.copy()
                st.success("✅ File uploaded successfully!")
                st.dataframe(df.head(10))

                if st.button("🔀 Shuffle Players"):
                    st.session_state['players_df'] = df.sample(frac=1).reset_index(drop=True)
                    st.session_state['player_index'] = 0
                    st.success("✅ Player list shuffled!")
                    st.rerun()
            else:
                missing = list(set(required_columns) - set(df.columns))
                st.error(f"Missing columns: {', '.join(missing)}")

        except Exception as e:
            st.error(f"Error reading file: {e}")
    else:
        st.info("Upload an Excel file with columns: Player No, Player Name, Role")

# ---------- 2️⃣ TEAM SETUP ----------
elif page == "2️⃣ Team Setup":
    st.title("👥 Team Setup")

    num_teams = st.number_input("Number of teams", min_value=2, max_value=12, value=4, step=1, key="num_teams")

    with st.form("team_setup_form"):
        st.subheader("Enter Team Details")
        teams = []
        for i in range(num_teams):
            col1, col2 = st.columns([2, 1])
            name = col1.text_input(f"Team {i+1} Name", key=f"team_name_{i}")
            budget = col2.number_input(f"Budget (₹)", min_value=100, step=10, value=900, key=f"budget_{i}")
            teams.append({'Team': name.strip(), 'Budget': budget, 'Spent': 0, 'Players': []})
        submit = st.form_submit_button("✅ Save Teams")

    if submit:
        if all(team['Team'] for team in teams):
            st.session_state['teams'] = teams
            st.success("✅ Teams saved successfully!")
        else:
            st.error("❌ All team names are required.")

    if st.session_state['teams']:
        st.subheader("📋 Team Summary")
        st.dataframe(pd.DataFrame(st.session_state['teams']).drop(columns=['Players']))

# ---------- 3️⃣ AUCTION PANEL ----------
elif page == "3️⃣ Auction Panel":
    st.title("🎯 Live Auction Panel")

    if st.session_state['players_df'] is None or not st.session_state['teams']:
        st.warning("⚠️ Please upload player list and set up teams first.")
        st.stop()

    players = st.session_state['players_df']
    teams = st.session_state['teams']
    i = st.session_state['player_index']

    if i >= len(players):
        st.success("✅ All players have been auctioned.")
        if st.button("🔁 Restart Auction"):
            st.session_state['player_index'] = 0
            st.session_state['auction_results'] = []
            for team in st.session_state['teams']:
                team['Players'] = []
                team['Spent'] = 0
                team['Budget'] = 900
            st.rerun()
        st.stop()

    player = players.iloc[i]
    base_price = 20
    step_price = 10

    st.subheader(f"👤 Player {player['Player No']}: {player['Player Name']}")
    st.markdown(f"**Role:** {player['Role']}  \n**Base Price:** ₹{base_price}")

    st.markdown("---")
    st.subheader("🎯 Live Bidding")

    col1, col2 = st.columns([2, 1])
    with col1:
        team_names = [team['Team'] for team in teams]
        selected_team = st.selectbox("🏆 Select Bidding Team", team_names, key="bidding_team")

    with col2:
        if st.button("🔺 Bid +₹10", key="bid_increment"):
            selected = next(t for t in teams if t['Team'] == selected_team)
            new_bid = st.session_state['current_bid'] + step_price

            if selected['Budget'] >= new_bid:
                st.session_state['current_bid'] = new_bid
                st.session_state['current_bid_team'] = selected_team
                st.success(f"{selected_team} placed a bid of ₹{new_bid}")
            else:
                st.error(f"{selected_team} doesn't have enough budget (₹{selected['Budget']})")

    st.info(f"🟢 Current Bid: ₹{st.session_state['current_bid']} by {st.session_state['current_bid_team'] or 'None'}")

    st.markdown("---")
    st.subheader("🏁 Finalize or Skip")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("✅ Confirm Sale", key="confirm_auction"):
            if st.session_state['current_bid_team'] is None:
                sold_to = "Unsold"
                final_price = 0
                st.info(f"{player['Player Name']} marked as Unsold.")
            else:
                sold_to = st.session_state['current_bid_team']
                final_price = st.session_state['current_bid']

                for team in st.session_state['teams']:
                    if team['Team'] == sold_to:
                        team['Players'].append(dict(player))
                        team['Spent'] += final_price
                        team['Budget'] -= final_price
                        st.success(f"{player['Player Name']} sold to {sold_to} for ₹{final_price}")

            st.session_state['auction_results'].append({
                "Player No": player['Player No'],
                "Player Name": player['Player Name'],
                "Role": player['Role'],
                "Base Price": base_price,
                "Sold To": sold_to,
                "Sold Price": final_price
            })

            st.session_state['player_index'] += 1
            st.session_state['current_bid'] = base_price
            st.session_state['current_bid_team'] = None
            st.rerun()

    with col2:
        if st.button("⏭️ Skip Player", key="skip_player"):
            st.session_state['auction_results'].append({
                "Player No": player['Player No'],
                "Player Name": player['Player Name'],
                "Role": player['Role'],
                "Base Price": base_price,
                "Sold To": "Skipped",
                "Sold Price": 0
            })

            st.session_state['player_index'] += 1
            st.session_state['current_bid'] = base_price
            st.session_state['current_bid_team'] = None
            st.rerun()

    st.markdown("---")
    st.subheader("📊 Live Team Leaderboard")

    leaderboard = []
    for team in st.session_state['teams']:
        leaderboard.append({
            "Team": team['Team'],
            "Spent": team['Spent'],
            "Remaining Budget": team['Budget'],
            "Players Bought": len(team['Players'])
        })

    leaderboard_df = pd.DataFrame(leaderboard).sort_values(by="Spent", ascending=False)
    st.dataframe(leaderboard_df, use_container_width=True)

# ---------- 4️⃣ SUMMARY ----------
elif page == "4️⃣ Summary & Export":
    st.title("📊 Auction Summary")

    if not st.session_state['auction_results']:
        st.warning("⚠️ No results yet.")
        st.stop()

    df = pd.DataFrame(st.session_state['auction_results'])
    st.subheader("📝 Auction Results")
    st.dataframe(df)

    st.download_button(
        label="⬇️ Download CSV",
        data=df.to_csv(index=False),
        file_name="auction_results.csv",
        mime="text/csv"
    )

    st.subheader("👥 Team Details")
    for team in st.session_state['teams']:
        with st.expander(f"{team['Team']} (💰 Left: ₹{team['Budget']:,})"):
            if team['Players']:
                st.dataframe(pd.DataFrame(team['Players'])[['Player No', 'Player Name', 'Role']])
            else:
                st.info("No players bought yet.")

    st.markdown("---")
    col1, col2 = st.columns(2)
    if col1.button("🔁 Restart Auction"):
        st.session_state['player_index'] = 0
        st.session_state['auction_results'] = []
        for team in st.session_state['teams']:
            team['Players'] = []
            team['Spent'] = 0
            team['Budget'] = 900
        st.success("Auction restarted.")
        st.rerun()

    if col2.button("❌ Clear All Data"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.success("All session data cleared.")
        st.rerun()
