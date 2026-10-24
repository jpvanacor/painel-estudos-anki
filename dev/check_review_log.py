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
edital = data.get("edital") or {}
done = sum(1 for m in edital.get("materias", []) for g in m["groups"] for t in g["topics"] if t["done"])
print(f"edital: {len(edital.get('materias', []))} matérias, cycle {edital.get('cycle')}, current {edital.get('current')}, done {done}")
col.close()
