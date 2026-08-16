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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::Values;
    use std::future::Future;
    use std::sync::Mutex;
    use std::task::{Context, Poll, Wake, Waker};

    struct NoopWake;

    impl Wake for NoopWake {
        fn wake(self: Arc<Self>) {}
    }

    /// Zero-dependency executor mirroring the integration-test harness.
    fn block_on<F: Future>(future: F) -> F::Output {
        let waker = Waker::from(Arc::new(NoopWake));
        let mut context = Context::from_waker(&waker);
        let mut future = Box::pin(future);
        loop {
            match future.as_mut().poll(&mut context) {
                Poll::Ready(value) => return value,
                Poll::Pending => std::thread::yield_now(),
            }
        }
    }

    /// A real language model that records the prompts it observes and answers deterministically.
    /// This is a genuine implementation of the trait contract, not an interaction mock: it has
    /// real behavior and the recorded prompts are inspectable state.
    struct RecordingModel {
        reply: String,
        seen: Mutex<Vec<PromptRequest>>,
    }

    impl RecordingModel {
        fn new(reply: &str) -> Self {
            Self {
                reply: reply.to_owned(),
                seen: Mutex::new(Vec::new()),
            }
        }

        fn seen(&self) -> Vec<PromptRequest> {
            self.seen.lock().expect("seen lock poisoned").clone()
        }
    }

    impl LanguageModel for RecordingModel {
        fn complete<'a>(&'a self, request: &'a PromptRequest) -> ModelFuture<'a> {
            self.seen
                .lock()
                .expect("seen lock poisoned")
                .push(request.clone());
            let reply = self.reply.clone();
            Box::pin(async move { Ok(Completion::new(reply)) })
        }
    }

    /// A real language model whose contract is to fail, recording how often it was reached.
    struct FailingModel {
        detail: String,
        calls: Mutex<usize>,
    }

    impl FailingModel {
        fn new(detail: &str) -> Self {
            Self {
                detail: detail.to_owned(),
                calls: Mutex::new(0),
            }
        }

        fn calls(&self) -> usize {
            *self.calls.lock().expect("calls lock poisoned")
        }
    }

    impl LanguageModel for FailingModel {
        fn complete<'a>(&'a self, _request: &'a PromptRequest) -> ModelFuture<'a> {
            *self.calls.lock().expect("calls lock poisoned") += 1;
            let detail = self.detail.clone();
            Box::pin(async move { Err(DspyError::Model(detail)) })
        }
    }

    fn request_with_metadata(prompt: &str, key: &str, value: &str) -> PromptRequest {
        let mut metadata = Values::new();
        metadata.insert(key.to_owned(), value.to_owned());
        PromptRequest {
            prompt: prompt.to_owned(),
            metadata,
        }
    }

    #[test]
    fn completion_request_preserves_prompt_and_metadata_through_conversion() {
        let mut request = CompletionRequest::new("summarize the exemplar");
        request
            .metadata
            .insert("tenant".to_owned(), "acme".to_owned());

        let prompt_request = request.into_prompt_request();

        assert_eq!(prompt_request.prompt, "summarize the exemplar");
        assert_eq!(
            prompt_request.metadata.get("tenant").map(String::as_str),
            Some("acme")
        );
    }

    #[test]
    fn completion_request_new_starts_with_empty_metadata() {
        let request = CompletionRequest::new("plain");

        assert!(request.metadata.is_empty());
        assert_eq!(request.prompt, "plain");
    }

    #[test]
    fn token_counter_reports_characters_and_whitespace_delimited_tokens() {
        let stats = TokenCounter.count("one two  three\nfour");

        assert_eq!(stats.estimated_tokens, 4);
        assert_eq!(stats.characters, "one two  three\nfour".chars().count());
    }

    #[test]
    fn token_counter_counts_unicode_scalars_not_bytes() {
        // "héllo" is 5 chars but 6 UTF-8 bytes; the counter must report scalar values.
        let stats = TokenCounter.count("héllo");

        assert_eq!(stats.characters, 5);
        assert_eq!(stats.estimated_tokens, 1);
    }

    #[test]
    fn token_counter_on_empty_and_whitespace_only_text_yields_zero_tokens() {
        assert_eq!(TokenCounter.count(""), TokenStats::default());

        let blank = TokenCounter.count("   \t\n");
        assert_eq!(blank.estimated_tokens, 0);
        assert_eq!(blank.characters, 5);
    }

    #[test]
    fn retry_config_default_allows_two_attempts() {
        assert_eq!(RetryConfig::default(), RetryConfig { max_attempts: 2 });
    }

    #[test]
    fn dummy_lm_answers_identically_regardless_of_request() {
        let model = DummyLM::new("fixed answer");

        let first = block_on(model.complete(&PromptRequest::new("first"))).expect("completion");
        let second = block_on(model.complete(&request_with_metadata("second", "k", "v")))
            .expect("completion");

        assert_eq!(first.text, "fixed answer");
        assert_eq!(second.text, first.text);
    }

    #[test]
    fn wrapper_adapters_forward_the_request_unchanged_to_the_inner_model() {
        for label in ["ggen_ai", "completion", "chat", "json", "integrated"] {
            let inner = Arc::new(RecordingModel::new("inner reply"));
            let model: Arc<dyn LanguageModel> = inner.clone();
            let adapter: Box<dyn LanguageModel> = match label {
                "ggen_ai" => Box::new(GgenAiAdapter::new(model)),
                "completion" => Box::new(CompletionAdapter::new(model)),
                "chat" => Box::new(ChatAdapter::new(model)),
                "json" => Box::new(JSONAdapter::new(model)),
                _ => Box::new(IntegratedAdapter::new(model)),
            };

            let request = request_with_metadata("carry me", "mode", label);
            let completion = block_on(adapter.complete(&request)).expect("completion");

            assert_eq!(completion.text, "inner reply", "adapter {label}");
            assert_eq!(
                inner.seen(),
                vec![request],
                "adapter {label} must forward the request verbatim"
            );
        }
    }

    #[test]
    fn fallback_returns_the_first_success_and_leaves_later_models_untouched() {
        let primary = Arc::new(RecordingModel::new("primary answer"));
        let secondary = Arc::new(RecordingModel::new("secondary answer"));
        let fallback = AdapterWithFallback::new([
            primary.clone() as Arc<dyn LanguageModel>,
            secondary.clone() as Arc<dyn LanguageModel>,
        ]);

        let completion =
            block_on(fallback.complete(&PromptRequest::new("question"))).expect("completion");

        assert_eq!(completion.text, "primary answer");
        assert_eq!(primary.seen().len(), 1);
        assert!(
            secondary.seen().is_empty(),
            "a satisfied request must not reach later fallbacks"
        );
    }

    #[test]
    fn fallback_advances_past_failures_to_the_first_healthy_model() {
        let broken = Arc::new(FailingModel::new("upstream down"));
        let healthy = Arc::new(RecordingModel::new("recovered answer"));
        let fallback = AdapterWithFallback::new([
            broken.clone() as Arc<dyn LanguageModel>,
            healthy.clone() as Arc<dyn LanguageModel>,
        ]);

        let completion =
            block_on(fallback.complete(&PromptRequest::new("question"))).expect("completion");

        assert_eq!(completion.text, "recovered answer");
        assert_eq!(broken.calls(), 1);
        assert_eq!(healthy.seen().len(), 1);
    }

    #[test]
    fn fallback_aggregates_every_failure_in_declaration_order_when_all_models_fail() {
        let first = Arc::new(FailingModel::new("first outage"));
        let second = Arc::new(FailingModel::new("second outage"));
        let fallback = AdapterWithFallback::new([
            first.clone() as Arc<dyn LanguageModel>,
            second.clone() as Arc<dyn LanguageModel>,
        ]);

        let error =
            block_on(fallback.complete(&PromptRequest::new("question"))).expect_err("all fail");

        let DspyError::Model(detail) = error else {
            panic!("fallback exhaustion must surface as a model error");
        };
        assert_eq!(
            detail,
            "all fallback models failed: model failure: first outage | model failure: second outage"
        );
        assert_eq!(first.calls(), 1);
        assert_eq!(second.calls(), 1);
    }

    #[test]
    fn fallback_without_any_models_refuses_instead_of_fabricating_a_completion() {
        let fallback = AdapterWithFallback::new(Vec::<Arc<dyn LanguageModel>>::new());

        let error =
            block_on(fallback.complete(&PromptRequest::new("question"))).expect_err("no models");

        assert!(
            matches!(error, DspyError::Model(ref detail) if detail == "all fallback models failed: "),
            "unexpected error: {error}"
        );
    }
}
