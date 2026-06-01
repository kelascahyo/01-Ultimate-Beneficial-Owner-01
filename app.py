import streamlit as st
import pandas as pd
import networkx as nx
import json
import streamlit.components.v1 as components

# Set page config
st.set_page_config(layout="wide", page_title="Tax Risk & UBO Analytics Dashboard")

# Custom Title and Banner
st.markdown("""
<div style="background-color:#1e293b; padding:20px; border-radius:10px; margin-bottom:25px; color:white;">
    <h2 style="margin:0; color:#f8fafc;">💡 Tax Risk Analysis: Ultimate Beneficial Owner (UBO) Dashboard</h2>
    <p style="margin:5px 0 0 0; color:#cbd5e1; font-size:14px;">
        Trace layered ownership chains, calculate multi-tier effective shareholding, and detect ultimate beneficiaries (OP/LN).
    </p>
</div>
""", unsafe_allow_html=True)

# English Narratives Side documentation
with st.sidebar:
    st.markdown("""
    ### 📘 Methodology & Documentation
    
    In tax administration, aggressive tax planning and base erosion often involve masking the **Ultimate Beneficial Owner (UBO)** through complex layered corporate shells (**Badan**). 
    
    The target of this module is to traverse the ownership graph upwards from a selected target company to discover the top-level **Individuals (Orang Pribadi / OP)** or **Foreign Entities (Perusahaan Luar Negeri / LN)** who ultimately control the entity and receive economic benefits.
    
    #### 🔑 Key Concepts:
    - **Layered Ownership**: Entity A is owned by Entity B, which is owned by Individual C.
    - **Effective Ownership %**: Calculated via path multiplication. If B owns 60% of A, and C owns 50% of B, C's effective ownership in A is $50\% \times 60\% = 30\%$.
    - **UBO Threshold**: Commonly set at $\ge 25\%$ to determine significant influence/control for tax audit profiling.
    """, unsafe_allow_html=True)

@st.cache_data
def load_data():
    nodes = pd.read_csv('nodes_masked.csv')
    edges = pd.read_csv('edges_masked_part1_a.csv')
    return nodes, edges

try:
    nodes_df, edges_df = load_data()
except Exception as e:
    st.error(f"Error loading CSV files: {e}. Please ensure nodes_masked.csv and edges_masked_part1_a.csv are in the same folder.")
    st.stop()

# Build NetworkX Directed Graph
G = nx.DiGraph()

for _, row in nodes_df.iterrows():
    G.add_node(row['id'], label=row['nama'], type=row['jenis_node'])

for _, row in edges_df.iterrows():
    G.add_edge(
        row['sumber'], 
        row['target'], 
        weight=float(row['persentase']), 
        nilai=float(row['nilai']), 
        dividen=float(row['dividen']),
        rel_id=row['rel_id']
    )

# Filters & Selections
st.subheader("🔍 UBO Path Finder & Ownership Investigation")
col1, col2 = st.columns([1, 3])

with col1:
    valid_targets = [n for n in G.nodes() if G.in_degree(n) > 0 and G.nodes[n].get('type') == 'Badan']
    target_options = {f"{G.nodes[n].get('label', 'Unknown')} ({n})": n for n in valid_targets}
    
    selected_target_label = st.selectbox(
        "Select Target Company (Badan) to Investigate:",
        options=list(target_options.keys()) if target_options else ["No corporate nodes found"]
    )
    
    ubo_threshold = st.slider("Minimum Effective Ownership UBO Threshold (%)", min_value=0.0, max_value=100.0, value=25.0, step=1.0)

selected_target_id = target_options[selected_target_label]

def find_all_upstream_paths(graph, target_node):
    all_ancestors = nx.ancestors(graph, target_node)
    all_paths = []
    for ancestor in all_ancestors:
        paths = list(nx.all_simple_paths(graph, source=ancestor, target=target_node))
        all_paths.extend(paths)
    return all_paths

paths = find_all_upstream_paths(G, selected_target_id)

ubo_results = []
subgraph_nodes = set([selected_target_id])
subgraph_edges = []
node_effective_ownership = {}

for path in paths:
    eff_pct = 1.0
    for i in range(len(path) - 1):
        u, v = path[i], path[i+1]
        eff_pct *= (G[u][v]['weight'] / 100.0)
    
    eff_pct *= 100.0
    root_node = path[0]
    node_effective_ownership[root_node] = node_effective_ownership.get(root_node, 0.0) + eff_pct
    
    for n in path:
        subgraph_nodes.add(n)
    for i in range(len(path) - 1):
        subgraph_edges.append((path[i], path[i+1]))

