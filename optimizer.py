# optimizer.py
import pulp
import pandas as pd

def run_optimization(df, battery_params, diesel_params, grid_params, demand_charge_rate=0):
    """
    df: DataFrame with columns 'hour', 'load', 'solar', 'price_import' (and optionally 'price_export')
    Returns: (results_df, total_cost, strategy_text)
    """
    hours = df['hour'].tolist()
    load = df.set_index('hour')['load'].to_dict()
    solar = df.set_index('hour')['solar'].to_dict()
    price_import = df.set_index('hour')['price_import'].to_dict()
    
    if 'price_export' in df.columns:
        price_export = df.set_index('hour')['price_export'].to_dict()
    else:
        price_export = {h: grid_params.get('price_export', 0.08) for h in hours}
    
    allow_export = grid_params.get('allow_export', True)
    
    # Battery parameters
    E_max = battery_params['E_max']
    P_bat_max = battery_params['P_max']
    SoC_initial = battery_params['SoC_initial']
    eta_c = battery_params.get('eta_c', 0.95)
    eta_d = battery_params.get('eta_d', 0.95)
    degrade_cost = battery_params.get('degrade_cost_per_kWh', 0.01)
    # If cycle cost provided, convert (approx)
    if battery_params.get('cycle_cost'):
        degrade_cost = battery_params['cycle_cost'] / (2 * E_max)
    
    # Diesel parameters
    P_diesel_min = diesel_params['P_min']
    P_diesel_max = diesel_params['P_max']
    fuel_cost = diesel_params['fuel_cost']
    maintain_cost = diesel_params.get('maintain_cost', 0.01)
    startup_cost = diesel_params.get('startup_cost', 0)
    min_runtime = diesel_params.get('min_runtime', 1)
    
    prob = pulp.LpProblem("Microgrid_Optimization", pulp.LpMinimize)
    
    # Variables
    P_grid_in = pulp.LpVariable.dicts("P_grid_in", hours, lowBound=0)
    P_grid_out = pulp.LpVariable.dicts("P_grid_out", hours, lowBound=0)
    P_diesel = pulp.LpVariable.dicts("P_diesel", hours, lowBound=0)
    diesel_on = pulp.LpVariable.dicts("diesel_on", hours, lowBound=0, upBound=1, cat='Binary')
    P_bat_c = pulp.LpVariable.dicts("P_bat_c", hours, lowBound=0)
    P_bat_d = pulp.LpVariable.dicts("P_bat_d", hours, lowBound=0)
    SoC = pulp.LpVariable.dicts("SoC", hours, lowBound=0, upBound=E_max)
    P_solar_curtailed = pulp.LpVariable.dicts("P_solar_curtailed", hours, lowBound=0)
    P_peak = pulp.LpVariable("P_peak", lowBound=0)
    diesel_start = pulp.LpVariable.dicts("diesel_start", hours, lowBound=0, upBound=1, cat='Binary')
    
    # Objective
    cost_import = pulp.lpSum(P_grid_in[h] * price_import[h] for h in hours)
    revenue_export = pulp.lpSum(P_grid_out[h] * price_export[h] for h in hours) if allow_export else 0
    cost_diesel_fuel = pulp.lpSum(P_diesel[h] * (fuel_cost + maintain_cost) for h in hours)
    cost_diesel_startup = pulp.lpSum(diesel_start[h] * startup_cost for h in hours)
    cost_degrade = pulp.lpSum(P_bat_d[h] * degrade_cost for h in hours)
    cost_demand = demand_charge_rate * P_peak
    
    prob += cost_import - revenue_export + cost_diesel_fuel + cost_diesel_startup + cost_degrade + cost_demand
    
    # Constraints
    for h in hours:
        prob += (P_grid_in[h] - P_grid_out[h] + solar[h] - P_solar_curtailed[h] + P_diesel[h] + P_bat_d[h] - P_bat_c[h] == load[h])
        prob += P_solar_curtailed[h] <= solar[h]
        prob += P_diesel[h] <= P_diesel_max * diesel_on[h]
        prob += P_diesel[h] >= P_diesel_min * diesel_on[h]
        prob += P_bat_c[h] <= P_bat_max
        prob += P_bat_d[h] <= P_bat_max
        prob += P_peak >= P_grid_in[h]
        
        # Startup detection
        if h == hours[0]:
            prob += diesel_start[h] >= diesel_on[h]
            prob += diesel_start[h] <= diesel_on[h]
        else:
            prev_h = hours[hours.index(h)-1]
            prob += diesel_start[h] >= diesel_on[h] - diesel_on[prev_h]
            prob += diesel_start[h] <= 1 - diesel_on[prev_h]
    
    # Minimum runtime
    for i, h in enumerate(hours):
        if i + min_runtime <= len(hours):
            prob += pulp.lpSum(diesel_on[hours[j]] for j in range(i, i+min_runtime)) >= min_runtime * diesel_start[h]
    
    # SoC dynamics
    prob += SoC[hours[0]] == SoC_initial
    for i in range(len(hours)-1):
        h = hours[i]; h_next = hours[i+1]
        prob += SoC[h_next] == SoC[h] + eta_c * P_bat_c[h] - (1/eta_d) * P_bat_d[h]
    
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=60)
    prob.solve(solver)
    
    if prob.status != pulp.LpStatusOptimal:
        return None, None, "Optimization failed."
    
    # Collect results
    results = []
    for h in hours:
        results.append({
            'hour': h,
            'load': load[h],
            'solar': solar[h],
            'grid_in': P_grid_in[h].varValue,
            'grid_out': P_grid_out[h].varValue,
            'diesel': P_diesel[h].varValue,
            'diesel_on': diesel_on[h].varValue,
            'battery_charge': P_bat_c[h].varValue,
            'battery_discharge': P_bat_d[h].varValue,
            'SoC': SoC[h].varValue,
            'solar_curtailed': P_solar_curtailed[h].varValue
        })
    results_df = pd.DataFrame(results)
    total_cost = pulp.value(prob.objective)
    
    # Build textual strategy
    strategy_lines = []
    for _, row in results_df.iterrows():
        h = int(row['hour'])
        actions = []
        if row['solar_curtailed'] > 0.1:
            actions.append(f"curtail {row['solar_curtailed']:.1f} kW solar")
        if row['grid_in'] > 0.1:
            actions.append(f"import {row['grid_in']:.1f} kW from grid (${price_import[h]:.2f}/kWh)")
        if row['grid_out'] > 0.1:
            actions.append(f"export {row['grid_out']:.1f} kW (${price_export[h]:.2f}/kWh)")
        if row['diesel'] > 0.1:
            actions.append(f"run diesel at {row['diesel']:.1f} kW")
        if row['battery_charge'] > 0.1:
            actions.append(f"charge battery at {row['battery_charge']:.1f} kW")
        if row['battery_discharge'] > 0.1:
            actions.append(f"discharge battery at {row['battery_discharge']:.1f} kW")
        if not actions:
            actions.append("no action needed")
        strategy_lines.append(f"**Hour {h}:** " + ", ".join(actions) + f" → SoC ends at {row['SoC']:.1f} kWh")
    strategy_text = "\n".join(strategy_lines)
    
    return results_df, total_cost, strategy_text