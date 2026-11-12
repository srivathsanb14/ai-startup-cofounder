"""A small, fixed 'web' for testing the question-driven agents on a concept unrelated to climbing.

Concept: a staff-scheduling app for independent coffee shops in Austin (B2B; the payer is the shop owner).
Pages are invented test fixtures (domains end in .test) with the kinds of evidence a real run sees: owners' forum
posts, a vendor's own pricing page, a free competitor, a local count, an off-topic page that shares a word, an
out-of-area statistic, and a post that contradicts the founder's assumption. Nothing here is real data.
"""
import re

from startup_cofounder.llm import MockLLM
from startup_cofounder.tools import ALL_TOOLS, Tool, ToolResult

IDEA = ("A scheduling app for independent coffee shops in Austin that helps owners build weekly staff rosters "
        "without spreadsheets. It is not a payroll system.")

PAGES = [
    {"title": "How do you schedule baristas? : r/barista", "url": "https://www.reddit.com/r/barista/comments/a1/schedule",
     "snippet": "As a cafe owner I spend about three hours every week building the staff schedule in a spreadsheet. "
                "Shift swaps by text message are the worst part of scheduling baristas.",
     "keys": "schedul roster shift barista owner spreadsheet staff coffee"},
    {"title": "Scheduling staff at a small coffee shop - forum", "url": "https://forum.coffeeowners.test/t/42",
     "snippet": "We tried a scheduling app but went back to paper; for six staff a printed roster works fine and "
                "costs nothing.", "keys": "schedul roster staff coffee shop paper free"},
    {"title": "ShiftBrew pricing - plans for cafes", "url": "https://shiftbrew.test/pricing",
     "snippet": "ShiftBrew scheduling costs $39 per month per location. ShiftBrew helps cafes build shift schedules.",
     "keys": "shiftbrew pricing schedul coffee cafe staff plan price"},
    {"title": "RosterPal - free staff scheduling for small teams", "url": "https://rosterpal.test/",
     "snippet": "RosterPal is free for up to 10 employees. RosterPal is a scheduling app for restaurants and coffee "
                "shops.", "keys": "rosterpal free schedul staff restaurant coffee shop"},
    {"title": "ShiftBrew reviews - App Store", "url": "https://apps.apple.com/us/app/shiftbrew/id1",
     "snippet": "The shift swap feature keeps crashing and I wish it handled availability better for part-time "
                "baristas.", "keys": "shiftbrew review crash wish schedul barista app"},
    {"title": "Austin coffee scene report", "url": "https://www.austinchronicle.test/food/coffee-2026",
     "snippet": "Austin has more than 320 independent coffee shops, according to the 2026 city business directory.",
     "keys": "austin coffee shop independent number count directory"},
    {"title": "US coffee shop market statistics", "url": "https://coffeestats.test/us",
     "snippet": "There are 38,000 coffee shops in the United States and the market is growing.",
     "keys": "coffee shop number market statistics"},
    {"title": "How to roast coffee beans at home", "url": "https://homeroast.test/guide",
     "snippet": "Roasting coffee beans at home takes about fifteen minutes in a pan.",
     "keys": "coffee beans roast"},
    {"title": "Austin Independent Coffee Owners Meetup", "url": "https://www.meetup.com/austin-coffee-owners/",
     "snippet": "A monthly meetup group for independent coffee shop owners in Austin to share hiring and staffing tips.",
     "keys": "austin meetup group owner coffee community event staff"},
    {"title": "Building a shift scheduling backend with a calendar API", "url": "https://devblog.test/shift-api",
     "snippet": "A shift scheduling backend needs a database of availability, a calendar API and push notification "
                "service; open source libraries handle recurring shifts.",
     "keys": "api architecture backend schedul database notification open source"},
    {"title": "Why our cafe scheduling startup shut down", "url": "https://blog.founderstories.test/cafe-shifts",
     "snippet": "Our coffee shop scheduling startup shut down because small cafes would not pay more than $10 a month "
                "and churned after the free trial.", "keys": "shut down fail startup coffee schedul pay"},
]


def search(query: str):
    q = set(re.findall(r"[a-z]+", query.lower()))
    hits = []
    for p in PAGES:
        keys = set(p["keys"].split())
        score = sum(1 for k in keys for w in q if w.startswith(k[:5]))
        if score >= 2:
            hits.append((score, p))
    hits.sort(key=lambda x: -x[0])
    return ToolResult(sources=[{k: p[k] for k in ("title", "url", "snippet")} for _, p in hits[:5]])


def install(monkeypatch, calls=None):
    def tool(name):
        def run(query):
            if calls is not None:
                calls.append((name, query))
            return search(query)
        return Tool(name, "stub", {"query": "string"}, run)
    for name in ("web_search", "news_search", "hn_search", "wikipedia"):
        monkeypatch.setitem(ALL_TOOLS, name, tool(name))
    from startup_cofounder import retrieval
    monkeypatch.setattr(retrieval, "page_text", lambda url, limit=30000: ("", ""))


class ScriptedSmallModel(MockLLM):
    """Behaves like a small model: the brief call drifts ('AI marketplace'), the analyst quotes evidence and marks
    a stance, and the contradicting forum post is reported as contradicting."""

    def chat(self, messages, temperature=None, json_mode=False, schema=None):
        import json
        system, user = messages[0]["content"], messages[1]["content"]
        role = re.search(r"ROLE: (\w+)", system).group(1)
        if role == "brief":
            return json.dumps({"product": "AI-powered staffing marketplace", "target_customer": "independent coffee "
                               "shops in Austin", "problem": "building weekly staff rosters takes hours",
                               "customer_job": "build weekly staff rosters", "geography": "Austin", "stage": "launched",
                               "payer": "business", "business_model": "subscription marketplace commission",
                               "constraints": [], "exclusions": ["payroll system"], "riskiest_assumption": ""})
        if role == "coordinator":
            return json.dumps({"idea_summary": IDEA, "category": "coffee shop staff scheduling software",
                               "problem": "building weekly staff rosters without spreadsheets",
                               "search_keywords": ["coffee shop scheduling", "barista roster"], "geography": "Austin",
                               "payer": "business", "customer_type": "independent coffee shop owners",
                               "tasks": {}, "extra_specialists": []})
        if role == "analyst":
            items = re.findall(r"\[(E\d+)\] (.+)\n\s+url: (.+)\n\s+(.+)", user)
            findings = []
            for sid, title, url, snippet in items[:3]:
                sent = re.split(r"(?<=[.!?])\s+", snippet)[0]
                stance = "contradicts" if re.search(r"works fine|went back to paper|would not pay", sent) else (
                    "supports" if re.search(r"spend|worst|wish|crash", sent) else "neutral")
                findings.append({"statement": sent, "type": "fact", "stance": stance, "source_ids": [sid]})
            if not findings:
                return json.dumps({"status": "insufficient", "answer": "", "findings": [], "unknown": "no evidence"})
            return json.dumps({"status": "answered", "answer": findings[0]["statement"], "findings": findings,
                               "unknown": ""})
        return super().chat(messages, temperature=temperature, json_mode=json_mode, schema=schema)
