"""One document, several questions, one call; reasoning always on. Run with LEVANTO_API_KEY set."""

from levanto import LevantoClient, Scale, YesNo

policy = "Refunds within 30 days. Store credit up to 60 days for unopened items."
request = "Order bought 41 days ago, box unopened. Customer asks for a cash refund."

with LevantoClient(reasoning="on") as client:
    for item in client.decide(f"{policy}\n\n{request}", [
        YesNo("Under the policy, should we issue a cash refund?"),
        Scale("How likely is the customer to escalate?", ["none", "low", "medium", "high", "certain"]),
    ]):
        if item["ok"]:
            print(item["id"], item["result"], item["meta"].get("reasoning"))
        else:
            print(item["id"], "failed:", item["error"])
