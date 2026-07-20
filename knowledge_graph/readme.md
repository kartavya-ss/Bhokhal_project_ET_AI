# Knowledge Graph Visualization (Day 6-10)

## What it does
`build_graph.py` reads the `relationships` table from `meridian.db` (joined against
`entities` for names/types) and renders it as an interactive HTML network via pyvis:
- Nodes colored by entity type (MATERIAL=teal, OPERATOR=purple, SOP_REFERENCE=coral,
  EQUIPMENT=blue, PROCESS_STEP=pink, PARAMETER=amber, BATCH_ID/TIMESTAMP=gray)
- Edges labeled with relationship type (USED_IN, OPERATED_BY, GOVERNED_BY, RECORDED_AT)
- Physics-based layout (Barnes-Hut) so the graph auto-arranges into readable clusters
- Hover tooltips showing entity type + name
- Self-contained HTML — the vis-network JS library is embedded inline, so the file
  works even without an internet connection (good for a live demo with no wifi)

## Run
```bash
cd src
python build_graph.py --db ../../entity_extraction/output/meridian.db --out ../output/knowledge_graph.html

# Or filter to a single document (useful once you have many BMRs loaded):
python build_graph.py --db ../../entity_extraction/output/meridian.db \
    --out ../output/knowledge_graph.html --document-id BMR_MP-PCM-2601.pdf
```

Then just double-click `knowledge_graph.html` to open it in a browser.

## Notes
- If it prints "No relationships found" — you haven't run `load_entities.py` yet, or
  ran it against an empty/wrong DB path.
- This is a static export, not embedded in Streamlit yet. For the demo UI, this same
  pyvis HTML can be embedded via `st.components.v1.html(open(path).read(), height=750)`.