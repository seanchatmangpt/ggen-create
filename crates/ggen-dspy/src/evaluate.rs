use std::future::Future;
use std::pin::Pin;

use crate::core::{DspyError, Example, Module, Prediction};

/// A bounded metric. Scores must be finite and inside [0, 1].
pub trait Metric: Send + Sync {
    fn score(&self, example: &Example, prediction: &Prediction) -> Result<f64, DspyError>;
}

/// Exact match across all expected output fields.
#[derive(Clone, Copy, Debug, Default)]
pub struct ExactMatch;

impl Metric for ExactMatch {
    fn score(&self, example: &Example, prediction: &Prediction) -> Result<f64, DspyError> {
        let matches = example
            .outputs
            .iter()
            .all(|(field, expected)| prediction.outputs.get(field) == Some(expected));
        Ok(if matches { 1.0 } else { 0.0 })
    }
}

/// Evidence emitted by an evaluation pass.
#[derive(Clone, Debug, PartialEq)]
pub struct EvaluationSummary {
    pub total: usize,
    pub passed: usize,
    pub mean_score: f64,
    pub scores: Vec<f64>,
}

/// Historical named metric value.
#[derive(Clone, Debug, PartialEq)]
pub struct MetricValue {
    pub name: String,
    pub value: f64,
}

/// Aggregate metrics compatible with the historical evaluator surface.
#[derive(Clone, Debug, PartialEq)]
pub struct EvaluationMetrics {
    pub total: usize,
    pub passed: usize,
    pub pass_rate: f64,
    pub mean_score: f64,
}

impl From<&EvaluationSummary> for EvaluationMetrics {
    fn from(summary: &EvaluationSummary) -> Self {
        Self {
            total: summary.total,
            passed: summary.passed,
            pass_rate: if summary.total == 0 {
                0.0
            } else {
                summary.passed as f64 / summary.total as f64
            },
            mean_score: summary.mean_score,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct EvaluationResult {
    pub summary: EvaluationSummary,
    pub metrics: EvaluationMetrics,
    pub named: Vec<MetricValue>,
}

impl EvaluationResult {
    pub fn from_summary(summary: EvaluationSummary) -> Self {
        let metrics = EvaluationMetrics::from(&summary);
        let named = vec![
            MetricValue {
                name: "mean_score".to_owned(),
                value: metrics.mean_score,
            },
            MetricValue {
                name: "pass_rate".to_owned(),
                value: metrics.pass_rate,
            },
        ];
        Self {
            summary,
            metrics,
            named,
        }
    }
}

pub struct Evaluator<'a> {
    metric: &'a dyn Metric,
}

impl<'a> Evaluator<'a> {
    pub fn new(metric: &'a dyn Metric) -> Self {
        Self { metric }
    }

    pub fn run<'b>(
        &'b self,
        module: &'b dyn Module,
        examples: &'b [Example],
    ) -> EvaluationFuture<'b> {
        Box::pin(async move {
            let summary = evaluate(module, examples, self.metric).await?;
            Ok(EvaluationResult::from_summary(summary))
        })
    }
}

pub type EvalFuture<'a> =
    Pin<Box<dyn Future<Output = Result<EvaluationSummary, DspyError>> + Send + 'a>>;
pub type EvaluationFuture<'a> =
    Pin<Box<dyn Future<Output = Result<EvaluationResult, DspyError>> + Send + 'a>>;

/// Evaluate one module against a fixed example set.
pub fn evaluate<'a>(
    module: &'a dyn Module,
    examples: &'a [Example],
    metric: &'a dyn Metric,
) -> EvalFuture<'a> {
    Box::pin(async move {
        let mut scores = Vec::with_capacity(examples.len());
        for example in examples {
            let prediction = module.forward(&example.inputs).await?;
            let score = metric.score(example, &prediction)?;
            validate_score(score)?;
            scores.push(score);
        }

        let total = scores.len();
        let passed = scores.iter().filter(|score| **score >= 1.0).count();
        let mean_score = if scores.is_empty() {
            0.0
        } else {
            scores.iter().sum::<f64>() / total as f64
        };

        Ok(EvaluationSummary {
            total,
            passed,
            mean_score,
            scores,
        })
    })
}

pub(crate) fn validate_score(score: f64) -> Result<(), DspyError> {
    if !score.is_finite() || !(0.0..=1.0).contains(&score) {
        return Err(DspyError::Metric(format!(
            "score must be finite and inside [0, 1], got {score}"
        )));
    }
    Ok(())
}
