use std::collections::{BTreeSet, HashSet};
use std::sync::Arc;

use crate::core::{
    Completion, DspyError, Example, LanguageModel, Module, ModuleFuture, Prediction, PromptRequest,
    Signature, Values,
};

/// DSPy Predict: compile a signature and values into a prompt, then parse typed outputs.
#[derive(Clone)]
pub struct Predictor {
    signature: Signature,
    model: Arc<dyn LanguageModel>,
    demonstrations: Vec<Example>,
}

impl Predictor {
    pub fn new(signature: Signature, model: Arc<dyn LanguageModel>) -> Self {
        Self {
            signature,
            model,
            demonstrations: Vec::new(),
        }
    }

    pub fn signature(&self) -> &Signature {
        &self.signature
    }

    pub fn demonstrations(&self) -> &[Example] {
        &self.demonstrations
    }

    pub fn with_demonstrations(mut self, demonstrations: Vec<Example>) -> Result<Self, DspyError> {
        for (index, example) in demonstrations.iter().enumerate() {
            self.signature.validate_example(example).map_err(|error| {
                DspyError::InvalidExample(format!("demonstration {index}: {error}"))
            })?;
        }
        self.demonstrations = demonstrations;
        Ok(self)
    }

    pub fn with_instructions(&self, instructions: impl Into<String>) -> Self {
        Self {
            signature: self.signature.with_instructions(instructions),
            model: Arc::clone(&self.model),
            demonstrations: self.demonstrations.clone(),
        }
    }

    pub fn compile_prompt(&self, inputs: &Values) -> Result<String, DspyError> {
        self.request(inputs, PromptMode::Predict)
            .map(|request| request.prompt)
    }

    fn request(&self, inputs: &Values, mode: PromptMode) -> Result<PromptRequest, DspyError> {
        self.signature.validate_inputs(inputs)?;
        let prompt = compile_prompt(&self.signature, &self.demonstrations, inputs, mode);
        let mut request = PromptRequest::new(prompt);
        request
            .metadata
            .insert("signature".to_owned(), self.signature.name.clone());
        request.metadata.insert(
            "mode".to_owned(),
            match mode {
                PromptMode::Predict => "predict",
                PromptMode::ChainOfThought => "chain_of_thought",
            }
            .to_owned(),
        );
        Ok(request)
    }

    async fn predict_with_mode(
        &self,
        inputs: &Values,
        mode: PromptMode,
    ) -> Result<Prediction, DspyError> {
        let request = self.request(inputs, mode)?;
        let Completion { text } = self.model.complete(&request).await?;
        match mode {
            PromptMode::Predict => parse_prediction(&self.signature, &text),
            PromptMode::ChainOfThought => parse_chain_of_thought(&self.signature, &text),
        }
    }
}

impl Module for Predictor {
    fn forward<'a>(&'a self, inputs: &'a Values) -> ModuleFuture<'a> {
        Box::pin(async move { self.predict_with_mode(inputs, PromptMode::Predict).await })
    }

    fn name(&self) -> &str {
        "Predictor"
    }
}

/// DSPy ChainOfThought. Reasoning is typed as construction evidence, not authority.
#[derive(Clone)]
pub struct ChainOfThought {
    predictor: Predictor,
}

impl ChainOfThought {
    pub fn new(signature: Signature, model: Arc<dyn LanguageModel>) -> Self {
        Self {
            predictor: Predictor::new(signature, model),
        }
    }

    pub fn with_demonstrations(mut self, demonstrations: Vec<Example>) -> Result<Self, DspyError> {
        self.predictor = self.predictor.with_demonstrations(demonstrations)?;
        Ok(self)
    }
}

impl Module for ChainOfThought {
    fn forward<'a>(&'a self, inputs: &'a Values) -> ModuleFuture<'a> {
        Box::pin(async move {
            self.predictor
                .predict_with_mode(inputs, PromptMode::ChainOfThought)
                .await
        })
    }

    fn name(&self) -> &str {
        "ChainOfThought"
    }
}

/// Data-only tool declaration. It carries no executable callback.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Tool {
    pub name: String,
    pub description: String,
}

impl Tool {
    pub fn new(name: impl Into<String>, description: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
        }
    }
}

