use std::collections::BTreeSet;
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
///
/// This is intentionally data-only. There is no callback, executable closure, process handle,
/// filesystem handle, network client, or ambient tool authority in the type.
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

pub type ReactFuture<'a> =
    std::pin::Pin<Box<dyn std::future::Future<Output = Result<ReactTurn, DspyError>> + Send + 'a>>;

/// DSPy ReAct with a hard authority fence.
///
/// `ReAct` can propose a tool intent, but it cannot execute one. The host must admit and actuate
/// through its own broker, then supply the resulting observation to a later `step`.
#[derive(Clone)]
pub struct ReAct {
    signature: Signature,
    model: Arc<dyn LanguageModel>,
    allowed_tools: BTreeSet<String>,
    demonstrations: Vec<Example>,
}

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
                signature
                    .input_fields()
                    .filter_map(|field| example.inputs.get(&field.name).map(|value| (&field.name, value))),
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
