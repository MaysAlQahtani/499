"""ai.py - stand-in AI layer (Cosine Similarity, Genetic Algorithm, K-Means).
Your teammate's real modules can replace these three public functions without touching the UI:
    recommend_substitutes(target, candidates, top_n)
    generate_lineup(players, formation)
    classify_positions(players)
"""
import random

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics.pairwise import cosine_similarity

from db import SKILLS

MIN_PLAYERS = 11
# weight of each skill (Speed, Passing, Shooting, Defending, Stamina, Dribbling) per role
ROLE_WEIGHTS = {
    "GK": [.10, .20, .00, .60, .10, .00],
    "DF": [.15, .15, .00, .50, .20, .00],
    "MF": [.10, .35, .10, .10, .20, .15],
    "FW": [.25, .05, .40, .00, .10, .20],
}
FORMATIONS = {
    "4-3-3": [("GK", ["GK"]), ("DF", ["LB", "LCB", "RCB", "RB"]), ("MF", ["LCM", "CM", "RCM"]), ("FW", ["LW", "ST", "RW"])],
    "4-4-2": [("GK", ["GK"]), ("DF", ["LB", "LCB", "RCB", "RB"]), ("MF", ["LM", "LCM", "RCM", "RM"]), ("FW", ["LS", "RS"])],
    "3-5-2": [("GK", ["GK"]), ("DF", ["LCB", "CB", "RCB"]), ("MF", ["LWB", "LCM", "CM", "RCM", "RWB"]), ("FW", ["LS", "RS"])],
    "4-2-3-1": [("GK", ["GK"]), ("DF", ["LB", "LCB", "RCB", "RB"]), ("MF", ["LDM", "RDM"]),
                ("MF", ["LAM", "CAM", "RAM"]), ("FW", ["ST"])],
}


def vec(p):
    return np.array([p[s] for s in SKILLS], dtype=float)


def role_fit(p, role):
    return float(vec(p) @ np.array(ROLE_WEIGHTS[role]))


def slots(formation):
    rows, out = FORMATIONS[formation], []
    for i, (role, names) in enumerate(rows):
        y = 8 + i * (80 / (len(rows) - 1))
        for j, nm in enumerate(names):
            out.append({"slot": nm, "role": role, "x": 100 * (j + 1) / (len(names) + 1), "y": y})
    return out


# ---------------- Cosine Similarity (UC-10) ----------------
def similarity(a, b):
    return float(cosine_similarity([vec(a)], [vec(b)])[0][0])


def _sub_reason(t, c):
    diff = vec(c) - vec(t)
    closest = [SKILLS[i] for i in np.argsort(np.abs(diff))[:2]]
    gap = int(np.argmax(np.abs(diff)))
    direction = "higher" if diff[gap] > 0 else "lower"
    text = f"Very close in {closest[0]} and {closest[1]}; biggest difference is {SKILLS[gap]} ({abs(diff[gap]):.0f} points {direction})."
    if c["Position"] == t["Position"]:
        text += " Plays the same position."
    return text


def recommend_substitutes(target, candidates, top_n=3):
    cands = [c for c in candidates if c["PlayerID"] != target["PlayerID"]]
    if not cands:
        return []
    sims = cosine_similarity([vec(target)], [vec(c) for c in cands])[0]
    return [{"player": cands[i], "similarity": float(sims[i]), "reason": _sub_reason(target, cands[i])}
            for i in np.argsort(-sims)[:top_n]]


