# app_v3.py (fully corrected)
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from optimizer import run_optimization
from scada_interface import SCADAInterface

st.set_page_config(page_title="Industrial Energy Optimizer", layout="wide")
st.title("🏭 Industrial Microgrid Dispatch Optimizer with SCADA Integration")

# -------------------------------------------------------------------
# Sidebar parameters
st.sidebar.header("System Parameters")

# Grid
with st.sidebar.expander("🌐 Grid"):
    allow_export = st.checkbox("Allow selling to grid", value=True)
    demand_charge_rate = st.number_input("Demand Charge ($/kW per day)", value=0.0, step=1.0)
    price_export_default = st.number_input("Default Export Price ($/kWh)", value=0.08, step=0.01)

# Battery
with st.sidebar.expander("🔋 Battery"):
    E_max = st.number_input("Capacity (kWh)", value=500, step=50)
    P_bat_max = st.number_input("Max Power (kW)", value=150, step=10)
    SoC_initial = st.number_input("Initial SoC (kWh)", value=250, step=10)
    eta = st.slider("Round‑trip Efficiency (%)", 70, 100, 90) / 100
    eta_c = eta_d = eta ** 0.5
    degrade_cost = st.number_input("Degradation Cost ($/kWh discharged)", value=0.01, step=0.01, format="%.3f")
    battery_params = {'E_max': E_max, 'P_max': P_bat_max, 'SoC_initial': SoC_initial,
                      'eta_c': eta_c, 'eta_d': eta_d, 'degrade_cost_per_kWh': degrade_cost}

# Diesel
with st.sidebar.expander("🛢️ Diesel"):
    P_min = st.number_input("Min Power (kW)", value=50, step=10)
    P_max = st.number_input("Max Power (kW)", value=300, step=20)
    fuel_cost = st.number_input("Fuel Cost ($/kWh)", value=0.25, step=0.01)
    maintain_cost = st.number_input("Maintenance ($/kWh)", value=0.01, step=0.01)
    startup_cost = st.number_input("Startup Cost ($)", value=50, step=10)
    min_runtime = st.number_input("Minimum Runtime (hours)", value=2, step=1)
    diesel_params = {'P_min': P_min, 'P_max': P_max, 'fuel_cost': fuel_cost,
                     'maintain_cost': maintain_cost, 'startup_cost': startup_cost,
                     'min_runtime': min_runtime}

grid_params = {'allow_export': allow_export, 'price_export': price_export_default}

# -------------------------------------------------------------------
# File upload
uploaded_file = st.file_uploader("Upload SCADA CSV file (with forecast + actual columns)", type=["csv"])
if uploaded_file is not None:
    df_raw = pd.read_csv(uploaded_file)
    st.write("Preview of uploaded data:")
    st.dataframe(df_raw.head())
    
    required_cols = ['timestamp', 'load_forecast_kw', 'solar_forecast_kw', 
                     'price_import_forecast_usd_per_kwh', 'load_actual_kw', 
                     'solar_actual_kw', 'price_import_actual_usd_per_kwh']
    if not all(col in df_raw.columns for col in required_cols):
        st.error(f"CSV must contain: {', '.join(required_cols)}")
    else:
        st.session_state['df_raw'] = df_raw
        st.session_state['params'] = {'battery': battery_params, 'diesel': diesel_params,
                                      'grid': grid_params, 'demand_charge': demand_charge_rate}
        st.success("File loaded. Go to tabs to run optimizations.")
else:
    st.info("Upload a SCADA CSV file (see example from generate_sample_data.py).")

