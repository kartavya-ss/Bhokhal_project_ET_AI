"""
Task 15: build an interactive pyvis graph from the SQLite relationships table.
Can render the FULL graph, or a subgraph filtered to entities relevant to the
current question (better for the UI -- a 50-node graph is not "showstopper",
a focused 8-node graph that answers the question visually is).
"""
import sqlite3
from pyvis.network import Network

DB_PATH = "/home/claude/meridian/db/meridian.sqlite"

TYPE_COLORS = {
    "Batch": "#4C9AFF",
    "Machine": "#FF8B00",
    "Person": "#36B37E",
    "SOP": "#6554C0",
    "Deviation": "#DE350B",
}


def build_graph_html(out_path, focus_entities=None):
    """focus_entities: optional list of (type, value) tuples to filter the
    graph down to only relationships touching those entities (1-hop)."""
    conn = sqlite3.connect(DB_PATH)

    if focus_entities:
        values = [v for _, v in focus_entities]
        placeholders = ",".join("?" for _ in values)
        query = f"""SELECT subject_type, subject_value, relation, object_type, object_value, source_file
                    FROM relationships
                    WHERE subject_value IN ({placeholders}) OR object_value IN ({placeholders})"""
        cur = conn.execute(query, values + values)
    else:
        cur = conn.execute(
            "SELECT subject_type, subject_value, relation, object_type, object_value, source_file FROM relationships"
        )

    rows = cur.fetchall()

    net = Network(height="500px", width="100%", bgcolor="#ffffff", font_color="#222222", directed=True)
    net.barnes_hut(gravity=-3000, spring_length=150)

    added_nodes = set()

    def add_node(etype, evalue):
        key = f"{etype}:{evalue}"
        if key not in added_nodes:
            net.add_node(
                key,
                label=evalue,
                title=f"{etype}: {evalue}",
                color=TYPE_COLORS.get(etype, "#999999"),
                shape="box" if etype in ("Batch", "Deviation") else "dot",
                size=25,
            )
            added_nodes.add(key)

    for s_t, s_v, rel, o_t, o_v, src in rows:
        add_node(s_t, s_v)
        add_node(o_t, o_v)
        net.add_edge(f"{s_t}:{s_v}", f"{o_t}:{o_v}", label=rel, title=f"Source: {src}", arrows="to")

    net.set_options("""
    {
      "physics": {"stabilization": {"iterations": 150}},
      "edges": {"font": {"size": 10, "align": "middle"}, "smooth": {"type": "continuous"}}
    }
    """)
    net.write_html(out_path, notebook=False)
    return out_path


if __name__ == "__main__":
    path = build_graph_html("/home/claude/meridian/ui/graph_full.html")
    print(f"Full graph written to {path}")
