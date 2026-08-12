use std::sync::Arc;

use crate::core::{
    Completion, DspyError, Example, LanguageModel, ModelFuture, PromptRequest, Values,
};

/// Historical adapter trait name. Adapters are inference-only language models.
pub trait LlmAdapter: LanguageModel {}

impl<T> LlmAdapter for T where T: LanguageModel + ?Sized {}

/// Structured completion request retained for compatibility.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CompletionRequest {
    pub prompt: String,
    pub metadata: Values,
}

impl CompletionRequest {
    pub fn new(prompt: impl Into<String>) -> Self {
        Self {
            prompt: prompt.into(),
            metadata: Values::new(),
        }
    }

    pub fn into_prompt_request(self) -> PromptRequest {
        PromptRequest {
            prompt: self.prompt,
            metadata: self.metadata,
        }
    }
}

/// Historical demonstration name.
pub type Demonstration = Example;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct ModelUsage {
    pub prompt_tokens: u64,
    pub completion_tokens: u64,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct TokenStats {
    pub characters: usize,
    pub estimated_tokens: usize,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct TokenCounter;

impl TokenCounter {
    pub fn count(&self, text: &str) -> TokenStats {
        TokenStats {
            characters: text.chars().count(),
            estimated_tokens: text.split_whitespace().count(),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RetryConfig {
    pub max_attempts: usize,
}

impl Default for RetryConfig {
    fn default() -> Self {
        Self { max_attempts: 2 }
    }
}

/// Compatibility adapter named after the old ggen-ai integration point.
///
/// It now wraps the target's explicit [`LanguageModel`] boundary instead of importing the
/// historical ggen-ai workspace, removing that dependency while preserving the adapter role.
#[derive(Clone)]
pub struct GgenAiAdapter {
    inner: Arc<dyn LanguageModel>,
}

impl GgenAiAdapter {
    pub fn new(inner: Arc<dyn LanguageModel>) -> Self {
        Self { inner }
    }
}

impl LanguageModel for GgenAiAdapter {
    fn complete<'a>(&'a self, request: &'a PromptRequest) -> ModelFuture<'a> {
        self.inner.complete(request)
    }
}

#[derive(Clone)]
pub struct CompletionAdapter {
    inner: GgenAiAdapter,
}

impl CompletionAdapter {
    pub fn new(model: Arc<dyn LanguageModel>) -> Self {
        Self {
            inner: GgenAiAdapter::new(model),
        }
    }
}

impl LanguageModel for CompletionAdapter {
    fn complete<'a>(&'a self, request: &'a PromptRequest) -> ModelFuture<'a> {
        self.inner.complete(request)
    }
}

#[derive(Clone)]
pub struct ChatAdapter {
    inner: GgenAiAdapter,
}

impl ChatAdapter {
    pub fn new(model: Arc<dyn LanguageModel>) -> Self {
        Self {
            inner: GgenAiAdapter::new(model),
        }
    }
}

impl LanguageModel for ChatAdapter {
    fn complete<'a>(&'a self, request: &'a PromptRequest) -> ModelFuture<'a> {
        self.inner.complete(request)
    }
}

/// JSON-mode marker adapter. Parsing remains the consuming signature's responsibility.
#[derive(Clone)]
pub struct JSONAdapter {
    inner: GgenAiAdapter,
}

impl JSONAdapter {
    pub fn new(model: Arc<dyn LanguageModel>) -> Self {
        Self {
            inner: GgenAiAdapter::new(model),
        }
    }
}

impl LanguageModel for JSONAdapter {
    fn complete<'a>(&'a self, request: &'a PromptRequest) -> ModelFuture<'a> {
        self.inner.complete(request)
    }
}

#[derive(Clone)]
pub struct IntegratedAdapter {
    inner: GgenAiAdapter,
}

impl IntegratedAdapter {
    pub fn new(model: Arc<dyn LanguageModel>) -> Self {
        Self {
            inner: GgenAiAdapter::new(model),
        }
    }
}

impl LanguageModel for IntegratedAdapter {
    fn complete<'a>(&'a self, request: &'a PromptRequest) -> ModelFuture<'a> {
        self.inner.complete(request)
    }
}

/// Ordered inference fallback. Failure of one model is topology; remaining models are preserved.
#[derive(Clone)]
pub struct AdapterWithFallback {
    models: Vec<Arc<dyn LanguageModel>>,
}

impl AdapterWithFallback {
    pub fn new(models: impl IntoIterator<Item = Arc<dyn LanguageModel>>) -> Self {
        Self {
            models: models.into_iter().collect(),
        }
    }
}

impl LanguageModel for AdapterWithFallback {
    fn complete<'a>(&'a self, request: &'a PromptRequest) -> ModelFuture<'a> {
        Box::pin(async move {
            let mut failures = Vec::new();
            for model in &self.models {
                match model.complete(request).await {
                    Ok(completion) => return Ok(completion),
                    Err(error) => failures.push(error.to_string()),
                }
            }
            Err(DspyError::Model(format!(
                "all fallback models failed: {}",
                failures.join(" | ")
            )))
        })
    }
}

/// Deterministic model useful for examples and tests without ambient network authority.
#[derive(Clone, Debug)]
pub struct DummyLM {
    completion: Completion,
}

impl DummyLM {
    pub fn new(completion: impl Into<String>) -> Self {
        Self {
            completion: Completion::new(completion),
        }
    }
}

impl LanguageModel for DummyLM {
    fn complete<'a>(&'a self, _request: &'a PromptRequest) -> ModelFuture<'a> {
        let completion = self.completion.clone();
        Box::pin(async move { Ok(completion) })
    }
}
