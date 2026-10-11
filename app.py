import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(layout="wide")

st.markdown(
    """
    <style>
    .block-container {
        padding-left: 5rem;
        padding-right: 5rem;
        padding-top: 2rem;
    }
    [data-testid="stSidebar"] {
        padding-left: 4rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("Inventory Policy Simulator")

# ------------------------------------------------
# Sidebar Inputs (Base Case)
# ------------------------------------------------
st.sidebar.header("Base Case Inputs")

base_opening_balance = st.sidebar.number_input("Opening Balance", value=500, key="base_ob")
base_avg_demand = st.sidebar.number_input("Average Demand", value=25, key="base_ad")
base_cov = st.sidebar.number_input("Coefficient of Variation", value=0.8, key="base_cov")
base_lead_time = st.sidebar.number_input("Lead Time (Days)", value=3, key="base_lt")
base_reorder_point = st.sidebar.number_input("Reorder Point", value=200, key="base_rop")
base_order_qty = st.sidebar.number_input("Order Quantity", value=300, key="base_oq")
base_unit_value = st.sidebar.number_input("Value Per Unit", value=100, key="base_uv")
base_holding_cost_percent = st.sidebar.number_input("Holding Cost (% of Value)", value=20.0, key="base_hc")
base_ordering_cost = st.sidebar.number_input("Ordering Cost Per Order", value=500, key="base_oc")
num_days = st.sidebar.slider("Simulation Days", 100, 2000, 365, key="days")

base_holding_cost_rate = base_holding_cost_percent / 100

if "base_demand_sequence" not in st.session_state:
    st.session_state.base_demand_sequence = None
if st.sidebar.button("Reset Base Demand Scenario"):
    st.session_state.base_demand_sequence = None

if st.session_state.base_demand_sequence is None:
    st.session_state.base_demand_sequence = np.maximum(
        0, np.random.normal(base_avg_demand, base_avg_demand * base_cov, num_days)
    ).round()

base_demand = st.session_state.base_demand_sequence
dates = pd.date_range(start="2024-01-01", periods=num_days)

# ------------------------------------------------
# Main Page Inputs (Scenario Case)
# ------------------------------------------------
col1, col2 = st.columns([1, 1])

with col2:
    with st.expander("Scenario Inputs (Right Hand Side)", expanded=True):
        st.markdown("### Scenario Configuration")
        s_col_a, s_col_b = st.columns(2)
        scen_opening_balance = s_col_a.number_input("Opening Balance", value=500, key="scen_ob")
        scen_avg_demand = s_col_b.number_input("Average Demand", value=25, key="scen_ad")
        scen_cov = s_col_a.number_input("Coefficient of Variation", value=0.8, key="scen_cov")
        scen_lead_time = s_col_b.number_input("Lead Time (Days)", value=3, key="scen_lt")
        scen_reorder_point = s_col_a.number_input("Reorder Point", value=350, key="scen_rop") # Default updated to 350
        scen_order_qty = s_col_b.number_input("Order Quantity", value=300, key="scen_oq")
        scen_unit_value = s_col_a.number_input("Value Per Unit", value=100, key="scen_uv")
        scen_holding_cost_percent = s_col_b.number_input("Holding Cost (% of Value)", value=20.0, key="scen_hc")
        scen_ordering_cost = s_col_a.number_input("Ordering Cost Per Order", value=500, key="scen_oc")

scen_holding_cost_rate = scen_holding_cost_percent / 100

# Use same demand sequence if parameters match, otherwise generate new one
if scen_avg_demand == base_avg_demand and scen_cov == base_cov:
    scen_demand = base_demand
else:
    scen_demand = np.maximum(0, np.random.normal(scen_avg_demand, scen_avg_demand * scen_cov, num_days)).round()

# ------------------------------------------------
# Simulation Function
# ------------------------------------------------
def run_simulation(demand_seq, op_bal, lt, rop, oq, uv, hc_rate, oc):
    inventory = op_bal
    pipeline_orders = []
    data = []
    
    for day in range(num_days):
        shipment_received = 0
        for order in pipeline_orders.copy():
            if order[0] == day:
                shipment_received += order[1]
                pipeline_orders.remove(order)
                
        opening = inventory
        inventory += shipment_received
        demand_today = demand_seq[day]
        inventory -= demand_today
        
        if inventory < 0:
            inventory = 0
            
        pipeline_qty = sum(qty for arrival, qty in pipeline_orders)
        inventory_position = opening - demand_today + shipment_received + pipeline_qty
        
        new_order = 0
        if inventory_position < rop:
            new_order = oq
            pipeline_orders.append((day + lt, oq))
            
        closing = inventory
        closing_with_pipeline = closing + sum(qty for arrival, qty in pipeline_orders)
        
        data.append([
            dates[day], opening, demand_today, shipment_received, pipeline_qty,
            inventory_position, new_order, closing, closing_with_pipeline
        ])
        
    df = pd.DataFrame(data, columns=[
        "Date", "Opening Balance", "Demand", "Shipment Received", "Pipeline Order",
        "Inventory Position", "New Order", "Closing Balance", "Closing Balance Including Pipeline"
    ])
    
    # KPIs
    kpis = {}
    kpis["stockout_days"] = (df["Closing Balance"] == 0).sum()
    kpis["average_inventory"] = df["Closing Balance Including Pipeline"].mean()
    kpis["average_age_inventory"] = kpis["average_inventory"] / df["Demand"].mean() if df["Demand"].mean() > 0 else 0
    df["Blocked Working Capital"] = df["Inventory Position"] * uv
    kpis["average_working_capital"] = df["Blocked Working Capital"].mean()
    kpis["min_inventory"] = df["Closing Balance"].min()
    kpis["max_inventory"] = df["Closing Balance"].max()
    kpis["min_wc"] = df["Blocked Working Capital"].min()
    kpis["max_wc"] = df["Blocked Working Capital"].max()
    
    df["Inventory Value"] = df["Closing Balance Including Pipeline"] * uv
    df["Holding Cost"] = df["Inventory Value"] * hc_rate / 365
    kpis["total_holding_cost"] = df["Holding Cost"].sum()
    kpis["number_of_orders"] = (df["New Order"] > 0).sum()
    kpis["total_ordering_cost"] = kpis["number_of_orders"] * oc
    kpis["total_inventory_cost"] = kpis["total_holding_cost"] + kpis["total_ordering_cost"]
    
    return df, kpis

# ------------------------------------------------
# Run Simulations
# ------------------------------------------------
df_base, kpis_base = run_simulation(
    base_demand, base_opening_balance, base_lead_time, base_reorder_point, 
    base_order_qty, base_unit_value, base_holding_cost_rate, base_ordering_cost
)

df_scen, kpis_scen = run_simulation(
    scen_demand, scen_opening_balance, scen_lead_time, scen_reorder_point, 
    scen_order_qty, scen_unit_value, scen_holding_cost_rate, scen_ordering_cost
)

# Helper function for percentage difference
def calc_delta(base, scen):
    if base == 0:
        return f"{scen - base:,.0f} (N/A)"
    diff = scen - base
    pct = (diff / base) * 100
    return f"{diff:,.0f} ({pct:+.1f}%)"

# ------------------------------------------------
# KPI Comparison Display
# ------------------------------------------------
st.subheader("KPI Comparison: Base vs Scenario")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Stockout Days (Scenario)", kpis_scen["stockout_days"], calc_delta(kpis_base["stockout_days"], kpis_scen["stockout_days"]), delta_color="inverse")
c2.metric("Average Age of Inv (Scenario)", round(kpis_scen["average_age_inventory"], 1), calc_delta(kpis_base["average_age_inventory"], kpis_scen["average_age_inventory"]), delta_color="inverse")
c3.metric("Average Inventory (Scenario)", round(kpis_scen["average_inventory"], 0), calc_delta(kpis_base["average_inventory"], kpis_scen["average_inventory"]), delta_color="inverse")
c4.metric("Avg Working Capital (Scenario)", round(kpis_scen["average_working_capital"], 0), calc_delta(kpis_base["average_working_capital"], kpis_scen["average_working_capital"]), delta_color="inverse")

cc1, cc2, cc3 = st.columns(3)
cc1.metric("Total Holding Cost (Scenario)", round(kpis_scen["total_holding_cost"], 0), calc_delta(kpis_base["total_holding_cost"], kpis_scen["total_holding_cost"]), delta_color="inverse")
cc2.metric("Total Ordering Cost (Scenario)", round(kpis_scen["total_ordering_cost"], 0), calc_delta(kpis_base["total_ordering_cost"], kpis_scen["total_ordering_cost"]), delta_color="inverse")
cc3.metric("Total Inventory Cost (Scenario)", round(kpis_scen["total_inventory_cost"], 0), calc_delta(kpis_base["total_inventory_cost"], kpis_scen["total_inventory_cost"]), delta_color="inverse")

st.divider()

# ------------------------------------------------
# Base Case Inventory Behaviour Chart
# ------------------------------------------------
st.subheader("Base Case Inventory Behaviour")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df_base["Date"], y=df_base["Closing Balance"], name="Closing Inventory"))
fig.add_trace(go.Scatter(x=df_base["Date"], y=df_base["Closing Balance Including Pipeline"], name="Inventory Position"))
fig.add_hline(y=base_reorder_point, line_dash="dash", annotation_text="Base Reorder Point")

stockouts = df_base[df_base["Closing Balance"] == 0]
fig.add_trace(go.Scatter(x=stockouts["Date"], y=stockouts["Closing Balance"], mode="markers", name="Stockout", marker=dict(color="red",size=9)))

reorders = df_base[df_base["New Order"] > 0]
fig.add_trace(go.Scatter(x=reorders["Date"], y=reorders["Closing Balance"], mode="markers", name="Reorder Trigger", marker=dict(color="green",symbol="triangle-up",size=10)))

fig.add_hrect(y0=0, y1=base_reorder_point*0.5, fillcolor="red", opacity=0.08)
fig.add_hrect(y0=base_reorder_point*0.5, y1=base_reorder_point, fillcolor="yellow", opacity=0.08)
fig.add_hrect(y0=base_reorder_point, y1=df_base["Closing Balance Including Pipeline"].max()*1.2, fillcolor="green", opacity=0.05)
fig.update_yaxes(rangemode="tozero")
st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------
# Data Table (Scenario Data Shown)
# ------------------------------------------------
st.subheader("Simulation Data (Scenario)")
st.dataframe(df_scen)

# ------------------------------------------------
# Demand Line Graph with Median
# ------------------------------------------------
st.subheader("Demand Trend over Time")
median_demand = df_scen["Demand"].median()

fig_demand = go.Figure()
fig_demand.add_trace(go.Scatter(
    x=df_scen["Date"], 
    y=df_scen["Demand"], 
    mode="lines", 
    name="Daily Demand",
    line=dict(color="royalblue")
))
fig_demand.add_hline(
    y=median_demand, 
    line_dash="dash", 
    line_color="orange",
    annotation_text=f"Median Demand: {median_demand:.0f}",
    annotation_position="bottom right"
)
fig_demand.update_layout(xaxis_title="Date", yaxis_title="Demand Quantity")
st.plotly_chart(fig_demand, use_container_width=True)