/// An observation supplied by the host after separately admitted/receipted actuation.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ToolObservation {
    pub tool: String,
    pub value: String,
}

impl ToolObservation {
    pub fn new(tool: impl Into<String>, value: impl Into<String>) -> Self {
        Self {
            tool: tool.into(),
            value: value.into(),
        }
    }
}

/// A candidate action manufactured by ReAct.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ActionIntent {
    pub tool: String,
    pub arguments: Values,
    pub rationale: Option<String>,
}

/// One ReAct construction step: either a typed final prediction or a candidate action intent.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ReactTurn {
    Final(Prediction),
    Intent(ActionIntent),
}

pub type ReactFuture<'a> = std::pin::Pin<
    Box<dyn std::future::Future<Output = Result<ReactTurn, DspyError>> + Send + 'a>,
>;

/// DSPy ReAct with a hard authority fence.
///
/// The historical crate accepted executable Tool callbacks. In ggen-create that boundary is
/// intentionally narrowed: ReAct may manufacture an [`ActionIntent`], but only the host broker
/// can admit and actuate it. Broker observations can then be supplied to the next step.
#[derive(Clone)]
pub struct ReAct {
    signature: Signature,
    model: Arc<dyn LanguageModel>,
    allowed_tools: BTreeSet<String>,
    demonstrations: Vec<Example>,
}

/// Historical name retained for compatibility.
pub type ReactAgent = ReAct;

impl ReAct {
    pub fn new(
        signature: Signature,
        model: Arc<dyn LanguageModel>,
        allowed_tools: impl IntoIterator<Item = String>,
    ) -> Self {
        Self {
            signature,
            model,
            allowed_tools: allowed_tools.into_iter().collect(),
            demonstrations: Vec::new(),
        }
    }

    pub fn from_tools(
        signature: Signature,
        model: Arc<dyn LanguageModel>,
        tools: impl IntoIterator<Item = Tool>,
    ) -> Self {
        Self::new(signature, model, tools.into_iter().map(|tool| tool.name))
    }

    pub fn with_demonstrations(mut self, demonstrations: Vec<Example>) -> Result<Self, DspyError> {
        for (index, example) in demonstrations.iter().enumerate() {
            self.signature.validate_example(example).map_err(|error| {
                DspyError::InvalidExample(format!("demonstration {index}: {error}"))
            })?;
        }
        self.demonstrations = demonstrations;
        Ok(self)
    }

    pub fn step<'a>(
        &'a self,
        inputs: &'a Values,
        observations: &'a [ToolObservation],
    ) -> ReactFuture<'a> {
        Box::pin(async move {
            self.signature.validate_inputs(inputs)?;
            let prompt = compile_react_prompt(
                &self.signature,
                &self.demonstrations,
                inputs,
                observations,
                &self.allowed_tools,
            );
            let mut request = PromptRequest::new(prompt);
            request
                .metadata
                .insert("signature".to_owned(), self.signature.name.clone());
            request
                .metadata
                .insert("mode".to_owned(), "react_construct_only".to_owned());

            let Completion { text } = self.model.complete(&request).await?;
            if let Some(intent) = parse_action_intent(&text)? {
                if !self.allowed_tools.contains(&intent.tool) {
                    return Err(DspyError::UnknownTool(intent.tool));
                }
                return Ok(ReactTurn::Intent(intent));
            }

            Ok(ReactTurn::Final(parse_prediction(&self.signature, &text)?))
        })
    }
}

/// One retrieved passage from an admitted corpus.
#[derive(Clone, Debug, PartialEq)]
pub struct Passage {
    pub text: String,
    pub score: f64,
    pub metadata: Values,
}

impl Passage {
    pub fn new(text: impl Into<String>, score: f64) -> Self {
        Self {
            text: text.into(),
            score,
            metadata: Values::new(),
        }
    }
}

/// Read-side retrieval boundary. Backends return observations and have no mutation API.
pub trait RetrieverBackend: Send + Sync {
    fn retrieve(&self, query: &str, limit: usize) -> Result<Vec<Passage>, DspyError>;
}

/// Deterministic lexical retriever for local/admitted corpora.
#[derive(Clone, Debug, Default)]
pub struct InMemoryRetriever {
    documents: Vec<String>,
}

