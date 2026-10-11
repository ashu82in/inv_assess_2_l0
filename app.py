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
base_reorder_point = st.sidebar.number_input("Reorder Point", value=350, key="base_rop")
base_order_qty = st.sidebar.number_input("Order Quantity", value=300, key="base_oq")
base_unit_value = st.sidebar.number_input("Value Per Unit", value=100, key="base_uv")
base_holding_cost_percent = st.sidebar.number_input("Holding Cost (% of Value)", value=20.0, key="base_hc")
base_ordering_cost = st.sidebar.number_input("Ordering Cost Per Order", value=500, key="base_oc")
num_days = st.sidebar.slider("Simulation Days", 100, 2000, 365, key="days")

base_holding_cost_rate = base_holding_cost_percent / 100

# ------------------------------------------------
# Synchronized Demand Generation & Reset
# ------------------------------------------------
if st.sidebar.button("Reset Demand Scenario", type="primary"):
    np.random.seed()
    st.session_state.base_demand_sequence = np.maximum(
        0, np.random.normal(base_avg_demand, base_avg_demand * base_cov, num_days)
    ).round()
    st.session_state.sim_days = num_days
    st.session_state.sim_avg_demand = base_avg_demand
    st.session_state.sim_cov = base_cov
elif ("base_demand_sequence" not in st.session_state or 
      st.session_state.get("sim_days") != num_days or 
      st.session_state.get("sim_avg_demand") != base_avg_demand or 
      st.session_state.get("sim_cov") != base_cov):
    
    np.random.seed(42)
    st.session_state.base_demand_sequence = np.maximum(
        0, np.random.normal(base_avg_demand, base_avg_demand * base_cov, num_days)
    ).round()
    st.session_state.sim_days = num_days
    st.session_state.sim_avg_demand = base_avg_demand
    st.session_state.sim_cov = base_cov

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
        scen_reorder_point = s_col_a.number_input("Reorder Point", value=350, key="scen_rop")
        scen_order_qty = s_col_b.number_input("Order Quantity", value=300, key="scen_oq")
        scen_unit_value = s_col_a.number_input("Value Per Unit", value=100, key="scen_uv")
        scen_holding_cost_percent = s_col_b.number_input("Holding Cost (% of Value)", value=20.0, key="scen_hc")
        scen_ordering_cost = s_col_a.number_input("Ordering Cost Per Order", value=500, key="scen_oc")

scen_holding_cost_rate = scen_holding_cost_percent / 100

if scen_avg_demand == base_avg_demand and scen_cov == base_cov:
    scen_demand = base_demand
else:
    np.random.seed(99)
    scen_demand = np.maximum(0, np.random.normal(scen_avg_demand, scen_avg_demand * scen_cov, num_days)).round()

# ------------------------------------------------
# Simulation Function
# ------------------------------------------------
def run_simulation(demand_seq, op_bal, avg_dem, lt, rop, oq, uv, hc_rate, oc):
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
    
    # Cost Comparison Logic (EOQ inner sim)
    def sim_cost(test_oq):
        inv = op_bal
        pl_orders = []
        hc_total = 0
        orders_count = 0
        for d in range(num_days):
            rec = 0
            for ord in pl_orders.copy():
                if ord[0] == d:
                    rec += ord[1]
                    pl_orders.remove(ord)
            inv += rec
            dem_today = demand_seq[d]
            inv -= dem_today
            if inv < 0: inv = 0
            pl_qty = sum(q for arr, q in pl_orders)
            inv_pos = inv + pl_qty
            if inv_pos < rop:
                pl_orders.append((d + lt, test_oq))
                orders_count += 1
            clos_pipe = inv + sum(q for arr, q in pl_orders)
            hc_total += (clos_pipe * uv) * hc_rate / 365
        return hc_total + (orders_count * oc)

    annual_demand = avg_dem * 365
    holding_cost_per_unit = uv * hc_rate
    eoq = np.sqrt((2 * annual_demand * oc) / holding_cost_per_unit) if holding_cost_per_unit > 0 else 0
    
    cost_current_policy = sim_cost(oq)
    cost_eoq_policy = sim_cost(int(eoq))

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
    
    kpis["eoq"] = eoq
    kpis["selected_order_qty"] = oq
    kpis["cost_current"] = cost_current_policy
    kpis["cost_eoq"] = cost_eoq_policy
    kpis["savings_eoq"] = cost_current_policy - cost_eoq_policy
    
    return df, kpis

# ------------------------------------------------
# Run Simulations
# ------------------------------------------------
df_base, kpis_base = run_simulation(
    base_demand, base_opening_balance, base_avg_demand, base_lead_time, base_reorder_point, 
    base_order_qty, base_unit_value, base_holding_cost_rate, base_ordering_cost
)

df_scen, kpis_scen = run_simulation(
    scen_demand, scen_opening_balance, scen_avg_demand, scen_lead_time, scen_reorder_point, 
    scen_order_qty, scen_unit_value, scen_holding_cost_rate, scen_ordering_cost
)

