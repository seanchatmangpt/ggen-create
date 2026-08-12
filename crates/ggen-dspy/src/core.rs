use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::fmt;
use std::future::Future;
use std::pin::Pin;

/// Deterministic name/value carrier used by signatures, examples, and predictions.
pub type Values = BTreeMap<String, String>;

/// A field's role in a DSPy signature.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FieldKind {
    Input,
    Output,
}

/// A typed field in a [`Signature`].
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Field {
    pub name: String,
    pub description: String,
    pub kind: FieldKind,
}

impl Field {
    pub fn input(name: impl Into<String>, description: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
            kind: FieldKind::Input,
        }
    }

    pub fn output(name: impl Into<String>, description: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
            kind: FieldKind::Output,
        }
    }
}

/// Historical DSPy-compatible input field constructor.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InputField(Field);

impl InputField {
    pub fn new(name: impl Into<String>, description: impl Into<String>) -> Self {
        Self(Field::input(name, description))
    }
}

impl From<InputField> for Field {
    fn from(value: InputField) -> Self {
        value.0
    }
}

/// Historical DSPy-compatible output field constructor.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OutputField(Field);

impl OutputField {
    pub fn new(name: impl Into<String>, description: impl Into<String>) -> Self {
        Self(Field::output(name, description))
    }
}

impl From<OutputField> for Field {
    fn from(value: OutputField) -> Self {
        value.0
    }
}

/// A typed DSPy signature.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Signature {
    pub name: String,
    pub instructions: String,
    fields: Vec<Field>,
}

impl Signature {
    pub fn new(
        name: impl Into<String>,
        instructions: impl Into<String>,
        fields: impl IntoIterator<Item = Field>,
    ) -> Result<Self> {
        let name = name.into();
        let instructions = instructions.into();
        let fields: Vec<Field> = fields.into_iter().collect();

        if name.trim().is_empty() {
            return Err(DspyError::InvalidSignature(
                "signature name must not be empty".to_owned(),
            ));
        }

        let mut seen = BTreeSet::new();
        let mut outputs = 0usize;
        for field in &fields {
            validate_field_name(&field.name)?;
            if !seen.insert(field.name.clone()) {
                return Err(DspyError::InvalidSignature(format!(
                    "duplicate field: {}",
                    field.name
                )));
            }
            if field.kind == FieldKind::Output {
                outputs += 1;
            }
        }

        if outputs == 0 {
            return Err(DspyError::InvalidSignature(
                "signature must declare at least one output".to_owned(),
            ));
        }

        Ok(Self {
            name,
            instructions,
            fields,
        })
    }

    /// Start a compatibility builder matching the historical Rust DSPy API.
    pub fn builder() -> SignatureBuilder {
        SignatureBuilder::default()
    }

    pub fn fields(&self) -> &[Field] {
        &self.fields
    }

    pub fn input_fields(&self) -> impl Iterator<Item = &Field> {
        self.fields
            .iter()
            .filter(|field| field.kind == FieldKind::Input)
    }

    pub fn output_fields(&self) -> impl Iterator<Item = &Field> {
        self.fields
            .iter()
            .filter(|field| field.kind == FieldKind::Output)
    }

    pub fn with_instructions(&self, instructions: impl Into<String>) -> Self {
        Self {
            name: self.name.clone(),
            instructions: instructions.into(),
            fields: self.fields.clone(),
        }
    }

    pub fn validate_inputs(&self, values: &Values) -> Result<()> {
        for field in self.input_fields() {
            if !values.contains_key(&field.name) {
                return Err(DspyError::MissingInput(field.name.clone()));
            }
        }
        Ok(())
    }

    pub fn validate_outputs(&self, values: &Values) -> Result<()> {
        for field in self.output_fields() {
            if !values.contains_key(&field.name) {
                return Err(DspyError::MissingOutput(field.name.clone()));
            }
        }
        Ok(())
    }

    pub fn validate_example(&self, example: &Example) -> Result<()> {
        self.validate_inputs(&example.inputs)?;
        self.validate_outputs(&example.outputs)
    }
}

/// Builder retained for source-level compatibility with the historical crate.
#[derive(Clone, Debug)]
pub struct SignatureBuilder {
    name: String,
    instructions: String,
    fields: Vec<Field>,
}

impl Default for SignatureBuilder {
    fn default() -> Self {
        Self {
            name: "anonymous".to_owned(),
            instructions: String::new(),
            fields: Vec::new(),
        }
    }
}

impl SignatureBuilder {
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.name = name.into();
        self
    }

    pub fn instructions(mut self, instructions: impl Into<String>) -> Self {
        self.instructions = instructions.into();
        self
    }

    pub fn input(mut self, field: InputField) -> Self {
        self.fields.push(field.into());
        self
    }

    pub fn output(mut self, field: OutputField) -> Self {
        self.fields.push(field.into());
        self
    }

    pub fn build(self) -> Result<Signature> {
        Signature::new(self.name, self.instructions, self.fields)
    }
}

