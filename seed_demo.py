"""seed_demo.py - fills the database with a demo coach + 18 players.  Run once:  python seed_demo.py
Login: demo@tactiki.com / Demo1234"""
import random

import db

db.init_db()
if db.email_exists("demo@tactiki.com"):
    print("Demo data already exists.")
    raise SystemExit
db.create_coach("Demo Coach", "demo@tactiki.com", "King Abdulaziz University", "KAU Eagles", "Demo1234")
coach = db.login("demo@tactiki.com", "Demo1234")
team = db.teams_for(coach["CoachID"])[0]
rng = random.Random(7)
bias = {"GK": dict(Defending=75, Passing=55), "DF": dict(Defending=78, Stamina=70), "MF": dict(Passing=78, Dribbling=68),
        "FW": dict(Shooting=80, Speed=76, Dribbling=72)}
names = ["Ahmed", "Khalid", "Omar", "Faisal", "Saad", "Yazeed", "Nawaf", "Fahad", "Turki", "Sultan", "Majed", "Rayan",
         "Abdullah", "Hassan", "Bandar", "Salman", "Mishal", "Talal"]
layout = ["GK"] * 2 + ["DF"] * 6 + ["MF"] * 6 + ["FW"] * 4
for name, pos in zip(names, layout):
    d = {s: rng.randint(45, 70) for s in db.SKILLS}
    d.update({k: min(95, v + rng.randint(-5, 8)) for k, v in bias[pos].items()})
    db.add_player(team["TeamID"], {"PlayerName": name, "Position": pos, "Height": rng.randint(165, 192),
                                   "Weight": rng.randint(62, 88), **d})
print("Demo data created. Login: demo@tactiki.com / Demo1234")