# -------------------------------------------------------------------
# TABS
if 'df_raw' in st.session_state:
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Single Day Optim", "🔄 Rolling Horizon", "📈 Backtest", "🔍 What‑If"])
    
    # Tab 1: Single day optimisation
    with tab1:
        st.header("Optimise a Single 24‑hour Period")
        day_offset = st.number_input("Start day (0 = first day in file)", min_value=0, value=0, step=1)
        start_idx = day_offset * 24
        df_raw = st.session_state['df_raw']
        if start_idx + 24 <= len(df_raw):
            subset = df_raw.iloc[start_idx:start_idx+24].copy()
            subset['hour'] = list(range(24))
            forecast_df = subset.rename(columns={
                'load_forecast_kw': 'load',
                'solar_forecast_kw': 'solar',
                'price_import_forecast_usd_per_kwh': 'price_import',
                'price_export_forecast_usd_per_kwh': 'price_export'
            })
            if 'price_export' not in forecast_df.columns:
                forecast_df['price_export'] = price_export_default
            
            if st.button("Run Single Day Optimisation"):
                results, cost, strategy = run_optimization(forecast_df[['hour','load','solar','price_import','price_export']],
                                                           battery_params, diesel_params, grid_params, demand_charge_rate)
                if results is not None:
                    st.metric("Optimal Total Cost", f"${cost:.2f}")
                    
                    # ---------------------------
                    # 1. Create Actionable Schedule Table
                    # ---------------------------
                    schedule = []
                    for _, row in results.iterrows():
                        h = int(row['hour'])
                        actions = []
                        if row['grid_in'] > 0.1:
                            actions.append(f"Import {row['grid_in']:.1f} kW from grid")
                        if row['grid_out'] > 0.1:
                            actions.append(f"Export {row['grid_out']:.1f} kW to grid")
                        if row['diesel'] > 0.1:
                            actions.append(f"Run diesel at {row['diesel']:.1f} kW")
                        if row['battery_charge'] > 0.1:
                            actions.append(f"Charge battery at {row['battery_charge']:.1f} kW")
                        if row['battery_discharge'] > 0.1:
                            actions.append(f"Discharge battery at {row['battery_discharge']:.1f} kW")
                        if row['solar_curtailed'] > 0.1:
                            actions.append(f"Curtail {row['solar_curtailed']:.1f} kW solar")
                        if not actions:
                            actions.append("No active generation/storage")
                        
                        reason = ""
                        if row['battery_charge'] > 0.1:
                            reason = "Cheap energy available (solar or low grid price)"
                        elif row['battery_discharge'] > 0.1:
                            reason = "High grid price – use stored energy"
                        elif row['diesel'] > 0.1 and row['grid_in'] < 0.1:
                            reason = "Grid price too high or import limited"
                        else:
                            reason = "Grid import at current time-of-use price"
                        
                        schedule.append({
                            "Hour": h,
                            "Action": "; ".join(actions),
                            "Reasoning": reason,
                            "End SoC (kWh)": round(row['SoC'], 1)
                        })
                    
                    schedule_df = pd.DataFrame(schedule)
                    st.subheader("📋 Hourly Operating Instructions")
                    st.dataframe(schedule_df, use_container_width=True)
                    
                    # ---------------------------
                    # 2. Overall Strategy Summary
                    # ---------------------------
                    st.subheader("📌 Overall Strategy Summary")
                    total_charge = results['battery_charge'].sum()
                    total_discharge = results['battery_discharge'].sum()
                    solar_used = results['solar'].sum() - results['solar_curtailed'].sum()
                    diesel_hours = (results['diesel'] > 0.1).sum()
                    summary_text = f"""
                    - **Battery** cycled {total_discharge:.1f} kWh discharged, {total_charge:.1f} kWh charged.  
                    - **Solar** generated {results['solar'].sum():.1f} kWh, used {solar_used:.1f} kWh, curtailed {results['solar_curtailed'].sum():.1f} kWh.  
                    - **Diesel** used for {diesel_hours} hours (total {results['diesel'].sum():.1f} kWh).  
                    - **Grid import** totalled {results['grid_in'].sum():.1f} kWh; export {results['grid_out'].sum():.1f} kWh.
                    
                    **Key decisions:**  
                    - Battery charges when grid price is low or solar is abundant.  
                    - Battery discharges during peak price hours.  
                    - Diesel only starts when required to meet demand and grid price > diesel cost.  
                    - Solar curtailed if battery full and export price unattractive.
                    """
                    st.markdown(summary_text)
                    
                    # ---------------------------
                    # 3. Plots
                    # ---------------------------
                    st.subheader("📊 Power Dispatch Plot")
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=results['hour'], y=results['grid_in'], name='Grid Import', mode='lines+markers'))
                    fig.add_trace(go.Scatter(x=results['hour'], y=results['grid_out'], name='Grid Export', mode='lines+markers'))
                    fig.add_trace(go.Scatter(x=results['hour'], y=results['diesel'], name='Diesel', mode='lines+markers'))
                    fig.add_trace(go.Scatter(x=results['hour'], y=results['battery_discharge'], name='Battery Discharge', mode='lines+markers'))
                    fig.add_trace(go.Scatter(x=results['hour'], y=-results['battery_charge'], name='Battery Charge (neg)', mode='lines+markers'))
                    fig.update_layout(xaxis_title="Hour", yaxis_title="kW")
                    st.plotly_chart(fig, use_container_width=True)
                    
                    fig2 = go.Figure()
                    fig2.add_trace(go.Scatter(x=results['hour'], y=results['SoC'], name='SoC', mode='lines+markers', fill='tozeroy'))
                    fig2.update_layout(title="Battery State of Charge", xaxis_title="Hour", yaxis_title="kWh")
                    st.plotly_chart(fig2, use_container_width=True)
                    
                    with st.expander("View raw hourly data"):
                        st.dataframe(results.round(1))
                else:
                    st.error("Optimization failed. Check constraints.")
        else:
            st.warning("Not enough data for the selected start day.")
    
    # Tab 2: Rolling horizon simulation
    with tab2:
        st.header("Real‑Time Rolling Horizon Simulation")
        days = st.number_input("Number of days to simulate", min_value=1, max_value=7, value=3, step=1)
        if st.button("Run Rolling Horizon"):
            scada = SCADAInterface(st.session_state['df_raw'], battery_params, diesel_params, grid_params, demand_charge_rate)
            total_cost, decisions_df = scada.rolling_horizon_simulation(start_idx=0)
            st.success(f"Total cost over {len(decisions_df)} hours: ${total_cost:.2f}")
            st.dataframe(decisions_df)
            if not decisions_df.empty:
                decisions_df['cumulative_cost'] = decisions_df['hourly_cost'].cumsum()
                fig = px.line(decisions_df, x='timestamp', y='cumulative_cost', title="Cumulative Cost Over Time")
                st.plotly_chart(fig)
    
    # Tab 3: Backtest
    with tab3:
        st.header("Backtest over Historical Data")
        days = st.number_input("Days to backtest", min_value=1, max_value=30, value=7, step=1)
        if st.button("Run Backtest"):
            scada = SCADAInterface(st.session_state['df_raw'], battery_params, diesel_params, grid_params, demand_charge_rate)
            total_cost, daily_costs = scada.backtest(start_idx=0, days=days)
            st.metric(f"Total cost over {days} days", f"${total_cost:.2f}")
            st.dataframe(daily_costs)
            if not daily_costs.empty:
                fig = px.bar(daily_costs, x='day', y='cost', title="Daily Cost")
                st.plotly_chart(fig)
    
    # Tab 4: What‑If
    with tab4:
        st.header("What‑If: Battery Capacity Sweep")
        min_size = st.number_input("Min battery (kWh)", value=200, step=50)
        max_size = st.number_input("Max battery (kWh)", value=1000, step=50)
        step_size = st.number_input("Step (kWh)", value=100, step=50)
        if st.button("Run What‑If Analysis"):
            sizes = list(range(min_size, max_size+1, step_size))
            scada = SCADAInterface(st.session_state['df_raw'], battery_params, diesel_params, grid_params, demand_charge_rate)
            results_df = scada.what_if_battery_size(sizes, start_idx=0, days=7)
            st.dataframe(results_df)
            if not results_df.empty:
                fig = px.line(results_df, x='battery_kwh', y='7_day_cost_usd', markers=True,
                              title="Total Cost vs Battery Capacity")
                st.plotly_chart(fig)