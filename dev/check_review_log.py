"""Prints the answers the demo gave through the panel, as Anki recorded them."""

import sys
import time

from anki.collection import Collection

col = Collection(sys.argv[1])
since = (int(time.time()) - 900) * 1000  # the demo run, not the synthetic history
names = {1: "De novo", 2: "Difícil", 3: "Bom", 4: "Fácil"}
rows = col.db.all(
    "select id, cid, ease, type from revlog where id >= ? and ease > 0 and factor != 2501 order by id", since
)
for rid, cid, ease, typ in rows:
    card = col.get_card(cid)
    front = card.note().fields[0]
    text = front.split("<br>")[0][:70] if not front.startswith("<b>") else front.split("<br><br>")[1][:70]
    print(f"{names.get(ease, ease):8} | {col.decks.name(card.did):24} | {text}")
data = col.get_config("painelEstudos", {})
roleta = data.get("roleta") or {}
for cat in roleta.get("cats", []):
    topics = [t for s in cat["subs"] for t in s["topics"]]
    seen = sum(1 for t in topics if t["seen"])
    notes = sum(1 for t in topics if t.get("note"))
    print(f"roleta: {cat['name']:24} deck={cat.get('deck')} topics={len(topics)} seen={seen} notes={notes}")
print(f"saved keys: {sorted(data)}; fx={data.get('fx')}")
col.close()