def calc_delta(base, scen):
    if base == 0:
        return f"{scen - base:,.0f} (N/A)"
    diff = scen - base
    pct = (diff / base) * 100
    return f"{diff:,.0f} ({pct:+.1f}%)"

# ------------------------------------------------
# KPI Displays (Comparing Scenario to Base)
# ------------------------------------------------
st.subheader("Inventory KPIs")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Stockout Days", kpis_scen["stockout_days"], calc_delta(kpis_base["stockout_days"], kpis_scen["stockout_days"]), delta_color="inverse")
c2.metric("Average Age of Inventory", round(kpis_scen["average_age_inventory"], 1), calc_delta(kpis_base["average_age_inventory"], kpis_scen["average_age_inventory"]), delta_color="inverse")
c3.metric("Average Inventory", round(kpis_scen["average_inventory"], 0), calc_delta(kpis_base["average_inventory"], kpis_scen["average_inventory"]), delta_color="inverse")
c4.metric("Avg Working Capital", round(kpis_scen["average_working_capital"], 0), calc_delta(kpis_base["average_working_capital"], kpis_scen["average_working_capital"]), delta_color="inverse")

st.subheader("Inventory Range")
r1, r2, r3, r4 = st.columns(4)
r1.metric("Minimum Inventory", round(kpis_scen["min_inventory"], 0), calc_delta(kpis_base["min_inventory"], kpis_scen["min_inventory"]))
r2.metric("Maximum Inventory", round(kpis_scen["max_inventory"], 0), calc_delta(kpis_base["max_inventory"], kpis_scen["max_inventory"]))
r3.metric("Minimum Working Capital", round(kpis_scen["min_wc"], 0), calc_delta(kpis_base["min_wc"], kpis_scen["min_wc"]))
r4.metric("Maximum Working Capital", round(kpis_scen["max_wc"], 0), calc_delta(kpis_base["max_wc"], kpis_scen["max_wc"]))

st.subheader("Inventory Cost Metrics")
cc1, cc2, cc3 = st.columns(3)
cc1.metric("Total Holding Cost", round(kpis_scen["total_holding_cost"], 0), calc_delta(kpis_base["total_holding_cost"], kpis_scen["total_holding_cost"]), delta_color="inverse")
cc2.metric("Total Ordering Cost", round(kpis_scen["total_ordering_cost"], 0), calc_delta(kpis_base["total_ordering_cost"], kpis_scen["total_ordering_cost"]), delta_color="inverse")
cc3.metric("Total Inventory Cost", round(kpis_scen["total_inventory_cost"], 0), calc_delta(kpis_base["total_inventory_cost"], kpis_scen["total_inventory_cost"]), delta_color="inverse")

st.subheader("EOQ")
e1, e2 = st.columns(2)
e1.metric("Economic Order Quantity", round(kpis_scen["eoq"], 0), calc_delta(kpis_base["eoq"], kpis_scen["eoq"]))
e2.metric("Selected Order Quantity", kpis_scen["selected_order_qty"], calc_delta(kpis_base["selected_order_qty"], kpis_scen["selected_order_qty"]))

st.subheader("Cost Comparison")
k1, k2, k3 = st.columns(3)
k1.metric("Cost with Current Policy", round(kpis_scen["cost_current"], 0), calc_delta(kpis_base["cost_current"], kpis_scen["cost_current"]), delta_color="inverse")
k2.metric("Cost with EOQ", round(kpis_scen["cost_eoq"], 0), calc_delta(kpis_base["cost_eoq"], kpis_scen["cost_eoq"]), delta_color="inverse")
k3.metric("Savings Using EOQ", round(kpis_scen["savings_eoq"], 0), calc_delta(kpis_base["savings_eoq"], kpis_scen["savings_eoq"]))

st.divider()

# ------------------------------------------------
# Inventory Behaviour Chart (Both Cases)
# ------------------------------------------------
st.subheader("Inventory Behaviour: Base vs Scenario")
fig = go.Figure()

fig.add_trace(go.Scatter(x=df_base["Date"], y=df_base["Closing Balance"], name="Base Closing Inventory", line=dict(color='royalblue', width=2)))
fig.add_trace(go.Scatter(x=df_scen["Date"], y=df_scen["Closing Balance"], name="Scenario Closing Inventory", line=dict(color='darkorange', width=2)))

fig.add_hline(y=base_reorder_point, line_dash="dash", line_color="royalblue", annotation_text="Base Reorder Point")
if base_reorder_point != scen_reorder_point:
    fig.add_hline(y=scen_reorder_point, line_dash="dash", line_color="darkorange", annotation_text="Scenario Reorder Point")

fig.update_layout(xaxis_title="Date", yaxis_title="Inventory Units", hovermode="x unified")
fig.update_yaxes(rangemode="tozero")
st.plotly_chart(fig, use_container_width=True)

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
    line=dict(color="mediumseagreen")
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

# ------------------------------------------------
# Data Tables (Both Cases)
# ------------------------------------------------
st.subheader("Simulation Data")

tab1, tab2 = st.tabs(["Base Case Data", "Scenario Data"])

with tab1:
    st.dataframe(df_base, use_container_width=True)

with tab2:
    st.dataframe(df_scen, use_container_width=True)
