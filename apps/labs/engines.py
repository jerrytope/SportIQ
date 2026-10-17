"""Scoring for each lab engine. All results are TRAINING EXERCISES (blueprint Module 3)."""


def branching_step(scenario, run, option_index):
    nodes = scenario.data.get("nodes", {})
    current = run.path[-1]["node"] if run.path else scenario.data.get("start")
    if run.path and run.path[-1].get("next") is not None:
        current = run.path[-1]["next"]
    node = nodes.get(current)
    if not node or not node.get("options"):
        return None
    try:
        opt = node["options"][option_index]
    except (IndexError, TypeError):
        return None
    run.path = list(run.path) + [{"node": current, "choice": option_index, "score": opt.get("score", 0),
                                  "feedback": opt.get("feedback", ""), "next": opt.get("next")}]
    nxt = nodes.get(opt.get("next")) if opt.get("next") else None
    if not nxt or not nxt.get("options"):
        steps = len(run.path)
        got = sum(int(p["score"]) for p in run.path)
        run.score = max(0, min(100, round(100 * got / (10 * steps)))) if steps else 0
        run.completed = True
        run.feedback = [p["feedback"] for p in run.path if p["feedback"]]
    return opt


def branching_current(scenario, run):
    nodes = scenario.data.get("nodes", {})
    if not run.path:
        return scenario.data.get("start"), nodes.get(scenario.data.get("start"))
    nxt = run.path[-1].get("next")
    return nxt, nodes.get(nxt)


def score_annotate(scenario, annotations, report):
    moments = scenario.data.get("key_moments", [])
    hits, feedback = 0, []
    for m in moments:
        tol = m.get("tolerance", 4)
        found = any(abs(float(a.get("t", -99)) - m["t"]) <= tol and a.get("tag") == m["tag"] for a in annotations)
        hits += int(found)
        feedback.append(("✓ " if found else "✗ ") + f"{m['tag']} at {int(m['t'])}s: {m.get('explain', '')}")
    report_bonus = 10 if len(report.split()) >= 60 else 0
    base = round(90 * hits / len(moments)) if moments else 0
    return min(100, base + report_bonus), feedback


def acwr(weeks):
    """Acute:chronic workload ratio: this week's load / mean of the 4 weeks before it."""
    if len(weeks) < 5:
        return None
    chronic = sum(weeks[-5:-1]) / 4
    return round(weeks[-1] / chronic, 2) if chronic else None


def score_load(scenario, flagged):
    threshold = scenario.data.get("threshold", 1.5)
    rows, correct, feedback = [], 0, []
    for a in scenario.data.get("athletes", []):
        ratio = acwr(a["weeks"])
        at_risk = ratio is not None and ratio > threshold
        chose = a["name"] in flagged
        correct += int(chose == at_risk)
        rows.append({"name": a["name"], "ratio": ratio, "at_risk": at_risk, "chose": chose})
        if chose != at_risk:
            feedback.append(f"{a['name']}: ACWR {ratio}: {'should' if at_risk else 'should not'} be flagged (threshold {threshold}).")
    n = len(rows) or 1
    return round(100 * correct / n), feedback or ["All athletes classified correctly. Good load monitoring."], rows


def score_designer(scenario, drill_ids):
    drills = {d["id"]: d for d in scenario.data.get("drills", [])}
    chosen = [drills[i] for i in drill_ids if i in drills]
    target = scenario.data.get("target_minutes", 60)
    total = sum(d["minutes"] for d in chosen)
    feedback, score = [], 100
    if not chosen:
        return 0, ["Add drills to build a session."]
    if chosen[0]["phase"] != "warmup":
        score -= 20
        feedback.append("Start with a warm-up to raise heart rate and reduce injury risk.")
    if chosen[-1]["phase"] != "cooldown":
        score -= 15
        feedback.append("Finish with a cool-down and review.")
    if not any(d["phase"] == "skill" for d in chosen):
        score -= 20
        feedback.append("Include at least one skill-development practice linked to your objective.")
    if not any(d["phase"] == "game" for d in chosen):
        score -= 15
        feedback.append("Add a game-related practice so players apply the skill under pressure.")
    order = {"warmup": 0, "skill": 1, "game": 2, "cooldown": 3}
    if [order[d["phase"]] for d in chosen] != sorted(order[d["phase"]] for d in chosen):
        score -= 10
        feedback.append("Phases are out of order: warm-up → skill → game → cool-down works best.")
    if abs(total - target) > 10:
        score -= 15
        feedback.append(f"Session lasts {total} min; aim for about {target} min.")
    high = [d for d in chosen if d.get("intensity") == "high"]
    if len(high) > 2:
        score -= 10
        feedback.append("Too many high-intensity blocks for this age group; balance load and recovery.")
    if not feedback:
        feedback.append("Well-structured session: clear progression and appropriate duration.")
    return max(0, score), feedback


def score_budget(scenario, allocation):
    total = scenario.data.get("total", 0)
    spent = sum(allocation.values())
    score, feedback = 100, []
    if spent > total:
        score -= 40
        feedback.append(f"Over budget by ₦{spent - total:,.0f}. Federations must not commit funds they don't have.")
    for line in scenario.data.get("lines", []):
        amt = allocation.get(line["key"], 0)
        if amt < line.get("min", 0):
            score -= 15
            feedback.append(f"{line['label']}: ₦{amt:,.0f} is below the minimum safe level (₦{line['min']:,.0f}). {line.get('why', '')}")
        elif line.get("ideal") and abs(amt - line["ideal"]) > 0.5 * line["ideal"]:
            score -= 5
            feedback.append(f"{line['label']}: allocation is far from the typical share for an event of this size.")
    if spent < 0.85 * total:
        score -= 5
        feedback.append("Large unallocated balance: consider a contingency line (5-10%) instead.")
    if not feedback:
        feedback.append("Balanced, realistic budget with safety and contingency covered.")
    return max(0, score), feedback
