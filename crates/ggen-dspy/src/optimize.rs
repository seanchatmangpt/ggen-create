use std::future::Future;
use std::pin::Pin;

use crate::core::{DspyError, Example, Module, Values};
use crate::evaluate::{evaluate, validate_score, EvaluationSummary, Metric};
use crate::modules::Predictor;

/// Deterministic labeled few-shot compiler.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LabeledFewShot {
    pub max_examples: usize,
}

impl LabeledFewShot {
    pub fn new(max_examples: usize) -> Self {
        Self { max_examples }
    }

    pub fn compile(
        &self,
        student: &Predictor,
        examples: &[Example],
    ) -> Result<Predictor, DspyError> {
        student
            .clone()
            .with_demonstrations(examples.iter().take(self.max_examples).cloned().collect())
    }
}

/// Bootstrap few-shot optimizer.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct BootstrapFewShot {
    pub max_bootstrapped: usize,
    pub min_score: f64,
}

impl BootstrapFewShot {
    pub fn new(max_bootstrapped: usize, min_score: f64) -> Result<Self, DspyError> {
        validate_score(min_score)?;
        Ok(Self {
            max_bootstrapped,
            min_score,
        })
    }

    pub fn compile<'a>(
        &'a self,
        student: &'a Predictor,
        teacher: &'a dyn Module,
        training: &'a [Example],
        metric: &'a dyn Metric,
    ) -> OptimizeFuture<'a> {
        Box::pin(async move {
            let mut demonstrations = Vec::new();

            for example in training {
                if demonstrations.len() >= self.max_bootstrapped {
                    break;
                }

                let prediction = teacher.forward(&example.inputs).await?;
                let score = metric.score(example, &prediction)?;
                validate_score(score)?;
                if score >= self.min_score {
                    let admitted = Example::new(example.inputs.clone(), prediction.outputs.clone());
                    student.signature().validate_example(&admitted)?;
                    demonstrations.push(admitted);
                }
            }

            student.clone().with_demonstrations(demonstrations)
        })
    }
}

/// Optimizer settings retained from the historical Rust DSPy surface.
#[derive(Clone, Debug, PartialEq)]
pub struct OptimizerConfig {
    pub num_examples: usize,
    pub max_iterations: usize,
    pub convergence_threshold: f64,
    pub verbose: bool,
    pub seed: Option<u64>,
}

impl Default for OptimizerConfig {
    fn default() -> Self {
        Self {
            num_examples: 5,
            max_iterations: 10,
            convergence_threshold: 0.01,
            verbose: false,
            seed: None,
        }
    }
}

impl OptimizerConfig {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_num_examples(mut self, num_examples: usize) -> Self {
        self.num_examples = num_examples;
        self
    }

    pub fn with_max_iterations(mut self, max_iterations: usize) -> Self {
        self.max_iterations = max_iterations;
        self
    }

    pub fn with_convergence_threshold(mut self, threshold: f64) -> Result<Self, DspyError> {
        validate_score(threshold)?;
        self.convergence_threshold = threshold;
        Ok(self)
    }

    pub fn with_verbose(mut self, verbose: bool) -> Self {
        self.verbose = verbose;
        self
    }

    pub fn with_seed(mut self, seed: u64) -> Self {
        self.seed = Some(seed);
        self
    }
}

/// Historical training-example shape, convertible to the canonical [`Example`].
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TrainExample {
    pub inputs: Values,
    pub outputs: Values,
}

impl TrainExample {
    pub fn new(inputs: Values, outputs: Values) -> Self {
        Self { inputs, outputs }
    }

    pub fn from_pairs(inputs: &[(&str, &str)], outputs: &[(&str, &str)]) -> Self {
        Self {
            inputs: inputs
                .iter()
                .map(|(key, value)| ((*key).to_owned(), (*value).to_owned()))
                .collect(),
            outputs: outputs
                .iter()
                .map(|(key, value)| ((*key).to_owned(), (*value).to_owned()))
                .collect(),
        }
    }

    pub fn as_example(&self) -> Example {
        Example::new(self.inputs.clone(), self.outputs.clone())
    }
}

/// Shared compile boundary for program optimizers.
pub trait Optimizer: Send + Sync {
    fn name(&self) -> &str;

    fn compile<'a>(
        &'a self,
        student: &'a Predictor,
        training: &'a [Example],
        metric: &'a dyn Metric,
    ) -> OptimizeFuture<'a>;
}

/// Bounded MIPRO-style instruction search.
///
/// This implementation deliberately searches a finite, explicit candidate set. It manufactures
/// the best observed Predictor and never actuates tools or external state.
#[derive(Clone, Debug)]
pub struct MiproOptimizer {
    pub config: OptimizerConfig,
    pub candidate_instructions: Vec<String>,
}

impl MiproOptimizer {
    pub fn new(config: OptimizerConfig) -> Self {
        Self {
            config,
            candidate_instructions: Vec::new(),
        }
    }

    pub fn with_candidates(
        mut self,
        candidates: impl IntoIterator<Item = String>,
    ) -> Self {
        self.candidate_instructions = candidates.into_iter().collect();
        self
    }
}

impl Optimizer for MiproOptimizer {
    fn name(&self) -> &str {
        "MIPRO"
    }

    fn compile<'a>(
        &'a self,
        student: &'a Predictor,
        training: &'a [Example],
        metric: &'a dyn Metric,
    ) -> OptimizeFuture<'a> {
        Box::pin(async move {
            let mut best = student.clone();
            let mut best_score = evaluate(student, training, metric).await?.mean_score;
            let candidates = self
                .candidate_instructions
                .iter()
                .take(self.config.max_iterations.max(1));

            for instructions in candidates {
                let candidate = student.with_instructions(instructions.clone());
                let score = evaluate(&candidate, training, metric).await?.mean_score;
                if score > best_score + self.config.convergence_threshold {
                    best = candidate;
                    best_score = score;
                }
            }

            Ok(best)
        })
    }
}

/// Evidence from optimizer selection.
#[derive(Clone, Debug, PartialEq)]
pub struct OptimizationReceipt {
    pub optimizer: String,
    pub baseline: EvaluationSummary,
    pub candidate: EvaluationSummary,
    pub improved: bool,
}

pub type OptimizeFuture<'a> =
    Pin<Box<dyn Future<Output = Result<Predictor, DspyError>> + Send + 'a>>;
