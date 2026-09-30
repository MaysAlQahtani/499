"""db.py - SQLite layer. Tables follow the normalized schema in report section 4.3.2."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.environ.get("TACTIKI_DB", "tactiki.db")
SKILLS = ["Speed", "Passing", "Shooting", "Defending", "Stamina", "Dribbling"]
POSITIONS = ["GK", "DF", "MF", "FW"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS Coach (
  CoachID INTEGER PRIMARY KEY AUTOINCREMENT,
  FullName TEXT NOT NULL, Email TEXT NOT NULL UNIQUE,
  University TEXT NOT NULL, PasswordHash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS Team (
  TeamID INTEGER PRIMARY KEY AUTOINCREMENT,
  CoachID INTEGER NOT NULL REFERENCES Coach(CoachID),
  TeamName TEXT NOT NULL, University TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS Player (
  PlayerID INTEGER PRIMARY KEY AUTOINCREMENT,
  TeamID INTEGER NOT NULL REFERENCES Team(TeamID),
  PlayerName TEXT NOT NULL, Position TEXT NOT NULL,
  IsActive INTEGER NOT NULL DEFAULT 1,
  Height REAL, Weight REAL,
  Speed INTEGER NOT NULL, Passing INTEGER NOT NULL, Shooting INTEGER NOT NULL,
  Defending INTEGER NOT NULL, Stamina INTEGER NOT NULL, Dribbling INTEGER NOT NULL,
  OverallScore REAL NOT NULL);
CREATE TABLE IF NOT EXISTS Lineup (
  LineupID INTEGER PRIMARY KEY AUTOINCREMENT,
  TeamID INTEGER NOT NULL REFERENCES Team(TeamID),
  Formation TEXT NOT NULL, CreateDate TEXT NOT NULL,
  SynergyScore REAL, Reason TEXT);
CREATE TABLE IF NOT EXISTS Lineup_Player (
  LineupID INTEGER NOT NULL REFERENCES Lineup(LineupID),
  PlayerID INTEGER NOT NULL REFERENCES Player(PlayerID),
  AssignedPosition TEXT NOT NULL,
  PRIMARY KEY (LineupID, PlayerID));
CREATE TABLE IF NOT EXISTS PlayerProgress (
  ProgressID INTEGER PRIMARY KEY AUTOINCREMENT,
  PlayerID INTEGER NOT NULL REFERENCES Player(PlayerID),
  PreviousScore REAL NOT NULL, CurrentScore REAL NOT NULL,
  ProgressStatus TEXT NOT NULL, LastUpdate TEXT NOT NULL);
"""


@contextmanager
def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with db() as c:
        c.executescript(SCHEMA)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------- authentication (UC-01, UC-02) ----------------
def _hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"{salt}${h}"


def _check_pw(pw, stored):
    salt, h = stored.split("$")
    return hmac.compare_digest(_hash_pw(pw, salt).split("$")[1], h)


def email_exists(email):
    with db() as c:
        return c.execute("SELECT 1 FROM Coach WHERE lower(Email)=lower(?)", (email.strip(),)).fetchone() is not None


