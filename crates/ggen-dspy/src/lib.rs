//! Authority-safe Rust DSPy for `ggen-create`.
//!
//! Provenance: the semantic surface descends from
//! `seanchatmangpt/ggen@39c5d11d961a3143b228381e0ec208344e0054c6/crates/ggen-dspy`.
//! That historical crate proved the Rust DSPy direction but was coupled to the former ggen
//! workspace and allowed agent patterns to cross execution boundaries directly.
//!
//! This migration preserves the useful public capability families while applying ggen-create's
//! current authority law:
//!
//! - model and optimizer output is CONSTRUCT-only;
//! - ReAct manufactures typed [`ActionIntent`] values rather than executing tools;
//! - ProgramOfThought manufactures [`CodeIntent`] values rather than executing code;
//! - the host broker remains the exclusive DO path and owns admission, actuation, receipts,
//!   replay, and standing.

#![forbid(unsafe_code)]

pub mod adapters;
pub mod assertions;
pub mod config;
pub mod core;
pub mod evaluate;
pub mod modules;
pub mod optimize;
pub mod patterns;

pub use adapters::{
    AdapterWithFallback, ChatAdapter, CompletionAdapter, CompletionRequest, Demonstration,
    DummyLM, GgenAiAdapter, IntegratedAdapter, JSONAdapter, LlmAdapter, ModelUsage, RetryConfig,
    TokenCounter, TokenStats,
};
pub use assertions::{Assert, AssertionError, Suggest};
pub use config::{
    get_dspy_config, init_dspy_config, with_context, CacheConfig, CacheManager, CacheStats,
    ContextBuilder, DspyContext, DspySettings, UsageStats, UsageTracker,
};
pub use core::{
    Completion, DspyError, Example, Field, FieldKind, InputField, LanguageModel, ModelFuture,
    Module, ModuleContext, ModuleFuture, ModuleOutput, OutputField, Prediction, PromptRequest,
    Result, Signature, SignatureBuilder, Values,
};
pub use evaluate::{
    evaluate, EvalFuture, EvaluationFuture, EvaluationMetrics, EvaluationResult,
    EvaluationSummary, Evaluator, ExactMatch, Metric, MetricValue,
};
pub use modules::{
    ActionIntent, BaleenBuilder, BaleenConfig, BaleenHop, ChainOfThought, CodeIntent,
    CodeLanguage, ExecutionResult, HopState, InMemoryRetriever, MultiHopConfig, MultiHopQA,
    MultiHopQABuilder, Passage, Predictor, ProgramIntentFuture, ProgramOfThought,
    ProgramOfThoughtBuilder, ProgramOfThoughtConfig, ReAct, ReactAgent, ReactFuture, ReactTurn,
    Retrieve, RetrieveBuilder, RetrieverBackend, SimplifiedBaleen, Tool, ToolObservation,
};
pub use optimize::{
    BootstrapFewShot, LabeledFewShot, MiproOptimizer, OptimizationReceipt, OptimizeFuture,
    Optimizer, OptimizerConfig, TrainExample,
};
pub use patterns::{AgentPattern, PatternBuilder, PatternLibrary, PatternSpec};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