fn validate_field_name(name: &str) -> Result<()> {
    let trimmed = name.trim();
    if trimmed.is_empty()
        || trimmed != name
        || name
            .chars()
            .any(|ch| ch.is_whitespace() || matches!(ch, ':' | '=' | '\n' | '\r'))
    {
        return Err(DspyError::InvalidSignature(format!(
            "field name is not line-protocol safe: {name:?}"
        )));
    }
    Ok(())
}

/// A supervised example suitable for few-shot optimization.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Example {
    pub inputs: Values,
    pub outputs: Values,
}

impl Example {
    pub fn new(inputs: Values, outputs: Values) -> Self {
        Self { inputs, outputs }
    }
}

/// The only request a DSPy module may issue to its model dependency.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PromptRequest {
    pub prompt: String,
    pub metadata: Values,
}

impl PromptRequest {
    pub fn new(prompt: impl Into<String>) -> Self {
        Self {
            prompt: prompt.into(),
            metadata: Values::new(),
        }
    }
}

/// Model completion text before typed signature parsing.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Completion {
    pub text: String,
}

impl Completion {
    pub fn new(text: impl Into<String>) -> Self {
        Self { text: text.into() }
    }
}

/// A typed module result.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Prediction {
    pub outputs: Values,
    pub reasoning: Option<String>,
}

impl Prediction {
    pub fn new(outputs: Values) -> Self {
        Self {
            outputs,
            reasoning: None,
        }
    }

    pub fn with_reasoning(outputs: Values, reasoning: impl Into<String>) -> Self {
        Self {
            outputs,
            reasoning: Some(reasoning.into()),
        }
    }

    pub fn get(&self, field: &str) -> Option<&str> {
        self.outputs.get(field).map(String::as_str)
    }

    pub fn set(&mut self, field: impl Into<String>, value: impl Into<String>) {
        self.outputs.insert(field.into(), value.into());
    }

    pub fn fields(&self) -> &Values {
        &self.outputs
    }

    pub fn from_fields(outputs: Values) -> Self {
        Self::new(outputs)
    }
}

/// Historical name for a module result.
pub type ModuleOutput = Prediction;

/// Non-authoritative metadata supplied to module construction.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ModuleContext {
    pub metadata: Values,
}

impl ModuleContext {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn set_metadata(&mut self, key: impl Into<String>, value: impl Into<String>) {
        self.metadata.insert(key.into(), value.into());
    }

    pub fn get_metadata(&self, key: &str) -> Option<&str> {
        self.metadata.get(key).map(String::as_str)
    }
}

/// Typed failures at the DSPy construction boundary.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DspyError {
    InvalidSignature(String),
    MissingInput(String),
    MissingOutput(String),
    InvalidExample(String),
    Model(String),
    Parse(String),
    Metric(String),
    Config(String),
    Cache(String),
    Assertion(String),
    UnknownTool(String),
    Refused(String),
}

impl fmt::Display for DspyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidSignature(detail) => write!(f, "invalid signature: {detail}"),
            Self::MissingInput(field) => write!(f, "missing required input: {field}"),
            Self::MissingOutput(field) => write!(f, "missing required output: {field}"),
            Self::InvalidExample(detail) => write!(f, "invalid example: {detail}"),
            Self::Model(detail) => write!(f, "model failure: {detail}"),
            Self::Parse(detail) => write!(f, "prediction parse failure: {detail}"),
            Self::Metric(detail) => write!(f, "metric failure: {detail}"),
            Self::Config(detail) => write!(f, "configuration failure: {detail}"),
            Self::Cache(detail) => write!(f, "cache failure: {detail}"),
            Self::Assertion(detail) => write!(f, "assertion failure: {detail}"),
            Self::UnknownTool(tool) => write!(f, "REFUSED:UNKNOWN_TOOL:{tool}"),
            Self::Refused(reason) => write!(f, "REFUSED:{reason}"),
        }
    }
}

impl Error for DspyError {}

pub type Result<T> = std::result::Result<T, DspyError>;

/// Object-safe future returned by language-model adapters.
pub type ModelFuture<'a> = Pin<Box<dyn Future<Output = Result<Completion>> + Send + 'a>>;

/// Minimal model boundary. Implementations provide inference, not actuation authority.
pub trait LanguageModel: Send + Sync {
    fn complete<'a>(&'a self, request: &'a PromptRequest) -> ModelFuture<'a>;
}

/// Object-safe future returned by DSPy modules.
pub type ModuleFuture<'a> = Pin<Box<dyn Future<Output = Result<Prediction>> + Send + 'a>>;

/// A typed DSPy module that manufactures a prediction from admitted inputs.
pub trait Module: Send + Sync {
    fn forward<'a>(&'a self, inputs: &'a Values) -> ModuleFuture<'a>;

    fn name(&self) -> &str {
        std::any::type_name::<Self>()
    }
}
