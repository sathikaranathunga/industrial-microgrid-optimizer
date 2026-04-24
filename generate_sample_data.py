# generate_sample_data.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_scada_csv(days=7, output_file='scada_data.csv'):
    start = datetime(2025,4,1)
    hours = [start + timedelta(hours=i) for i in range(24*days)]
    
    def load_pattern(hour_of_day):
        base = 200
        peak = 150
        return base + peak * np.sin(np.pi * (hour_of_day - 8)/12) + np.random.normal(0, 5)
    
    def solar_pattern(hour_of_day):
        if 6 <= hour_of_day <= 18:
            return max(0, 100 * np.sin(np.pi * (hour_of_day - 6)/12) + np.random.normal(0, 5))
        return 0
    
    def price_import_pattern(hour_of_day):
        if hour_of_day < 6:
            return 0.10
        elif hour_of_day < 16:
            return 0.14
        else:
            return 0.22
    
    df = pd.DataFrame({'timestamp': hours})
    df['hour_of_day'] = df['timestamp'].dt.hour
    
    # Forecasts
    df['load_forecast_kw'] = df['hour_of_day'].apply(load_pattern)
    df['solar_forecast_kw'] = df['hour_of_day'].apply(solar_pattern)
    df['price_import_forecast_usd_per_kwh'] = df['hour_of_day'].apply(price_import_pattern)
    df['price_export_forecast_usd_per_kwh'] = 0.08
    
    # Actuals (add small random error)
    df['load_actual_kw'] = df['load_forecast_kw'] + np.random.normal(0, 3, len(df))
    df['solar_actual_kw'] = df['solar_forecast_kw'] * np.random.uniform(0.9, 1.1, len(df))
    df['price_import_actual_usd_per_kwh'] = df['price_import_forecast_usd_per_kwh'] + np.random.normal(0, 0.01, len(df))
    
    # Ensure no negative loads
    df['load_actual_kw'] = df['load_actual_kw'].clip(lower=0)
    df['solar_actual_kw'] = df['solar_actual_kw'].clip(lower=0)
    
    df.to_csv(output_file, index=False)
    print(f"Sample SCADA CSV with {days} days saved to {output_file}")

if __name__ == "__main__":
    generate_scada_csv(days=7)