impl InMemoryRetriever {
    pub fn new(documents: impl IntoIterator<Item = String>) -> Self {
        Self {
            documents: documents.into_iter().collect(),
        }
    }
}

impl RetrieverBackend for InMemoryRetriever {
    fn retrieve(&self, query: &str, limit: usize) -> Result<Vec<Passage>, DspyError> {
        let query_terms = terms(query);
        let mut passages: Vec<Passage> = self
            .documents
            .iter()
            .map(|document| {
                let document_terms = terms(document);
                let overlap = query_terms.intersection(&document_terms).count();
                let denominator = query_terms.len().max(1) as f64;
                Passage::new(document.clone(), overlap as f64 / denominator)
            })
            .collect();
        passages.sort_by(|left, right| {
            right
                .score
                .partial_cmp(&left.score)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| left.text.cmp(&right.text))
        });
        passages.truncate(limit);
        Ok(passages)
    }
}

fn terms(text: &str) -> HashSet<String> {
    text.split(|ch: char| !ch.is_alphanumeric())
        .filter(|part| !part.is_empty())
        .map(str::to_ascii_lowercase)
        .collect()
}

#[derive(Clone)]
pub struct Retrieve {
    backend: Arc<dyn RetrieverBackend>,
    limit: usize,
}

impl Retrieve {
    pub fn new(backend: Arc<dyn RetrieverBackend>, limit: usize) -> Self {
        Self { backend, limit }
    }

    pub fn passages(&self, query: &str) -> Result<Vec<Passage>, DspyError> {
        self.backend.retrieve(query, self.limit)
    }
}

impl Module for Retrieve {
    fn forward<'a>(&'a self, inputs: &'a Values) -> ModuleFuture<'a> {
        Box::pin(async move {
            let query = inputs
                .get("query")
                .or_else(|| inputs.get("question"))
                .ok_or_else(|| DspyError::MissingInput("query".to_owned()))?;
            let passages = self.passages(query)?;
            let mut outputs = Values::new();
            outputs.insert(
                "context".to_owned(),
                passages
                    .iter()
                    .map(|passage| passage.text.as_str())
                    .collect::<Vec<_>>()
                    .join("\n\n"),
            );
            outputs.insert("passage_count".to_owned(), passages.len().to_string());
            Ok(Prediction::new(outputs))
        })
    }

    fn name(&self) -> &str {
        "Retrieve"
    }
}

pub struct RetrieveBuilder {
    backend: Arc<dyn RetrieverBackend>,
    limit: usize,
}

impl RetrieveBuilder {
    pub fn new(backend: Arc<dyn RetrieverBackend>) -> Self {
        Self { backend, limit: 5 }
    }

    pub fn limit(mut self, limit: usize) -> Self {
        self.limit = limit;
        self
    }

