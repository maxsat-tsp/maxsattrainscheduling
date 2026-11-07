//! Configuration for `maxsat_ladder_sc`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RefinementPolicy {
    /// Preserve the accepted CSOnet implementation exactly.
    Legacy,
    /// Use the new full-scan pipeline but apply every detected refinement.
    AllScanned,
    /// Limit model growth with the AGLR selector.
    Adaptive,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RescueProgressPolicy {
    /// Trigger rescue only when the bound or heuristic incumbent is stuck.
    BoundOrHeuristic,
    /// Count newly applied refinement clauses/time points as progress.
    Model,
}

/// How many soft-cost assumptions enter each SAT call. Only the final SAT
/// call containing all assumptions may supply a model to the DDD loop.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AssumptionStrategy {
    Legacy,
    Full,
    Geometric,
}

impl AssumptionStrategy {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Legacy => "legacy",
            Self::Full => "full",
            Self::Geometric => "geometric",
        }
    }

    pub(super) fn initial(self, total: usize) -> usize {
        match self {
            Self::Legacy | Self::Geometric => 20,
            Self::Full => total,
        }
    }

    pub(super) fn next(self, current: usize, total: usize) -> usize {
        match self {
            Self::Legacy => current.saturating_add(20),
            Self::Full => total,
            Self::Geometric => current.saturating_mul(2).max(1).min(total),
        }
    }
}

impl RescueProgressPolicy {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::BoundOrHeuristic => "bound-or-heuristic",
            Self::Model => "model",
        }
    }
}

impl RefinementPolicy {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Legacy => "legacy",
            Self::AllScanned => "all-scanned",
            Self::Adaptive => "adaptive",
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct AglrSettings {
    pub policy: RefinementPolicy,
    pub min_growth: usize,
    pub fraction: f64,
    pub max_wait: usize,
    pub rescue_progress: RescueProgressPolicy,
    pub heuristic_period: usize,
    pub heuristic_min_gap: usize,
    pub use_objective_bound: bool,
    pub filter_duplicates: bool,
}

impl Default for AglrSettings {
    fn default() -> Self {
        Self {
            policy: RefinementPolicy::Legacy,
            min_growth: 32,
            fraction: 0.5,
            max_wait: 5,
            rescue_progress: RescueProgressPolicy::BoundOrHeuristic,
            heuristic_period: 1,
            heuristic_min_gap: 0,
            use_objective_bound: false,
            filter_duplicates: false,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct MaxSatDddLadderScSettings {
    pub assumption_strategy: AssumptionStrategy,
    pub sparse_costs: bool,
    pub resource_orders: bool,
    /// Close three-way cycles only among resource-order bits already created.
    pub order_transitivity: bool,
    /// Lazily forbid positive temporal cycles among existing resource orders.
    pub order_cycle_cuts: bool,
    /// Charge unavoidable earliest-time costs directly; encode only residuals.
    pub extract_initial_cost: bool,
    /// Restrict original weighted cost terms by a verified feasible upper bound.
    pub use_objective_bound: bool,
    /// Fix residual soft preferences that cannot be violated within verified UB.
    pub residual_hardening: bool,
    /// Maximum extra SAT checks per core; zero preserves the published path.
    pub core_minimize_checks: usize,
    /// Native MiniSAT conflicts per extra core check; zero is unlimited.
    pub core_minimize_conflicts: usize,
    /// Extra cardinality-floor checks per new core; zero preserves legacy RC2.
    pub core_exhaust_checks: usize,
    pub use_precedence_graph: bool,
    pub use_sc_amo: bool,
    pub use_touched_clique_amo: bool,

    // ── Alternative / experimental knobs (default OFF) ───────────────────
    /// Eagerly expand long travel-time precedence chains into per-step
    /// 3-literal clauses.
    pub use_eager_chain_expansion: bool,
    /// Seed fixed precedence rows from earliest time points.
    pub seed_sc_from_earliest: bool,
    /// Pre-allocate SAT variables and monotonicity clauses for the
    /// per-visit cost-threshold time points at INIT.
    pub prealloc_cost_thresholds: bool,
    /// Conflict-refinement policy.  Defaults to `Legacy`, so the published
    /// CSOnet solver remains the unchanged command-line baseline.
    pub aglr: AglrSettings,
}

impl Default for MaxSatDddLadderScSettings {
    fn default() -> Self {
        Self {
            assumption_strategy: AssumptionStrategy::Legacy,
            sparse_costs: false,
            resource_orders: false,
            order_transitivity: false,
            order_cycle_cuts: false,
            extract_initial_cost: false,
            use_objective_bound: false,
            residual_hardening: false,
            core_minimize_checks: 0,
            core_minimize_conflicts: 0,
            core_exhaust_checks: 0,
            use_precedence_graph: true,
            use_eager_chain_expansion: false,
            use_sc_amo: true,
            use_touched_clique_amo: true,
            seed_sc_from_earliest: false,
            prealloc_cost_thresholds: false,
            aglr: AglrSettings::default(),
        }
    }
}

// ─── Tunable for SC AMO encoding ─────────────────────────────────────────
// Benchmark configuration: pairwise for n <= 5, prefix counter for n >= 6.
pub(super) const PAIRWISE_AMO_MAX_SIZE: usize = 5;

#[cfg(test)]
mod assumption_tests {
    use super::AssumptionStrategy;

    #[test]
    fn assumption_schedules_reach_the_full_set_without_skipping_termination() {
        for total in [0, 1, 19, 20, 21, 101, 1000] {
            for strategy in [AssumptionStrategy::Legacy, AssumptionStrategy::Full,
                             AssumptionStrategy::Geometric] {
                let mut count = strategy.initial(total);
                let mut calls = 1;
                while count < total {
                    let next = strategy.next(count, total);
                    assert!(next > count);
                    count = next;
                    calls += 1;
                }
                assert!(count >= total);
                if strategy == AssumptionStrategy::Full {
                    assert_eq!(calls, 1);
                }
                if strategy == AssumptionStrategy::Geometric && total == 1000 {
                    assert_eq!(calls, 7);
                }
            }
        }
    }
}
