# Sequential-Counter MaxSAT Encodings and Precedence Propagation for Dynamic Discretization Discovery in Train Rescheduling

This repository contains the official Rust implementation of the train rescheduling algorithms, benchmark datasets, and experimental results for the paper:

> **Sequential-Counter MaxSAT Encodings and Precedence Propagation for Dynamic Discretization Discovery in Train Rescheduling**

The project implements a strengthened MaxSAT-based Dynamic Discretization Discovery (MaxSAT-DDD) framework for fixed-route train rescheduling. It evaluates and compares several solver configurations (including MaxSAT, Incremental SAT, Pure SAT, MILP, and CP baselines) across 72 problem instances and 3 delay-cost objectives (stepwise, rounded linear, and continuous linear).

## Repository Structure

- `src/` and `crates/`: Rust source code for the MaxSAT-DDD solver and the baselines (MIP-DDD, Big-$M$, and CP).
- `instances/`: The benchmark datasets (72 instances in total, under three infrastructure abstractions: `original`, `track`, and `station`).
- `results/` and `2026-05-16-Verified-Result-For-Graduation-Thesis/`: Raw experimental outputs in CSV and JSON formats, matching the results tables in the paper.
- `quick_scripts/`: Bash and Python utility scripts to run benchmarks, ablation studies, post-processing, and plotting.

## Installation

### Prerequisites

- **Operating System**: Linux (Ubuntu 22.04 recommended). On Windows, install via WSL2.
- **Rust Toolchain**: 1.83 or newer (`rustup install stable`)
- **Gurobi Optimizer**: version 12.0 with a valid license (free academic license available)
- **Python 3**: for analysis and plotting scripts (3.10+ recommended)
- **GCC / Build Tools**: `build-essential` package

### Step 1: Clone External Solver Dependencies

The project links against external SAT/MaxSAT solvers built from source. Clone them as **siblings** of this repository:

```bash
cd ~/projects   # or your preferred projects directory
git clone https://github.com/maxsat-tsp/maxsattrainscheduling.git
git clone https://github.com/luteberget/salvers.git
git clone https://github.com/arminbiere/cadical.git
git clone https://github.com/marekpiotrow/uwrmaxsat.git
git clone https://github.com/biotomas/ipamir.git ipamir-rs
```

### Step 2: Build External Solvers

```bash
# CaDiCaL
cd ~/projects/cadical
./configure && make -j$(nproc)

# UWrMaxSat (requires CaDiCaL built first)
cd ~/projects/uwrmaxsat
make build_release -j$(nproc)

# IPAMIR Rust bindings
cd ~/projects/ipamir-rs
cargo build --release
```

### Step 3: Set up Gurobi

1. Download Gurobi 12.0 from [gurobi.com](https://www.gurobi.com/downloads/)
2. Install it and acquire a license (academic free)
3. Export environment variables (e.g., in `~/.bashrc`):

```bash
export GUROBI_HOME="/opt/gurobi1200/linux64"
export PATH="${PATH}:${GUROBI_HOME}/bin"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${GUROBI_HOME}/lib"
export GRB_LICENSE_FILE="$HOME/gurobi.lic"
```

### Step 4: Configure Link Paths

The build system links against external solver libraries via `.cargo/config.toml`. Edit this file to match your installation paths:

```toml
[build]
rustflags = [
  "-L", "/path/to/ipamir-rs",
  "-L", "/path/to/uwrmaxsat/build/release/lib",
  "-L", "/path/to/cadical/build",
  "-L", "/path/to/gurobi/lib",
  "-l", "cadical",
]
```

### Step 5: Build the Project

```bash
cd ~/projects/maxsattrainscheduling
cargo build --release
```

The compiled binary will be located at `target/release/ddd`.

---

## Reproducing Paper Results

To reproduce the benchmarks and ablation studies shown in the paper:

1. **Activate Environment Settings:**
   ```bash
   source quick_scripts/activation.txt
   ```

2. **Run MaxSAT-Default (Proposed Method):**
   ```bash
   bash quick_scripts/bench/maxsat_default.sh
   ```

3. **Run Baselines:**
   - **MaxSAT Baseline (Croella et al. 2024):**
     ```bash
     bash quick_scripts/bench/maxsat_baseline.sh
     ```
   - **MILP Baselines (Big-$M$ and MIP-DDD):**
     ```bash
     bash quick_scripts/bench/milp_objectives_separate.sh
     ```

4. **Run Ablation Studies & Plotting:**
   Run the ablation benchmark and generate the ablation figures:
   ```bash
   bash quick_scripts/bench/maxsat_ablation.sh
   python3 quick_scripts/analyze/plot_4config_hard_groups.py
   ```
   The generated figures will be saved under the results directory.