def validate_signup(full_name, email, university, team_name, password, confirm):
    errs = []
    if not all([full_name.strip(), email.strip(), university.strip(), team_name.strip(), password]):
        errs.append("Missing required fields: please fill in all fields.")  # A3
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
        errs.append("Invalid email format.")
    if password and not (len(password) >= 8 and re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        errs.append("Password must be at least 8 characters and contain letters and digits.")  # A2
    if password != confirm:
        errs.append("Passwords do not match.")
    if email and email_exists(email):
        errs.append("This email is already registered. Use another email or log in.")  # A1
    return errs


def create_coach(full_name, email, university, team_name, password):
    with db() as c:
        cur = c.execute(
            "INSERT INTO Coach (FullName, Email, University, PasswordHash) VALUES (?,?,?,?)",
            (full_name.strip(), email.strip().lower(), university.strip(), _hash_pw(password)))
        c.execute("INSERT INTO Team (CoachID, TeamName, University) VALUES (?,?,?)",
                  (cur.lastrowid, team_name.strip(), university.strip()))


def login(email, password):
    with db() as c:
        row = c.execute("SELECT * FROM Coach WHERE lower(Email)=lower(?)", (email.strip(),)).fetchone()
    if row and _check_pw(password, row["PasswordHash"]):
        return {k: row[k] for k in ("CoachID", "FullName", "Email", "University")}
    return None


# ---------------- teams ----------------
def teams_for(coach_id):
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM Team WHERE CoachID=? ORDER BY TeamName", (coach_id,))]


def create_team(coach_id, name, university):
    with db() as c:
        c.execute("INSERT INTO Team (CoachID, TeamName, University) VALUES (?,?,?)", (coach_id, name.strip(), university))


def delete_team(team_id):
    with db() as c:
        c.execute("DELETE FROM Lineup_Player WHERE LineupID IN (SELECT LineupID FROM Lineup WHERE TeamID=?)", (team_id,))
        c.execute("DELETE FROM Lineup WHERE TeamID=?", (team_id,))
        c.execute("DELETE FROM PlayerProgress WHERE PlayerID IN (SELECT PlayerID FROM Player WHERE TeamID=?)", (team_id,))
        c.execute("DELETE FROM Player WHERE TeamID=?", (team_id,))
        c.execute("DELETE FROM Team WHERE TeamID=?", (team_id,))


# ---------------- players (UC-03 .. UC-07) ----------------
def _num(v):
    try:
        if v is None or v == "" or (isinstance(v, float) and v != v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def clean_player(d):
    errs, out = [], {}
    name = str(d.get("PlayerName") or "").strip()
    if not name or name.lower() == "nan":
        errs.append("Player name is required")
    out["PlayerName"] = name
    pos = d.get("Position")
    if pos not in POSITIONS:
        errs.append(f"Position must be one of {', '.join(POSITIONS)}")
    out["Position"] = pos
    for s in SKILLS:
        v = _num(d.get(s))
        if v is None or not (1 <= v <= 100):
            errs.append(f"{s} must be between 1 and 100")
        else:
            out[s] = int(round(v))
    out["Height"], out["Weight"] = _num(d.get("Height")), _num(d.get("Weight"))
    out["IsActive"] = int(d.get("IsActive", 1))
    if not errs:
        out["OverallScore"] = round(sum(out[s] for s in SKILLS) / len(SKILLS), 1)
    return out, errs


def _status(prev, curr):
    diff = curr - prev
    return "Improved" if diff > 0.4 else "Declined" if diff < -0.4 else "Stable"


def _dup(c, team_id, name, exclude_id=None):
    q = "SELECT 1 FROM Player WHERE TeamID=? AND lower(PlayerName)=lower(?)"
    args = [team_id, name]
    if exclude_id:
        q += " AND PlayerID<>?"
        args.append(exclude_id)
    return c.execute(q, args).fetchone() is not None


def add_player(team_id, d):
    """Returns (status, message) where status is 'added' | 'duplicate' | 'error'."""
    data, errs = clean_player(d)
    if errs:
        return "error", "; ".join(errs)
    try:
        with db() as c:
            if _dup(c, team_id, data["PlayerName"]):
                return "duplicate", f"{data['PlayerName']} already exists in this team"
            cur = c.execute(
                "INSERT INTO Player (TeamID, PlayerName, Position, IsActive, Height, Weight, "
                "Speed, Passing, Shooting, Defending, Stamina, Dribbling, OverallScore) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (team_id, data["PlayerName"], data["Position"], data["IsActive"], data["Height"], data["Weight"],
                 *[data[s] for s in SKILLS], data["OverallScore"]))
            c.execute("INSERT INTO PlayerProgress (PlayerID, PreviousScore, CurrentScore, ProgressStatus, LastUpdate) "
                      "VALUES (?,?,?,?,?)", (cur.lastrowid, data["OverallScore"], data["OverallScore"], "Stable", _now()))
        return "added", data["PlayerName"]
    except sqlite3.Error as e:
        return "error", f"Database error: {e}"


def update_player(player_id, team_id, d):
    data, errs = clean_player(d)
    if errs:
        return "error", "; ".join(errs)
    try:
        with db() as c:
            old = c.execute("SELECT OverallScore FROM Player WHERE PlayerID=?", (player_id,)).fetchone()
            if not old:
                return "error", "Player record not found"
            if _dup(c, team_id, data["PlayerName"], exclude_id=player_id):
                return "duplicate", f"Another player named {data['PlayerName']} already exists"
            c.execute("UPDATE Player SET PlayerName=?, Position=?, IsActive=?, Height=?, Weight=?, Speed=?, Passing=?, "
                      "Shooting=?, Defending=?, Stamina=?, Dribbling=?, OverallScore=? WHERE PlayerID=?",
                      (data["PlayerName"], data["Position"], data["IsActive"], data["Height"], data["Weight"],
                       *[data[s] for s in SKILLS], data["OverallScore"], player_id))
            if data["OverallScore"] != old["OverallScore"]:
                c.execute("INSERT INTO PlayerProgress (PlayerID, PreviousScore, CurrentScore, ProgressStatus, LastUpdate) "
                          "VALUES (?,?,?,?,?)", (player_id, old["OverallScore"], data["OverallScore"],
                                                 _status(old["OverallScore"], data["OverallScore"]), _now()))
        return "updated", data["PlayerName"]
    except sqlite3.Error as e:
        return "error", f"Database error: {e}"


def delete_player(player_id):
    """Deactivates when the player has lineup history, otherwise deletes (UC-07)."""
    with db() as c:
        used = c.execute("SELECT 1 FROM Lineup_Player WHERE PlayerID=? LIMIT 1", (player_id,)).fetchone()
        if used:
            c.execute("UPDATE Player SET IsActive=0 WHERE PlayerID=?", (player_id,))
            return "deactivated"
        c.execute("DELETE FROM PlayerProgress WHERE PlayerID=?", (player_id,))
        c.execute("DELETE FROM Player WHERE PlayerID=?", (player_id,))
        return "deleted"


def get_players(team_id, active_only=False):
    q = "SELECT * FROM Player WHERE TeamID=?" + (" AND IsActive=1" if active_only else "") + " ORDER BY PlayerName"
    with db() as c:
        return [dict(r) for r in c.execute(q, (team_id,))]


def progress_history(player_id):
    with db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM PlayerProgress WHERE PlayerID=? ORDER BY ProgressID", (player_id,))]


# ---------------- lineups ----------------
def save_lineup(team_id, formation, assignments, score, reason):
    """assignments: list of (slot_name, player_id)."""
    with db() as c:
        cur = c.execute("INSERT INTO Lineup (TeamID, Formation, CreateDate, SynergyScore, Reason) VALUES (?,?,?,?,?)",
                        (team_id, formation, _now(), score, reason))
        c.executemany("INSERT INTO Lineup_Player (LineupID, PlayerID, AssignedPosition) VALUES (?,?,?)",
                      [(cur.lastrowid, pid, slot) for slot, pid in assignments])
        return cur.lastrowid


def list_lineups(team_id):
    with db() as c:
        out = []
        for l in c.execute("SELECT * FROM Lineup WHERE TeamID=? ORDER BY LineupID DESC", (team_id,)).fetchall():
            players = [dict(r) for r in c.execute(
                "SELECT lp.AssignedPosition, p.PlayerName, p.Position, p.OverallScore FROM Lineup_Player lp "
                "JOIN Player p ON p.PlayerID=lp.PlayerID WHERE lp.LineupID=?", (l["LineupID"],))]
            out.append({**dict(l), "players": players})
        return out
