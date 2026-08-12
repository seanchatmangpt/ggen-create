use std::future::Future;
use std::pin::Pin;

use crate::core::{DspyError, Example, Module};
use crate::evaluate::{validate_score, Metric};
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
///
/// Teacher predictions are evaluated first. Only predictions admitted by the metric threshold
/// become demonstrations. The optimizer manufactures a new Predictor; it does not mutate or
/// actuate external state.
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
                    let admitted =
                        Example::new(example.inputs.clone(), prediction.outputs.clone());
                    student.signature().validate_example(&admitted)?;
                    demonstrations.push(admitted);
                }
            }

            student.clone().with_demonstrations(demonstrations)
        })
    }
}

pub type OptimizeFuture<'a> =
    Pin<Box<dyn Future<Output = Result<Predictor, DspyError>> + Send + 'a>>;
