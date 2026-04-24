# Industrial Microgrid Optimizer

**MILP-based economic dispatch for factory power systems (grid, solar, battery, diesel).**  
Minimizes operating cost using time‑of‑use tariffs, demand charges, battery degradation, and diesel constraints.  
Includes rolling horizon, backtesting, what‑if analysis, and an interactive Streamlit dashboard with **hourly operating instructions**.

---

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Input Data Format (SCADA CSV)](#input-data-format-scada-csv)
- [Algorithm Explanation](#algorithm-explanation)
- [Results & Strategy](#results--strategy)
- [Possible Extensions](#possible-extensions)
- [License](#license)

---

## Overview

This project provides a **decision support tool** for industrial facility managers. It optimises the hourly dispatch of:
- **Grid import/export** (time‑of‑use pricing)
- **Solar PV** (free but variable)
- **Battery storage** (efficiency, degradation, power limits)
- **Diesel generator** (min power, startup cost, min runtime)

The optimisation engine uses **Mixed‑Integer Linear Programming (MILP)** to find the globally optimal 24‑hour schedule that minimises total cost while meeting load exactly. A Streamlit-based user interface allows users to upload their own SCADA‑style data, adjust parameters, and obtain **actionable instructions** for each hour.

---

## Features

- **✔️ Perfect‑forecast single‑day optimisation** – optimal dispatch for a given 24h forecast.
- **✔️ Rolling horizon simulation** – mimics real‑time operation (re‑optimise each hour using updated forecasts).
- **✔️ Backtesting over historical data** – compare optimal cost against simple strategies.
- **✔️ What‑if analysis** – test different battery capacities instantly.
- **✔️ Realistic constraints**:
  - Battery round‑trip efficiency & degradation cost (per kWh or per cycle)
  - Diesel minimum power, startup cost, minimum runtime
  - Solar curtailment (waste excess when uneconomical)
  - Grid demand charge (peak import penalty)
- **✔️ Operator‑friendly output**:
  - Hourly instructions (e.g., “Run diesel at 50 kW, Charge battery at 100 kW”)
  - Reasoning behind each action
  - Interactive plots (power flows, battery SoC)
  - Cost comparison with baseline strategies (grid‑only, solar+grid)

---

## How It Works

1. **User uploads a CSV file** containing 24‑hour forecasts and actual values for load, solar, and grid prices (SCADA format).
2. **Sets parameters** in the sidebar (battery capacity, diesel costs, demand charge, etc.).
3. **Selects an analysis mode**:
   - *Single Day Optim* – optimises one day using forecast data.
   - *Rolling Horizon* – simulates real‑time operation with hourly re‑optimisation.
   - *Backtest* – runs rolling horizon over several days and reports total cost.
   - *What‑If* – sweeps battery capacity to find cost‑effective size.
4. **The MILP solver (CBC)** finds the optimal schedule.
5. **Results are displayed** as a table of instructions, summary text, and interactive plots.

---

## Installation

### Prerequisites
- Python 3.8 or higher
- Git

### Clone the repository
```bash
git clone https://github.com/yourusername/industrial-microgrid-optimizer.git
cd industrial-microgrid-optimizer
