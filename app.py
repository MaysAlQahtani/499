"""app.py - entry point.  Run with:  streamlit run app.py"""
import streamlit as st

import db
import ui_pages as pg

st.set_page_config(page_title="Tactiki", page_icon="⚽", layout="wide")
db.init_db()

if "coach" not in st.session_state:
    pg.auth_screen()
    st.stop()

coach = st.session_state.coach
teams = db.teams_for(coach["CoachID"])

with st.sidebar:
    st.markdown(f"### ⚽ Tactiki\n**{coach['FullName']}**  \n{coach['University']}")
    team = None
    if teams:
        ids = [t["TeamID"] for t in teams]
        if st.session_state.get("team_id") not in ids:
            st.session_state.team_id = ids[0]
        tid = st.selectbox("Team", ids, key="team_id", format_func=lambda i: next(t["TeamName"] for t in teams if t["TeamID"] == i))
        team = next(t for t in teams if t["TeamID"] == tid)
    else:
        st.warning("Create a team to start.")
    with st.expander("Create team"):
        with st.form("new_team", clear_on_submit=True):
            name = st.text_input("Team name")
            if st.form_submit_button("Create") and name.strip():
                db.create_team(coach["CoachID"], name, coach["University"])
                st.rerun()
    if team:
        with st.expander("Delete team"):
            sure = st.checkbox("I understand this deletes all its players and lineups")
            if st.button("Delete team", disabled=not sure):
                db.delete_team(team["TeamID"])
                st.rerun()
    st.divider()
    PAGES = {"Dashboard": pg.dashboard, "Squad Input": pg.squad_input, "Manage Players": pg.manage_players,
             "Lineup": pg.lineup, "Substitutes": pg.substitutes, "Player Progress": pg.progress,
             "Position Map": pg.position_map}
    choice = st.radio("Navigation", list(PAGES), label_visibility="collapsed")
    st.divider()
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

if team:
    PAGES[choice](team)
else:
    st.info("Create your first team from the sidebar.")