summary_data = []
for node_id, eff_share in node_effective_ownership.items():
    ntype = G.nodes[node_id].get('type', 'Unknown')
    summary_data.append({
        "Node ID": node_id,
        "Name": G.nodes[node_id].get('label', 'Unknown'),
        "Type": ntype,
        "Accumulated Effective Shareholding": f"{eff_share:.4f}%",
        "Is Qualified UBO (Threshold)": "✅ Yes" if eff_share >= ubo_threshold and ntype in ['OP', 'LN'] else ("⚠️ Direct/Indirect Owner" if ntype in ['OP', 'LN'] else "🏢 Intermediary Shell")
    })

df_summary = pd.DataFrame(summary_data)

with col2:
    st.markdown("### 📊 Calculated Upstream Ownership Summary")
    if not df_summary.empty:
        st.dataframe(df_summary, use_container_width=True)
    else:
        st.info("No upstream paths or owners detected for this entity.")

# Data formatting for D3.js
d3_nodes = []
d3_links = []
seen_edges = set()

for node_id in subgraph_nodes:
    n_attr = G.nodes[node_id]
    eff_val = node_effective_ownership.get(node_id, 0.0) if node_id != selected_target_id else 100.0
    d3_nodes.append({
        "id": str(node_id),
        "name": n_attr.get('label', 'Unknown'),
        "type": n_attr.get('type', 'Unknown'),
        "effective_share": round(eff_val, 2),
        "is_target": node_id == selected_target_id
    })

for u, v in subgraph_edges:
    edge_key = f"{u}->{v}"
    if edge_key not in seen_edges:
        seen_edges.add(edge_key)
        d3_links.append({
            "source": str(u),
            "target": str(v),
            "percentage": G[u][v]['weight'],
            "value_idr": G[u][v]['nilai'],
            "dividen_idr": G[u][v]['dividen']
        })

graph_json = json.dumps({"nodes": d3_nodes, "links": d3_links})

