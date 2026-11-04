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
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct MaxSatDddLadderScSettings {
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
