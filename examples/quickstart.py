"""Every decision kind once. Run: LEVANTO_API_KEY=lv_live_... python examples/quickstart.py"""

from levanto import LevantoClient, TagSpec

ticket = "Checkout returns a 500 for about 10% of EU customers since the deploy 20 minutes ago."

with LevantoClient() as client:
    print(client.yesno(ticket, "Is this revenue-impacting?"))
    print(client.choice(ticket, "Which team owns this first?", ["billing", "engineering", "sales"]))
    print(client.scale(ticket, "How urgent?", ["none", "low", "medium", "high", "critical"]))
    print(client.sort([{"id": "typo", "content": "FAQ typo"}, {"id": "db", "content": "Database down"}], "Most urgent first"))
    print(client.tags(ticket, [TagSpec("outage", "outage: something is down"), "billing"], instructions="Tag what it reports."))