# Embedded D3.js Component Engine with Zoom, Pan and Interactive Highlighting
html_component = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; margin: 0; background-color: #0f172a; color: #e2e8f0; overflow: hidden; }}
        #graph-container {{ width: 100%; height: 600px; border: 1px solid #334155; border-radius: 8px; background-color: #1e293b; position: relative; }}
        .node {{ stroke-width: 2px; cursor: pointer; transition: stroke-width 0.2s; }}
        .node:hover {{ stroke-width: 4px; stroke: #f59e0b !important; }}
        .link {{ stroke: #64748b; stroke-opacity: 0.6; stroke-width: 2px; fill: none; marker-end: url(#arrow); }}
        .link.highlight {{ stroke: #10b981; stroke-opacity: 1; stroke-width: 4px; }}
        .node.highlight {{ stroke: #10b981 !important; stroke-width: 4px; }}
        .text-label {{ font-size: 11px; fill: #94a3b8; pointer-events: none; font-weight: 600; }}
        .edge-label {{ font-size: 10px; fill: #cbd5e1; pointer-events: none; }}
        #tooltip {{ position: absolute; background: rgba(15, 23, 42, 0.95); border: 1px solid #475569; padding: 10px; border-radius: 6px; font-size: 12px; color: #f8fafc; visibility: hidden; z-index: 1000; box-shadow: 0 4px 6px rgba(0,0,0,0.5); }}
        .legend {{ position: absolute; bottom: 15px; left: 15px; background: rgba(30, 41, 59, 0.9); padding: 10px; border-radius: 6px; border: 1px solid #475569; font-size: 11px; }}
        .legend-item {{ display: flex; align-items: center; margin-bottom: 4px; }}
        .legend-color {{ width: 12px; height: 12px; margin-right: 8px; border-radius: 50%; }}
    </style>
    <script src="https://d3js.org/d3.v7.min.js"></script>
</head>
<body>
    <div id="graph-container">
        <div id="tooltip"></div>
        <div class="legend">
            <div style="font-weight:bold; margin-bottom: 5px; color:#f1f5f9;">Node Types Legend</div>
            <div class="legend-item"><div class="legend-color" style="background:#ef4444;"></div><b>Badan</b> (Corporate Shell)</div>
            <div class="legend-item"><div class="legend-color" style="background:#3b82f6;"></div><b>OP</b> (Orang Pribadi / Individual)</div>
            <div class="legend-item"><div class="legend-color" style="background:#a855f7;"></div><b>LN</b> (Foreign Entity)</div>
            <div class="legend-item"><div class="legend-color" style="background:#e2e8f0;"></div><b>Non NPWP</b></div>
            <div class="legend-item" style="margin-top:5px; border-top:1px solid #475569; padding-top:5px;">
                <div style="width:12px; height:12px; border:2px dashed #f59e0b; margin-right:8px;"></div>Target Under Audit
            </div>
        </div>
    </div>

    <script>
        const graphData = {graph_json};
        const width = document.getElementById('graph-container').clientWidth;
        const height = 600;

        const svg = d3.select("#graph-container").append("svg").attr("width", "100%").attr("height", height);
        
        svg.append("defs").append("marker")
            .attr("id", "arrow").attr("viewBox", "0 -5 10 10").attr("refX", 22).attr("refY", 0)
            .attr("markerWidth", 6).attr("markerHeight", 6).attr("orient", "auto")
            .append("path").attr("d", "M0,-5L10,0L0,5").attr("fill", "#64748b");

        const g = svg.append("g");
        svg.call(d3.zoom().scaleExtent([0.2, 4]).on("zoom", (e) => g.attr("transform", e.transform)));

        function getNodeColor(t) {{
            if(t==='Badan') return '#ef4444';
            if(t==='OP') return '#3b82f6';
            if(t==='LN') return '#a855f7';
            return '#e2e8f0';
        }}

        const simulation = d3.forceSimulation(graphData.nodes)
            .force("link", d3.forceLink(graphData.links).id(d => d.id).distance(130))
            .force("charge", d3.forceManyBody().strength(-400))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collision", d3.forceCollide().radius(45));

        const link = g.append("g").selectAll("path").data(graphData.links).enter().append("path").attr("class", "link");
        const linkText = g.append("g").selectAll("text").data(graphData.links).enter().append("text").attr("class", "edge-label").text(d => d.percentage + "%");

        const node = g.append("g").selectAll("circle").data(graphData.nodes).enter().append("circle")
            .attr("class", "node").attr("r", d => d.is_target ? 16 : 12)
            .attr("fill", d => getNodeColor(d.type)).attr("stroke", d => d.is_target ? "#f59e0b" : "#475569")
            .style("stroke-dasharray", d => d.is_target ? "4,4" : "0")
            .call(d3.drag().on("start", dragstarted).on("drag", dragged).on("end", dragended));

        const labels = g.append("g").selectAll("text").data(graphData.nodes).enter().append("text")
            .attr("class", "text-label").attr("dx", d => d.is_target ? 20 : 16).attr("dy", 4).text(d => d.name);

        const tooltip = d3.select("#tooltip");
        node.on("mouseover", function(e, d) {{
            tooltip.style("visibility", "visible").html(`
                <strong>Name:</strong> ${{d.name}}<br/><strong>ID:</strong> ${{d.id}}<br/>
                <strong>Type:</strong> ${{d.type}}<br/><strong>Effective Share:</strong> ${{d.effective_share}}%
            `);
        }}).on("mousemove", function(e) {{
            tooltip.style("top", (e.pageY - 10) + "px").style("left", (e.pageX + 15) + "px");
        }}).on("mouseout", function() {{ tooltip.style("visibility", "hidden"); }});

        // Click handler to highlight path to top-level owners
        node.on("click", function(e, d) {{
            node.classed("highlight", false); link.classed("highlight", false);
            let activeNodes = new Set(); let activeLinks = new Set();
            
            function traceUpstream(nId) {{
                activeNodes.add(nId);
                graphData.links.forEach(l => {{
                    const tgt = l.target.id || l.target; const src = l.source.id || l.source;
                    if (tgt === nId) {{
                        activeLinks.add(`${{src}}->${{tgt}}`);
                        if (!activeNodes.has(src)) traceUpstream(src);
                    }}
                }});
            }}
            traceUpstream(d.id);
            node.classed("highlight", n => activeNodes.has(n.id));
            link.classed("highlight", l => activeLinks.has(`${{l.source.id}}->${{l.target.id}}`));
        }});

        simulation.on("tick", () => {{
            link.attr("d", d => `M${{d.source.x}},${{d.source.y}} L${{d.target.x}},${{d.target.y}}`);
            node.attr("cx", d => d.x).attr("cy", d => d.y);
            labels.attr("x", d => d.x).attr("y", d => d.y);
            linkText.attr("x", d => (d.source.x + d.target.x) / 2).attr("y", d => (d.source.y + d.target.y) / 2);
        }});

        function dragstarted(e, d) {{ if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }}
        function dragged(e, d) {{ d.fx = e.x; d.fy = e.y; }}
        function dragended(e, d) {{ if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }}
    </script>
</body>
</html>
"""

st.markdown("### 🕸️ Interactive D3.js Corporate Layering & UBO Path Graph")
st.markdown("*💡 **Interactivity Tip:** Click on any node inside the chart view below to highlight the exact upstream chain of control to the ultimate founders or beneficiaries.*")

components.html(html_component, height=620, scrolling=False)
