use std::future::Future;
use std::sync::Arc;
use std::task::{Context, Poll, Wake, Waker};
use std::time::Duration;

use ggen_dspy::{
    Assert, CacheConfig, CacheManager, CodeLanguage, DummyLM, Field, InMemoryRetriever, Module,
    Optimizer, OptimizerConfig, OutputField, PatternLibrary, Predictor, ProgramOfThoughtBuilder,
    RetrieverBackend, Signature, Tool, Values,
};

struct NoopWake;

impl Wake for NoopWake {
    fn wake(self: Arc<Self>) {}
}

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

fn values(entries: &[(&str, &str)]) -> Values {
    entries
        .iter()
        .map(|(key, value)| ((*key).to_owned(), (*value).to_owned()))
        .collect()
}

#[test]
fn historical_signature_builder_surface_is_preserved() {
    let signature = Signature::builder()
        .name("qa")
        .instructions("Answer")
        .input(ggen_dspy::InputField::new("question", "question"))
        .output(OutputField::new("answer", "answer"))
        .build()
        .expect("builder must create valid signature");

    assert_eq!(signature.name, "qa");
    assert_eq!(signature.input_fields().count(), 1);
    assert_eq!(signature.output_fields().count(), 1);
}

#[test]
fn cache_is_bounded_and_reports_eviction_evidence() {
    let cache = CacheManager::new(CacheConfig {
        enabled: true,
        max_entries: 1,
        ttl: Duration::from_secs(60),
    });
    cache.insert("a", "one").expect("first insert");
    cache.insert("b", "two").expect("second insert");

    assert_eq!(cache.get("a").expect("get a"), None);
    assert_eq!(cache.get("b").expect("get b").as_deref(), Some("two"));
    let stats = cache.stats().expect("stats");
    assert_eq!(stats.evictions, 1);
    assert_eq!(stats.hits, 1);
}

#[test]
fn in_memory_retrieval_is_deterministic_and_read_only() {
    let backend = InMemoryRetriever::new([
        "Rust has ownership and borrowing".to_owned(),
        "Python has dynamic typing".to_owned(),
        "Rust uses Cargo".to_owned(),
    ]);
    let passages = backend.retrieve("Rust ownership", 2).expect("retrieval");

    assert_eq!(passages.len(), 2);
    assert!(passages[0].text.contains("ownership"));
    assert!(passages[0].score >= passages[1].score);
}

#[test]
fn program_of_thought_manufactures_code_but_refuses_execution() {
    let signature = Signature::new(
        "program",
        "Write code",
        [
            Field::input("question", "question"),
            Field::output("code", "program"),
        ],
    )
    .expect("signature");
    let predictor = Predictor::new(signature, Arc::new(DummyLM::new("code: print(42)")));
    let program = ProgramOfThoughtBuilder::new(predictor)
        .language(CodeLanguage::Python)
        .build();

    let prediction = block_on(program.forward(&values(&[("question", "compute")])))
        .expect("construct program");
    assert_eq!(prediction.get("code"), Some("print(42)"));
    assert_eq!(
        prediction.get("execution_status"),
        Some("REFUSED:ACTUATION_REQUIRES_BROKER")
    );
}

#[test]
fn tool_type_is_data_only() {
    let tool = Tool::new("search", "read admitted evidence");
    assert_eq!(tool.name, "search");
    assert_eq!(tool.description, "read admitted evidence");
}

#[test]
fn assertions_operate_on_predictions_without_retry_or_actuation() {
    let mut prediction = ggen_dspy::Prediction::new(Values::new());
    prediction.set("answer", "42");
    Assert::field_nonempty("answer")
        .check(&prediction)
        .expect("non-empty answer passes");
    assert!(Assert::field_nonempty("missing").check(&prediction).is_err());
}

#[test]
fn historical_pattern_library_is_complete() {
    let library = PatternLibrary::new();
    let names: Vec<&str> = library.names().collect();
    assert_eq!(names.len(), 7);
    for expected in [
        "predict",
        "chain_of_thought",
        "react",
        "retrieve",
        "multihop_qa",
        "simplified_baleen",
        "program_of_thought",
    ] {
        assert!(names.contains(&expected));
    }
}

#[test]
fn mipro_surface_is_bounded_by_explicit_candidates() {
    let optimizer = ggen_dspy::MiproOptimizer::new(
        OptimizerConfig::new().with_max_iterations(3),
    )
    .with_candidates(["short".to_owned(), "precise".to_owned()]);
    assert_eq!(optimizer.name(), "MIPRO");
    assert_eq!(optimizer.candidate_instructions.len(), 2);
}