    pub fn build(self) -> Retrieve {
        Retrieve::new(self.backend, self.limit)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MultiHopConfig {
    pub max_hops: usize,
    pub passages_per_hop: usize,
}

impl Default for MultiHopConfig {
    fn default() -> Self {
        Self {
            max_hops: 2,
            passages_per_hop: 3,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct HopState {
    pub hop: usize,
    pub query: String,
    pub passages: Vec<Passage>,
}

#[derive(Clone)]
pub struct MultiHopQA {
    predictor: Predictor,
    backend: Arc<dyn RetrieverBackend>,
    config: MultiHopConfig,
}

impl MultiHopQA {
    pub fn new(
        predictor: Predictor,
        backend: Arc<dyn RetrieverBackend>,
        config: MultiHopConfig,
    ) -> Self {
        Self {
            predictor,
            backend,
            config,
        }
    }

    pub fn trace(&self, question: &str) -> Result<Vec<HopState>, DspyError> {
        let mut trace = Vec::new();
        let mut query = question.to_owned();
        for hop in 0..self.config.max_hops {
            let passages = self
                .backend
                .retrieve(&query, self.config.passages_per_hop)?;
            let next_query = passages
                .first()
                .map(|passage| format!("{question} {}", passage.text))
                .unwrap_or_else(|| question.to_owned());
            trace.push(HopState {
                hop,
                query,
                passages,
            });
            query = next_query;
        }
        Ok(trace)
    }
}

impl Module for MultiHopQA {
    fn forward<'a>(&'a self, inputs: &'a Values) -> ModuleFuture<'a> {
        Box::pin(async move {
            let question = inputs
                .get("question")
                .ok_or_else(|| DspyError::MissingInput("question".to_owned()))?;
            let trace = self.trace(question)?;
            let context = trace
                .iter()
                .flat_map(|hop| hop.passages.iter())
                .map(|passage| passage.text.as_str())
                .collect::<Vec<_>>()
                .join("\n\n");
            let mut enriched = inputs.clone();
            enriched.insert("context".to_owned(), context);
            self.predictor.forward(&enriched).await
        })
    }

    fn name(&self) -> &str {
        "MultiHopQA"
    }
}

pub struct MultiHopQABuilder {
    predictor: Predictor,
    backend: Arc<dyn RetrieverBackend>,
    config: MultiHopConfig,
}

impl MultiHopQABuilder {
    pub fn new(predictor: Predictor, backend: Arc<dyn RetrieverBackend>) -> Self {
        Self {
            predictor,
            backend,
            config: MultiHopConfig::default(),
        }
    }

    pub fn max_hops(mut self, max_hops: usize) -> Self {
        self.config.max_hops = max_hops;
        self
    }

    pub fn passages_per_hop(mut self, passages: usize) -> Self {
        self.config.passages_per_hop = passages;
        self
    }

    pub fn build(self) -> MultiHopQA {
        MultiHopQA::new(self.predictor, self.backend, self.config)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BaleenConfig {
    pub max_hops: usize,
    pub passages_per_hop: usize,
}

impl Default for BaleenConfig {
    fn default() -> Self {
        Self {
            max_hops: 2,
            passages_per_hop: 3,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct BaleenHop {
    pub hop: usize,
    pub passages: Vec<Passage>,
}

#[derive(Clone)]
pub struct SimplifiedBaleen {
    qa: MultiHopQA,
}

impl SimplifiedBaleen {
    pub fn new(
        predictor: Predictor,
        backend: Arc<dyn RetrieverBackend>,
        config: BaleenConfig,
    ) -> Self {
        Self {
            qa: MultiHopQA::new(
                predictor,
                backend,
                MultiHopConfig {
                    max_hops: config.max_hops,
                    passages_per_hop: config.passages_per_hop,
                },
            ),
        }
    }
}

impl Module for SimplifiedBaleen {
    fn forward<'a>(&'a self, inputs: &'a Values) -> ModuleFuture<'a> {
        self.qa.forward(inputs)
    }

    fn name(&self) -> &str {
        "SimplifiedBaleen"
    }
}

pub struct BaleenBuilder {
    predictor: Predictor,
    backend: Arc<dyn RetrieverBackend>,
    config: BaleenConfig,
}

impl BaleenBuilder {
    pub fn new(predictor: Predictor, backend: Arc<dyn RetrieverBackend>) -> Self {
        Self {
            predictor,
            backend,
            config: BaleenConfig::default(),
        }
    }

    pub fn max_hops(mut self, max_hops: usize) -> Self {
        self.config.max_hops = max_hops;
        self
    }

    pub fn build(self) -> SimplifiedBaleen {
        SimplifiedBaleen::new(self.predictor, self.backend, self.config)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CodeLanguage {
    Python,
    Rust,
    JavaScript,
    Other,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProgramOfThoughtConfig {
    pub language: CodeLanguage,
}

impl Default for ProgramOfThoughtConfig {
    fn default() -> Self {
        Self {
            language: CodeLanguage::Python,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CodeIntent {
    pub language: CodeLanguage,
    pub code: String,
    pub rationale: Option<String>,
}

/// Broker-returned result type. This crate never manufactures one by executing code.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExecutionResult {
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
    pub receipt: Option<String>,
}

#[derive(Clone)]
pub struct ProgramOfThought {
    predictor: Predictor,
    config: ProgramOfThoughtConfig,
}

impl ProgramOfThought {
    pub fn new(predictor: Predictor, config: ProgramOfThoughtConfig) -> Self {
        Self { predictor, config }
    }

    pub fn construct<'a>(&'a self, inputs: &'a Values) -> ProgramIntentFuture<'a> {
        Box::pin(async move {
            let prediction = self.predictor.forward(inputs).await?;
            let code = prediction
                .get("code")
                .ok_or_else(|| DspyError::MissingOutput("code".to_owned()))?;
            Ok(CodeIntent {
                language: self.config.language,
                code: code.to_owned(),
                rationale: prediction.reasoning.clone(),
            })
        })
    }
}

pub type ProgramIntentFuture<'a> = std::pin::Pin<
    Box<dyn std::future::Future<Output = Result<CodeIntent, DspyError>> + Send + 'a>,
>;

impl Module for ProgramOfThought {
    fn forward<'a>(&'a self, inputs: &'a Values) -> ModuleFuture<'a> {
        Box::pin(async move {
            let intent = self.construct(inputs).await?;
            let mut outputs = Values::new();
            outputs.insert("code".to_owned(), intent.code);
            outputs.insert(
                "execution_status".to_owned(),
                "REFUSED:ACTUATION_REQUIRES_BROKER".to_owned(),
            );
            Ok(Prediction::new(outputs))
        })
    }

    fn name(&self) -> &str {
        "ProgramOfThought"
    }
}

pub struct ProgramOfThoughtBuilder {
    predictor: Predictor,
    config: ProgramOfThoughtConfig,
}

impl ProgramOfThoughtBuilder {
    pub fn new(predictor: Predictor) -> Self {
        Self {
            predictor,
            config: ProgramOfThoughtConfig::default(),
        }
    }

    pub fn language(mut self, language: CodeLanguage) -> Self {
        self.config.language = language;
        self
    }

    pub fn build(self) -> ProgramOfThought {
        ProgramOfThought::new(self.predictor, self.config)
    }
}

#[derive(Clone, Copy)]
enum PromptMode {
    Predict,
    ChainOfThought,
}

fn compile_prompt(
    signature: &Signature,
    demonstrations: &[Example],
    inputs: &Values,
    mode: PromptMode,
) -> String {
    let mut prompt = String::new();
    prompt.push_str("Signature: ");
    prompt.push_str(&signature.name);
    prompt.push('\n');

    if !signature.instructions.trim().is_empty() {
        prompt.push_str("Instructions: ");
        prompt.push_str(signature.instructions.trim());
        prompt.push('\n');
    }

    if !demonstrations.is_empty() {
        prompt.push_str("Examples:\n");
        for (index, example) in demonstrations.iter().enumerate() {
            prompt.push_str(&format!("[example {}]\n", index + 1));
            append_values(
                &mut prompt,
                "input",
                signature.input_fields().filter_map(|field| {
                    example
                        .inputs
                        .get(&field.name)
                        .map(|value| (&field.name, value))
                }),
            );
            append_values(
                &mut prompt,
                "output",
                signature.output_fields().filter_map(|field| {
                    example
                        .outputs
                        .get(&field.name)
                        .map(|value| (&field.name, value))
                }),
            );
        }
    }

    prompt.push_str("Inputs:\n");
    append_values(
        &mut prompt,
        "input",
        signature
            .input_fields()
            .filter_map(|field| inputs.get(&field.name).map(|value| (&field.name, value))),
    );

    match mode {
        PromptMode::Predict => {
            prompt.push_str("Return one line per output using `<field>: <value>`:\n");
        }
        PromptMode::ChainOfThought => {
            prompt.push_str(
                "Return `reasoning: <reasoning>` followed by one line per output using `<field>: <value>`:\n",
            );
        }
    }
    for field in signature.output_fields() {
        prompt.push_str("- ");
        prompt.push_str(&field.name);
        if !field.description.trim().is_empty() {
            prompt.push_str(": ");
            prompt.push_str(field.description.trim());
        }
        prompt.push('\n');
    }
    prompt
}

fn compile_react_prompt(
    signature: &Signature,
    demonstrations: &[Example],
    inputs: &Values,
    observations: &[ToolObservation],
    allowed_tools: &BTreeSet<String>,
) -> String {
    let mut prompt = compile_prompt(signature, demonstrations, inputs, PromptMode::Predict);
    prompt.push_str("\nReAct authority boundary: you may propose an action but cannot execute it.\n");
    prompt.push_str("Allowed tools:");
    if allowed_tools.is_empty() {
        prompt.push_str(" (none)");
    } else {
        for tool in allowed_tools {
            prompt.push(' ');
            prompt.push_str(tool);
        }
    }
    prompt.push('\n');

    if !observations.is_empty() {
        prompt.push_str("Broker-supplied observations:\n");
        for observation in observations {
            prompt.push_str("observation.");
            prompt.push_str(&observation.tool);
            prompt.push_str(": ");
            prompt.push_str(&observation.value);
            prompt.push('\n');
        }
    }

    prompt.push_str(
        "To propose action, return `action.tool: <tool>`, optional `action.rationale: <text>`, and zero or more `action.arg.<name>: <value>` lines. Otherwise return final signature outputs.\n",
    );
    prompt
}

fn append_values<'a>(
    prompt: &mut String,
    namespace: &str,
    values: impl IntoIterator<Item = (&'a String, &'a String)>,
) {
    for (name, value) in values {
        prompt.push_str(namespace);
        prompt.push('.');
        prompt.push_str(name);
        prompt.push_str(": ");
        prompt.push_str(value);
        prompt.push('\n');
    }
}

fn parse_prediction(signature: &Signature, text: &str) -> Result<Prediction, DspyError> {
    let names: Vec<String> = signature
        .output_fields()
        .map(|field| field.name.clone())
        .collect();
    let outputs = parse_named_fields(text, &names);
    signature.validate_outputs(&outputs)?;
    Ok(Prediction::new(outputs))
}

fn parse_chain_of_thought(signature: &Signature, text: &str) -> Result<Prediction, DspyError> {
    let mut names = vec!["reasoning".to_owned()];
    names.extend(signature.output_fields().map(|field| field.name.clone()));
    let mut parsed = parse_named_fields(text, &names);
    let reasoning = parsed
        .remove("reasoning")
        .ok_or_else(|| DspyError::Parse("missing `reasoning` field".to_owned()))?;
    signature.validate_outputs(&parsed)?;
    Ok(Prediction::with_reasoning(parsed, reasoning))
}

fn parse_named_fields(text: &str, names: &[String]) -> Values {
    let mut result = Values::new();
    let mut current: Option<String> = None;

    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() {
            continue;
        }

        let parsed = line
            .split_once(':')
            .or_else(|| line.split_once('='))
            .map(|(name, value)| (name.trim(), value.trim()));
        let matched = if let Some((candidate, value)) = parsed {
            if let Some(name) = names.iter().find(|name| name.as_str() == candidate) {
                result.insert(name.clone(), value.to_owned());
                current = Some(name.clone());
                true
            } else {
                false
            }
        } else {
            false
        };

        if !matched {
            if let Some(name) = &current {
                if let Some(value) = result.get_mut(name) {
                    if !value.is_empty() {
                        value.push('\n');
                    }
                    value.push_str(line);
                }
            }
        }
    }

    result
}

fn parse_action_intent(text: &str) -> Result<Option<ActionIntent>, DspyError> {
    let mut tool: Option<String> = None;
    let mut rationale: Option<String> = None;
    let mut arguments = Values::new();

    for raw in text.lines() {
        let line = raw.trim();
        if let Some(value) = line
            .strip_prefix("action.tool:")
            .or_else(|| line.strip_prefix("action.tool="))
        {
            let candidate = value.trim();
            if candidate.is_empty() {
                return Err(DspyError::Parse("empty action.tool".to_owned()));
            }
            tool = Some(candidate.to_owned());
        } else if let Some(value) = line
            .strip_prefix("action.rationale:")
            .or_else(|| line.strip_prefix("action.rationale="))
        {
            rationale = Some(value.trim().to_owned());
        } else if let Some(rest) = line.strip_prefix("action.arg.") {
            let (name, value) = rest
                .split_once(':')
                .or_else(|| rest.split_once('='))
                .ok_or_else(|| DspyError::Parse(format!("malformed action argument: {line}")))?;
            let name = name.trim();
            if name.is_empty() {
                return Err(DspyError::Parse("empty action argument name".to_owned()));
            }
            arguments.insert(name.to_owned(), value.trim().to_owned());
        }
    }

    Ok(tool.map(|tool| ActionIntent {
        tool,
        arguments,
        rationale,
    }))
}
