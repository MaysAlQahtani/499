"""ui_pages.py - every screen of Tactiki (one function per use case)."""
import time

import pandas as pd
import streamlit as st

import ai
import charts
import db
from db import POSITIONS, SKILLS


def _label(p):
    return f"{p['PlayerName']} ({p['Position']}, {p['OverallScore']})"


# ======================= AUTH (UC-01 / UC-02) =======================
def auth_screen():
    st.title("⚽ Tactiki")
    st.caption("AI-powered decision support for university football coaches")
    tab_login, tab_signup = st.tabs(["Login", "Sign Up"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            pw = st.text_input("Password", type="password")
            go = st.form_submit_button("Login", type="primary")
        if go:
            if not email or not pw:
                st.error("Please enter your email and password.")
            else:
                coach = db.login(email, pw)
                if coach:
                    st.session_state.coach = coach
                    st.rerun()
                elif db.email_exists(email):
                    st.error("Invalid email or password.")
                else:
                    st.warning("No account found with this email. Please sign up first.")

    with tab_signup:
        with st.form("signup_form"):
            name = st.text_input("Full name")
            email = st.text_input("Email", key="su_email")
            uni = st.text_input("University")
            team = st.text_input("Team name")
            pw = st.text_input("Password", type="password", key="su_pw")
            confirm = st.text_input("Confirm password", type="password")
            go = st.form_submit_button("Create account", type="primary")
        if go:
            errs = db.validate_signup(name, email, uni, team, pw, confirm)
            if errs:
                for e in errs:
                    st.error(e)
            else:
                db.create_coach(name, email, uni, team, pw)
                st.success("Account created successfully. You can now log in from the Login tab.")


# ======================= DASHBOARD =======================
def dashboard(team):
    st.header(f"Dashboard - {team['TeamName']}")
    players = db.get_players(team["TeamID"])
    active = [p for p in players if p["IsActive"]]
    if not players:
        st.info("No players yet. Go to **Squad Input** to add your squad.")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Players", len(players))
    c2.metric("Active", len(active))
    c3.metric("Average overall", round(sum(p["OverallScore"] for p in active) / max(1, len(active)), 1))
    c4.metric("Saved lineups", len(db.list_lineups(team["TeamID"])))
    left, right = st.columns(2)
    with left:
        st.subheader("Top players")
        top = sorted(active, key=lambda p: p["OverallScore"], reverse=True)[:5]
        st.dataframe(pd.DataFrame(top)[["PlayerName", "Position", "OverallScore"]], hide_index=True, use_container_width=True)
    with right:
        st.subheader("Team average skills")
        avg = {s: sum(p[s] for p in active) / max(1, len(active)) for s in SKILLS}
        st.plotly_chart(charts.radar([("Team average", avg)]), use_container_width=True)


# ======================= UPLOAD PLAYERS DATA (UC-03) =======================
def squad_input(team):
    st.header("Squad Input")
    st.caption("Add rows with the + button, fill the skill ratings (1-100), then submit. Or load a CSV first.")
    cols = ["PlayerName", "Position", "Height", "Weight"] + SKILLS
    up = st.file_uploader("Optional: load players from a CSV file", type="csv")
    base = pd.DataFrame({c: pd.Series(dtype="object" if c in ("PlayerName", "Position") else "float") for c in cols})
    if up is not None:
        try:
            base = pd.read_csv(up)
            missing = [c for c in cols if c not in base.columns]
            if missing:
                st.error(f"CSV is missing columns: {', '.join(missing)}")
                base = base.reindex(columns=cols)
        except Exception as e:
            st.error(f"Could not read the CSV: {e}")
    config = {"Position": st.column_config.SelectboxColumn("Position", options=POSITIONS, required=True)}
    for s in SKILLS:
        config[s] = st.column_config.NumberColumn(s, min_value=1, max_value=100, step=1)
    edited = st.data_editor(base[cols], num_rows="dynamic", use_container_width=True, column_config=config,
                            key=f"squad_editor_{up.name if up else 'manual'}")
    if st.button("Submit players", type="primary"):
        added = dups = errs = 0
        issues = []
        for i, row in edited.iterrows():
            rec = row.to_dict()
            if all(pd.isna(v) or v == "" for v in rec.values()):
                continue
            status, msg = db.add_player(team["TeamID"], rec)
            if status == "added":
                added += 1
            elif status == "duplicate":
                dups += 1
                issues.append({"Row": i + 1, "Type": "Duplicate", "Details": msg})
            else:
                errs += 1
                issues.append({"Row": i + 1, "Type": "Error", "Details": msg})
        a, b, c = st.columns(3)
        a.metric("Added", added)
        b.metric("Duplicates", dups)
        c.metric("Errors", errs)
        if issues:
            st.dataframe(pd.DataFrame(issues), hide_index=True, use_container_width=True)
        if added + dups + errs == 0:
            st.warning("No player rows to submit.")


# ======================= MANAGE PLAYERS (UC-04 .. UC-07) =======================
def _player_form(key, d=None, label="Save", show_active=False):
    d = d or {}
    with st.form(key):
        name = st.text_input("Player name", d.get("PlayerName", ""), key=f"{key}_name")
        c1, c2, c3 = st.columns(3)
        pos = c1.selectbox("Position", POSITIONS, index=POSITIONS.index(d.get("Position", "MF")), key=f"{key}_pos")
        h = c2.number_input("Height (cm)", 0.0, 250.0, float(d.get("Height") or 0), key=f"{key}_h")
        w = c3.number_input("Weight (kg)", 0.0, 200.0, float(d.get("Weight") or 0), key=f"{key}_w")
        cs = st.columns(3)
        skills = {s: cs[i % 3].slider(s, 1, 100, int(d.get(s, 50)), key=f"{key}_{s}") for i, s in enumerate(SKILLS)}
        active = st.checkbox("Active", bool(d.get("IsActive", 1)), key=f"{key}_act") if show_active else True
        ok = st.form_submit_button(label, type="primary")
    return ok, {"PlayerName": name, "Position": pos, "Height": h or None, "Weight": w or None,
                "IsActive": int(active), **skills}


def manage_players(team):
    st.header("Manage Players Data")
    show_all = st.toggle("Show inactive players", value=False)
    players = db.get_players(team["TeamID"], active_only=not show_all)
    if players:
        df = pd.DataFrame(players).drop(columns=["TeamID"])
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.info("No players in this team yet. Use **Add New Player** below.")
    t_add, t_upd, t_del = st.tabs(["Add New Player", "Update Player", "Delete Player"])

    with t_add:
        ok, data = _player_form("add_form", label="Add player")
        if ok:
            status, msg = db.add_player(team["TeamID"], data)
            if status == "added":
                st.success(f"{msg} was added successfully.")
                st.rerun() if False else None
            elif status == "duplicate":
                st.warning(f"Duplicate player: {msg}.")
            else:
                st.error(msg)

    all_players = db.get_players(team["TeamID"])
    with t_upd:
        if not all_players:
            st.info("Nothing to update yet.")
        else:
            pid = st.selectbox("Select player", [p["PlayerID"] for p in all_players], key="upd_sel",
                               format_func=lambda i: _label(next(p for p in all_players if p["PlayerID"] == i)))
            cur = next(p for p in all_players if p["PlayerID"] == pid)
            ok, data = _player_form(f"upd_form_{pid}", cur, "Save changes", show_active=True)
            if ok:
                status, msg = db.update_player(pid, team["TeamID"], data)
                if status == "updated":
                    st.success(f"{msg} was updated successfully.")
                elif status == "duplicate":
                    st.warning(msg)
                else:
                    st.error(msg)

    with t_del:
        if not all_players:
            st.info("Nothing to delete yet.")
        else:
            pid = st.selectbox("Select player to delete", [p["PlayerID"] for p in all_players], key="del_sel",
                               format_func=lambda i: _label(next(p for p in all_players if p["PlayerID"] == i)))
            st.warning("Players used in a saved lineup are deactivated instead of deleted, to keep the history.")
            sure = st.checkbox("I confirm that I want to delete this player", key=f"del_ok_{pid}")
            if st.button("Delete player", disabled=not sure):
                res = db.delete_player(pid)
                st.success("Player deleted." if res == "deleted" else "Player has lineup history, so they were marked inactive.")
                time.sleep(0.8)
                st.rerun()


# ======================= LINEUP (UC-08 / UC-09) =======================
def lineup(team):
    st.header("Lineup")
    players = db.get_players(team["TeamID"], active_only=True)
    if not players:
        st.info("No active players found. Add or update player data first.")
        return
    ids = [p["PlayerID"] for p in players]
    by_id = {p["PlayerID"]: p for p in players}
    chosen = st.multiselect("Available players", ids, default=ids, key=f"lineup_sel_{team['TeamID']}",
                            format_func=lambda i: _label(by_id[i]))
    formation = st.selectbox("Formation", list(ai.FORMATIONS), index=None, placeholder="Select a formation")
    if st.button("Generate optimized lineup", type="primary"):
        if not formation:
            st.error("Please select a formation.")
        elif len(chosen) < ai.MIN_PLAYERS:
            st.error(f"Minimum players not met: select at least {ai.MIN_PLAYERS} (you selected {len(chosen)}).")
        else:
            t0 = time.time()
            try:
                with st.spinner("Running the Genetic Algorithm..."):
                    res = ai.generate_lineup([by_id[i] for i in chosen], formation)
                st.session_state.last_lineup = {"team_id": team["TeamID"], "formation": formation, "res": res,
                                                "secs": time.time() - t0}
            except Exception as e:
                st.error(f"AI model error: {e}. Please try again.")

    last = st.session_state.get("last_lineup")
    if last and last["team_id"] == team["TeamID"]:
        res = last["res"]
        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("Synergy score", f"{res['synergy']} / 100")
        m2.metric("Formation", last["formation"])
        m3.metric("Generated in", f"{last['secs']:.2f} s")
        st.plotly_chart(charts.pitch(res["assignments"]), use_container_width=True)
        st.info(res["reason"])
        table = pd.DataFrame([{"Slot": a["slot"], "Player": a["player"]["PlayerName"], "Position": a["player"]["Position"],
                               "Overall": a["player"]["OverallScore"], "Role fit": round(a["fit"])} for a in res["assignments"]])
        st.dataframe(table, hide_index=True, use_container_width=True)
        if res["bench"]:
            st.caption("Bench: " + ", ".join(p["PlayerName"] for p in res["bench"]))
        if st.button("Save this lineup"):
            try:
                db.save_lineup(team["TeamID"], last["formation"], [(a["slot"], a["player"]["PlayerID"]) for a in res["assignments"]],
                               res["synergy"], res["reason"])
                st.success("Lineup saved.")
            except Exception as e:
                st.error(f"Could not save the lineup: {e}")

    saved = db.list_lineups(team["TeamID"])
    if saved:
        st.divider()
        st.subheader("Saved lineups")
        for l in saved:
            with st.expander(f"{l['CreateDate']} - {l['Formation']} - Synergy {l['SynergyScore']}"):
                st.write(l["Reason"])
                st.dataframe(pd.DataFrame(l["players"]), hide_index=True, use_container_width=True)


# ======================= SUBSTITUTES (UC-10) =======================
def substitutes(team):
    st.header("Find Substitute Player")
    players = db.get_players(team["TeamID"], active_only=True)
    if len(players) < 2:
        st.info("You need at least two active players to find a substitute.")
        return
    by_id = {p["PlayerID"]: p for p in players}
    tid = st.selectbox("Unavailable player", list(by_id), format_func=lambda i: _label(by_id[i]))
    n = st.slider("Number of suggestions", 1, 5, 3)
    if st.button("Find substitute", type="primary"):
        try:
            recs = ai.recommend_substitutes(by_id[tid], players, n)
            st.session_state.sub_result = {"target": tid, "recs": recs}
        except Exception as e:
            st.error(f"AI model error: {e}. Please retry.")
    res = st.session_state.get("sub_result")
    if not res or res["target"] not in by_id:
        return
    target = by_id[res["target"]]
    st.divider()
    if not res["recs"]:
        st.warning("No substitute available.")
        return
    for i, r in enumerate(res["recs"], 1):
        p = r["player"]
        with st.container(border=True):
            a, b = st.columns([3, 1])
            a.markdown(f"**{i}. {p['PlayerName']}** - {p['Position']} - Overall {p['OverallScore']}")
            b.metric("Similarity", f"{r['similarity'] * 100:.1f}%")
            st.caption(r["reason"])
    others = [i for i in by_id if i != target["PlayerID"]]
    top_id = res["recs"][0]["player"]["PlayerID"]
    pick = st.selectbox("Compare with (you can also pick any player manually)", others, index=others.index(top_id),
                        format_func=lambda i: _label(by_id[i]))
    st.caption(f"Cosine similarity with {target['PlayerName']}: {ai.similarity(target, by_id[pick]) * 100:.1f}%")
    st.plotly_chart(charts.radar([(target["PlayerName"], target), (by_id[pick]["PlayerName"], by_id[pick])]),
                    use_container_width=True)


# ======================= PROGRESS (UC-11) =======================
def progress(team):
    st.header("Player Progress")
    players = db.get_players(team["TeamID"], active_only=True)
    if not players:
        st.info("No active players found.")
        return
    by_id = {p["PlayerID"]: p for p in players}
    pid = st.selectbox("Select player", list(by_id), format_func=lambda i: _label(by_id[i]))
    p = by_id[pid]
    hist = db.progress_history(pid)
    if not hist:
        st.info("No progress history available for this player.")
        return
    last = hist[-1]
    a, b, c = st.columns(3)
    a.metric("Current score", last["CurrentScore"], round(last["CurrentScore"] - last["PreviousScore"], 1))
    b.metric("Previous score", last["PreviousScore"])
    c.metric("Status", last["ProgressStatus"])
    l, r = st.columns(2)
    l.plotly_chart(charts.trend(hist, p["PlayerName"]), use_container_width=True)
    r.plotly_chart(charts.radar([(p["PlayerName"], p)]), use_container_width=True)
    st.caption("Tip: update the player's ratings in Manage Players (monthly / after each match) to add a new progress point.")


# ======================= POSITION MAP (K-Means) =======================
def position_map(team):
    st.header("Position Map")
    players = db.get_players(team["TeamID"], active_only=True)
    df = ai.classify_positions(players)
    if df is None:
        st.info("Add at least three active outfield players to see the K-Means position map.")
        return
    st.plotly_chart(charts.position_map(df), use_container_width=True)
    diff = df[df["Current position"] != df["Suggested role"]]
    st.subheader("Players the AI would place differently")
    if diff.empty:
        st.success("All players match the suggested role.")
    else:
        st.dataframe(diff[["Player", "Current position", "Suggested role"]], hide_index=True, use_container_width=True)
    st.caption("Goalkeepers are excluded because the six skill ratings do not measure goalkeeping.")
