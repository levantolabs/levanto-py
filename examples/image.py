"""Judge a screenshot with its ticket. Run: python examples/image.py screenshot.png (LEVANTO_API_KEY set)."""

import sys

from levanto import Image, LevantoClient

with LevantoClient() as client:
    shot = Image.from_path(sys.argv[1], text="Ticket: the checkout button is missing on mobile.")
    print(client.yesno(shot, "Does the screenshot show the reported problem?"))