# ---------------- Genetic Algorithm (UC-09) ----------------
def _score(team, sl):
    fits, matches, gk_bad = [], 0, 0
    for p, s in zip(team, sl):
        fits.append(role_fit(p, s["role"]))
        if p["Position"] == s["role"]:
            matches += 1
        elif s["role"] == "GK":
            gk_bad += 1
    atk = np.mean([(p["Shooting"] + p["Dribbling"] + p["Passing"]) / 3 for p, s in zip(team, sl) if s["role"] in ("MF", "FW")])
    dfn = np.mean([p["Defending"] for p, s in zip(team, sl) if s["role"] in ("GK", "DF")])
    avg = float(np.mean(fits))
    synergy = float(np.clip(0.7 * avg + 0.3 * (100 - min(100, 2 * abs(atk - dfn))), 0, 100))
    return {"fitness": synergy + 1.5 * matches - 15 * gk_bad, "synergy": synergy, "atk": float(atk),
            "dfn": float(dfn), "matches": matches, "fits": fits}


def generate_lineup(players, formation, pop_size=80, generations=100, seed=42):
    if len(players) < MIN_PLAYERS:
        raise ValueError(f"At least {MIN_PLAYERS} players are required")
    rng, sl, n = random.Random(seed), slots(formation), len(players)

    def fit(ch):
        return _score([players[i] for i in ch], sl)["fitness"]

    pop = [rng.sample(range(n), 11) for _ in range(pop_size)]
    for _ in range(generations):
        fits = [fit(c) for c in pop]
        order = sorted(range(pop_size), key=lambda i: fits[i], reverse=True)
        nxt = [pop[i] for i in order[:2]]
        while len(nxt) < pop_size:
            a, b = (pop[max(rng.sample(range(pop_size), 3), key=lambda i: fits[i])] for _ in range(2))
            child = a[:rng.randint(1, 10)]
            child += [g for g in b if g not in child][:11 - len(child)]
            while len(child) < 11:
                g = rng.randrange(n)
                if g not in child:
                    child.append(g)
            if rng.random() < 0.3:
                i, j = rng.sample(range(11), 2)
                child[i], child[j] = child[j], child[i]
            if n > 11 and rng.random() < 0.3:
                g = rng.choice([x for x in range(n) if x not in child])
                child[rng.randrange(11)] = g
            nxt.append(child)
        pop = nxt
    best = max(pop, key=fit)
    team = [players[i] for i in best]
    sc = _score(team, sl)
    assignments = [{"slot": s["slot"], "role": s["role"], "x": s["x"], "y": s["y"], "player": p, "fit": f}
                   for s, p, f in zip(sl, team, sc["fits"])]
    top = max(assignments, key=lambda a: a["fit"])
    gap = sc["atk"] - sc["dfn"]
    balance = "well balanced" if abs(gap) <= 8 else ("leans towards attack" if gap > 0 else "leans towards defense")
    reason = (f"{sc['matches']} of 11 players are in their natural position. Attack rating {sc['atk']:.0f} vs defense "
              f"rating {sc['dfn']:.0f} ({balance}). Best role fit: {top['player']['PlayerName']} at {top['slot']} ({top['fit']:.0f}).")
    return {"assignments": assignments, "synergy": round(sc["synergy"], 1), "reason": reason,
            "bench": [players[i] for i in range(n) if i not in best]}


# ---------------- K-Means position classification (Position Map) ----------------
def classify_positions(players, k=3):
    """Returns a DataFrame with suggested role per outfield player, or None if there are too few players."""
    outfield = [p for p in players if p["Position"] != "GK"]
    if len(outfield) < k:
        return None
    X = np.array([vec(p) for p in outfield])
    km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(X)
    roles = ["DF", "MF", "FW"]
    score = np.array([[c @ np.array(ROLE_WEIGHTS[r]) for r in roles] for c in km.cluster_centers_])
    rows, cols = linear_sum_assignment(-score)
    cluster_role = {r: roles[c] for r, c in zip(rows, cols)}
    xy = PCA(n_components=2).fit_transform(X)
    return pd.DataFrame({
        "Player": [p["PlayerName"] for p in outfield],
        "Current position": [p["Position"] for p in outfield],
        "Suggested role": [cluster_role[l] for l in km.labels_],
        "x": xy[:, 0], "y": xy[:, 1]})
