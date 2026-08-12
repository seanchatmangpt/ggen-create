//! Authority-safe DSPy primitives for `ggen-create`.
//!
//! This crate is the successor of the Rust DSPy work formerly hosted at
//! `seanchatmangpt/ggen@39c5d11d961a3143b228381e0ec208344e0054c6` under
//! `crates/ggen-dspy`. The semantic kernel is preserved here while the obsolete
//! `ggen-ai`/workspace coupling is intentionally removed.
//!
//! The authority boundary is deliberate:
//!
//! - language models may manufacture predictions and candidate action intents;
//! - optimizers may manufacture candidate programs/demonstrations;
//! - `ReAct` never receives executable tool callbacks and cannot actuate;
//! - the host application remains responsible for admission, BRCE actuation,
//!   receipts, and replay.
//!
//! This makes model output a CONSTRUCT artifact, never ambient DO authority.

#![forbid(unsafe_code)]

pub mod core;
pub mod evaluate;
pub mod modules;
pub mod optimize;

pub use core::{
    Completion, DspyError, Example, Field, FieldKind, LanguageModel, ModelFuture, Module,
    ModuleFuture, Prediction, PromptRequest, Signature, Values,
};
pub use evaluate::{evaluate, EvalFuture, EvaluationSummary, ExactMatch, Metric};
pub use modules::{
    ActionIntent, ChainOfThought, Predictor, ReAct, ReactFuture, ReactTurn, ToolObservation,
};
pub use optimize::{BootstrapFewShot, LabeledFewShot, OptimizeFuture};
