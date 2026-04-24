# scada_interface.py
import pandas as pd
from optimizer import run_optimization

class SCADAInterface:
    def __init__(self, data_source, battery_params, diesel_params, grid_params, demand_charge_rate):
        """
        data_source: either a file path (string) or a pandas DataFrame already loaded.
        """
        if isinstance(data_source, str):
            self.df = pd.read_csv(data_source, parse_dates=['timestamp'])
        else:
            self.df = data_source.copy()
        self.battery_params = battery_params
        self.diesel_params = diesel_params
        self.grid_params = grid_params
        self.demand_charge_rate = demand_charge_rate

        # Ensure required columns
        required = ['load_forecast_kw', 'solar_forecast_kw', 'price_import_forecast_usd_per_kwh',
                    'load_actual_kw', 'solar_actual_kw', 'price_import_actual_usd_per_kwh']
        for col in required:
            if col not in self.df.columns:
                raise ValueError(f"Missing column: {col}")
        if 'price_export_forecast_usd_per_kwh' not in self.df.columns:
            self.df['price_export_forecast_usd_per_kwh'] = self.grid_params.get('price_export', 0.08)

    def get_forecast_dataframe(self, start_idx):
        if start_idx + 24 > len(self.df):
            return None
        subset = self.df.iloc[start_idx:start_idx+24].copy()
        subset['hour'] = list(range(24))
        subset = subset.rename(columns={
            'load_forecast_kw': 'load',
            'solar_forecast_kw': 'solar',
            'price_import_forecast_usd_per_kwh': 'price_import',
            'price_export_forecast_usd_per_kwh': 'price_export'
        })
        return subset[['hour', 'load', 'solar', 'price_import', 'price_export']]

    def rolling_horizon_simulation(self, start_idx=0):
        total_cost = 0.0
        decisions = []
        current_idx = start_idx
        while current_idx < len(self.df):
            forecast_df = self.get_forecast_dataframe(current_idx)
            if forecast_df is None:
                break
            opt_df, _, _ = run_optimization(forecast_df, self.battery_params,
                                             self.diesel_params, self.grid_params,
                                             self.demand_charge_rate)
            if opt_df is None:
                print(f"Optimization failed at index {current_idx}")
                break
            first = opt_df.iloc[0]
            actual_price_import = self.df.iloc[current_idx]['price_import_actual_usd_per_kwh']
            actual_export_price = self.grid_params.get('price_export', 0.08)
            hourly_cost = (first['grid_in'] * actual_price_import -
                           first['grid_out'] * actual_export_price +
                           first['diesel'] * (self.diesel_params['fuel_cost'] + self.diesel_params.get('maintain_cost',0)) +
                           first['battery_discharge'] * self.battery_params.get('degrade_cost_per_kWh',0))
            total_cost += hourly_cost
            decisions.append({
                'timestamp': self.df.iloc[current_idx]['timestamp'],
                'grid_in': first['grid_in'],
                'grid_out': first['grid_out'],
                'diesel': first['diesel'],
                'battery_charge': first['battery_charge'],
                'battery_discharge': first['battery_discharge'],
                'actual_load': self.df.iloc[current_idx]['load_actual_kw'],
                'actual_solar': self.df.iloc[current_idx]['solar_actual_kw'],
                'hourly_cost': hourly_cost
            })
            current_idx += 1
        return total_cost, pd.DataFrame(decisions)

    def backtest(self, start_idx=0, days=7):
        total_cost = 0.0
        results_per_day = []
        for day in range(days):
            day_cost, _ = self.rolling_horizon_simulation(start_idx + day*24)
            total_cost += day_cost
            results_per_day.append({'day': day+1, 'cost': day_cost})
        return total_cost, pd.DataFrame(results_per_day)

    def what_if_battery_size(self, sizes_kwh, start_idx=0, days=7):
        results = []
        original_capacity = self.battery_params['E_max']
        for size in sizes_kwh:
            self.battery_params['E_max'] = size
            total_cost, _ = self.backtest(start_idx, days)
            results.append({'battery_kwh': size, f'{days}_day_cost_usd': total_cost})
        self.battery_params['E_max'] = original_capacity
        return pd.DataFrame(results)