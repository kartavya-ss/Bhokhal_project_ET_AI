"""
build_graph.py
Renders the Meridian knowledge graph (entities + relationships from meridian.db)
as an interactive HTML network using pyvis. This is the demo visual for the
hackathon — physics-based layout, hover tooltips, color-coded by entity type.
 
Usage:
    python build_graph.py --db ../../entity_extraction/output/meridian.db \
                           --out ../output/knowledge_graph.html \
                           [--document-id BMR_MP-PCM-2601.pdf]  # optional: filter to one doc
"""
 
import argparse
import sqlite3
 
from pyvis.network import Network
 
# One color per entity type — keeps the graph scannable at a glance.
TYPE_COLORS = {
    "MATERIAL": "#1D9E75",       # teal
    "OPERATOR": "#7F77DD",       # purple
    "SOP_REFERENCE": "#D85A30",  # coral
    "EQUIPMENT": "#378ADD",      # blue
    "PROCESS_STEP": "#D4537E",   # pink
    "PARAMETER": "#EF9F27",      # amber
    "BATCH_ID": "#888780",       # gray
    "TIMESTAMP": "#B4B2A9",      # light gray
}
DEFAULT_COLOR = "#888780"
 
 
def fetch_edges(db_path: str, document_id: str | None):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
 
    query = """
        SELECT e1.entity_id AS src_id, e1.entity_name AS src_name, e1.entity_type AS src_type,
               e2.entity_id AS dst_id, e2.entity_name AS dst_name, e2.entity_type AS dst_type,
               r.relationship_type
        FROM relationships r
        JOIN entities e1 ON e1.entity_id = r.entity_id_1
        JOIN entities e2 ON e2.entity_id = r.entity_id_2
    """
    params = ()
    if document_id:
        query += " WHERE r.document_id = ?"
        params = (document_id,)
 
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows
 
 
def build_graph(db_path: str, out_path: str, document_id: str | None):
    rows = fetch_edges(db_path, document_id)
    if not rows:
        print("No relationships found in the database — did you run load_entities.py?")
        return
 
    net = Network(height="750px", width="100%", directed=True, notebook=False, cdn_resources="in_line")
    net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=120, spring_strength=0.04)
 
    added_nodes = set()
 
    def add_node(entity_id, name, entity_type):
        if entity_id in added_nodes:
            return
        color = TYPE_COLORS.get(entity_type, DEFAULT_COLOR)
        net.add_node(
            entity_id,
            label=name,
            title=f"{entity_type}: {name}",
            color=color,
            shape="dot",
            size=18,
        )
        added_nodes.add(entity_id)
 
    for row in rows:
        add_node(row["src_id"], row["src_name"], row["src_type"])
        add_node(row["dst_id"], row["dst_name"], row["dst_type"])
        net.add_edge(
            row["src_id"],
            row["dst_id"],
            label=row["relationship_type"],
            title=row["relationship_type"],
            arrows="to",
        )
 
    net.set_options("""
    {
      "edges": {"font": {"size": 10, "align": "middle"}, "smooth": {"type": "continuous"}},
      "nodes": {"font": {"size": 14}},
      "interaction": {"hover": true, "tooltipDelay": 100}
    }
    """)
 
    net.write_html(out_path, notebook=False)
    print(f"Graph written to {out_path} — {len(added_nodes)} nodes, {len(rows)} edges.")
    print("Open it directly in a browser (double-click the file).")
 
 
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", default="../output/knowledge_graph.html")
    parser.add_argument("--document-id", default=None, help="filter graph to one document")
    args = parser.parse_args()
    build_graph(args.db, args.out, args.document_id)
 