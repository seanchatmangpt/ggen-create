use std::collections::VecDeque;
use std::future::Future;
use std::sync::{Arc, Mutex};
use std::task::{Context, Poll, Wake, Waker};

use ggen_dspy::{
    evaluate, BootstrapFewShot, ChainOfThought, Completion, DspyError, ExactMatch, Example, Field,
    LabeledFewShot, LanguageModel, ModelFuture, Module, Predictor, PromptRequest, ReAct, ReactTurn,
    Signature, ToolObservation, Values,
};

#[derive(Clone)]
struct FixedModel {
    responses: Arc<Mutex<VecDeque<String>>>,
    prompts: Arc<Mutex<Vec<String>>>,
}

impl FixedModel {
    fn new<I, S>(responses: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: Into<String>,
    {
        Self {
            responses: Arc::new(Mutex::new(responses.into_iter().map(Into::into).collect())),
            prompts: Arc::new(Mutex::new(Vec::new())),
        }
    }

    fn prompts(&self) -> Vec<String> {
        self.prompts.lock().expect("prompts lock poisoned").clone()
    }
}

impl LanguageModel for FixedModel {
    fn complete<'a>(&'a self, request: &'a PromptRequest) -> ModelFuture<'a> {
        self.prompts
            .lock()
            .expect("prompts lock poisoned")
            .push(request.prompt.clone());
        let response = self
            .responses
            .lock()
            .expect("responses lock poisoned")
            .pop_front();

        Box::pin(async move {
            response
                .map(Completion::new)
                .ok_or_else(|| DspyError::Model("fixed model exhausted".to_owned()))
        })
    }
}

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

fn qa_signature() -> Signature {
    Signature::new(
        "qa",
        "Answer the question.",
        [
            Field::input("question", "Question to answer"),
            Field::output("answer", "Answer"),
        ],
    )
    .expect("valid signature")
}

fn values(entries: &[(&str, &str)]) -> Values {
    entries
        .iter()
        .map(|(key, value)| ((*key).to_owned(), (*value).to_owned()))
        .collect()
}

#[test]
fn signature_rejects_duplicates_and_requires_output() {
    let duplicate = Signature::new(
        "bad",
        "",
        [Field::input("x", ""), Field::output("x", "duplicate")],
    );
    assert!(matches!(duplicate, Err(DspyError::InvalidSignature(_))));

    let no_output = Signature::new("bad", "", [Field::input("x", "")]);
    assert!(matches!(no_output, Err(DspyError::InvalidSignature(_))));
}

#[test]
fn predictor_parses_typed_output_and_records_deterministic_prompt() {
    let model = FixedModel::new(["answer: 4"]);
    let predictor = Predictor::new(qa_signature(), Arc::new(model.clone()));
    let prediction =
        block_on(predictor.forward(&values(&[("question", "2 + 2?")]))).expect("prediction");

    assert_eq!(prediction.get("answer"), Some("4"));
    let prompts = model.prompts();
    assert_eq!(prompts.len(), 1);
    assert!(prompts[0].contains("Signature: qa"));
    assert!(prompts[0].contains("input.question: 2 + 2?"));
}

#[test]
fn predictor_supports_multiple_outputs() {
    let signature = Signature::new(
        "classify",
        "",
        [
            Field::input("text", ""),
            Field::output("label", ""),
            Field::output("confidence", ""),
        ],
    )
    .expect("valid signature");
    let model = FixedModel::new(["label: positive\nconfidence: 0.98"]);
    let predictor = Predictor::new(signature, Arc::new(model));
    let prediction =
        block_on(predictor.forward(&values(&[("text", "great")]))).expect("prediction");

    assert_eq!(prediction.get("label"), Some("positive"));
    assert_eq!(prediction.get("confidence"), Some("0.98"));
}

#[test]
fn chain_of_thought_keeps_reasoning_separate_from_outputs() {
    let model = FixedModel::new(["reasoning: two plus two is four\nanswer: 4"]);
    let module = ChainOfThought::new(qa_signature(), Arc::new(model));
    let prediction =
        block_on(module.forward(&values(&[("question", "2 + 2?")]))).expect("prediction");

    assert_eq!(
        prediction.reasoning.as_deref(),
        Some("two plus two is four")
    );
    assert_eq!(prediction.get("answer"), Some("4"));
}

#[test]
fn react_manufactures_intent_without_any_tool_execution_surface() {
    let model = FixedModel::new([
        "action.tool: search\naction.rationale: need evidence\naction.arg.query: rust dspy",
    ]);
    let react = ReAct::new(qa_signature(), Arc::new(model), ["search".to_owned()]);

    let turn = block_on(react.step(
        &values(&[("question", "Where is the implementation?")]),
        &[],
    ))
    .expect("react turn");

    match turn {
        ReactTurn::Intent(intent) => {
            assert_eq!(intent.tool, "search");
            assert_eq!(
                intent.arguments.get("query").map(String::as_str),
                Some("rust dspy")
            );
            assert_eq!(intent.rationale.as_deref(), Some("need evidence"));
        }
        ReactTurn::Final(_) => panic!("expected intent"),
    }
}

#[test]
fn react_refuses_unadmitted_tool_and_accepts_broker_observations() {
    let refused_model = FixedModel::new(["action.tool: shell\naction.arg.command: rm -rf /"]);
    let react = ReAct::new(
        qa_signature(),
        Arc::new(refused_model),
        ["search".to_owned()],
    );
    let error = block_on(react.step(&values(&[("question", "actuate")]), &[]))
        .expect_err("unknown tool must be refused");
    assert_eq!(error, DspyError::UnknownTool("shell".to_owned()));

    let final_model = FixedModel::new(["answer: found"]);
    let react = ReAct::new(
        qa_signature(),
        Arc::new(final_model.clone()),
        ["search".to_owned()],
    );
    let turn = block_on(react.step(
        &values(&[("question", "locate")]),
        &[ToolObservation::new("search", "repository result")],
    ))
    .expect("final turn");
    assert!(matches!(turn, ReactTurn::Final(_)));
    assert!(final_model.prompts()[0].contains("observation.search: repository result"));
}

#[test]
fn labeled_few_shot_compiles_examples_into_student_prompt() {
    let model = FixedModel::new(["answer: 4"]);
    let student = Predictor::new(qa_signature(), Arc::new(model.clone()));
    let examples = vec![
        Example::new(
            values(&[("question", "1 + 1?")]),
            values(&[("answer", "2")]),
        ),
        Example::new(
            values(&[("question", "3 + 3?")]),
            values(&[("answer", "6")]),
        ),
    ];

    let compiled = LabeledFewShot::new(1)
        .compile(&student, &examples)
        .expect("compile");
    assert_eq!(compiled.demonstrations().len(), 1);
    block_on(compiled.forward(&values(&[("question", "2 + 2?")]))).expect("prediction");

    let prompt = model.prompts().pop().expect("captured prompt");
    assert!(prompt.contains("[example 1]"));
    assert!(prompt.contains("input.question: 1 + 1?"));
    assert!(!prompt.contains("input.question: 3 + 3?"));
}

#[test]
fn bootstrap_few_shot_admits_only_metric_passing_teacher_predictions() {
    let student_model = FixedModel::new(["answer: final"]);
    let student = Predictor::new(qa_signature(), Arc::new(student_model));
    let teacher_model = FixedModel::new(["answer: 2", "answer: wrong"]);
    let teacher = Predictor::new(qa_signature(), Arc::new(teacher_model));
    let training = vec![
        Example::new(
            values(&[("question", "1 + 1?")]),
            values(&[("answer", "2")]),
        ),
        Example::new(
            values(&[("question", "2 + 2?")]),
            values(&[("answer", "4")]),
        ),
    ];

    let optimizer = BootstrapFewShot::new(8, 1.0).expect("optimizer");
    let compiled =
        block_on(optimizer.compile(&student, &teacher, &training, &ExactMatch)).expect("bootstrap");

    assert_eq!(compiled.demonstrations().len(), 1);
    assert_eq!(
        compiled.demonstrations()[0]
            .outputs
            .get("answer")
            .map(String::as_str),
        Some("2")
    );
}

#[test]
fn evaluator_emits_bounded_summary() {
    let model = FixedModel::new(["answer: 2", "answer: wrong"]);
    let module = Predictor::new(qa_signature(), Arc::new(model));
    let examples = vec![
        Example::new(
            values(&[("question", "1 + 1?")]),
            values(&[("answer", "2")]),
        ),
        Example::new(
            values(&[("question", "2 + 2?")]),
            values(&[("answer", "4")]),
        ),
    ];

    let summary = block_on(evaluate(&module, &examples, &ExactMatch)).expect("evaluation");
    assert_eq!(summary.total, 2);
    assert_eq!(summary.passed, 1);
    assert_eq!(summary.mean_score, 0.5);
    assert_eq!(summary.scores, vec![1.0, 0.0]);
}
