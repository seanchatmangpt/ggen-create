use std::collections::BTreeMap;

use crate::core::Values;

/// Canonical reusable DSPy program families recovered from the historical crate.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum AgentPattern {
    Predict,
    ChainOfThought,
    ReAct,
    Retrieve,
    MultiHopQA,
    SimplifiedBaleen,
    ProgramOfThought,
}

impl AgentPattern {
    pub fn name(&self) -> &'static str {
        match self {
            Self::Predict => "predict",
            Self::ChainOfThought => "chain_of_thought",
            Self::ReAct => "react",
            Self::Retrieve => "retrieve",
            Self::MultiHopQA => "multihop_qa",
            Self::SimplifiedBaleen => "simplified_baleen",
            Self::ProgramOfThought => "program_of_thought",
        }
    }
}

/// A pattern declaration is configuration, not an executable program.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PatternSpec {
    pub pattern: AgentPattern,
    pub parameters: Values,
}

#[derive(Clone, Debug)]
pub struct PatternBuilder {
    pattern: AgentPattern,
    parameters: Values,
}

impl PatternBuilder {
    pub fn new(pattern: AgentPattern) -> Self {
        Self {
            pattern,
            parameters: Values::new(),
        }
    }

    pub fn parameter(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.parameters.insert(key.into(), value.into());
        self
    }

    pub fn build(self) -> PatternSpec {
        PatternSpec {
            pattern: self.pattern,
            parameters: self.parameters,
        }
    }
}

#[derive(Clone, Debug)]
pub struct PatternLibrary {
    patterns: BTreeMap<String, PatternSpec>,
}

impl Default for PatternLibrary {
    fn default() -> Self {
        let mut library = Self {
            patterns: BTreeMap::new(),
        };
        for pattern in [
            AgentPattern::Predict,
            AgentPattern::ChainOfThought,
            AgentPattern::ReAct,
            AgentPattern::Retrieve,
            AgentPattern::MultiHopQA,
            AgentPattern::SimplifiedBaleen,
            AgentPattern::ProgramOfThought,
        ] {
            library.register(PatternBuilder::new(pattern).build());
        }
        library
    }
}

impl PatternLibrary {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn register(&mut self, spec: PatternSpec) {
        self.patterns.insert(spec.pattern.name().to_owned(), spec);
    }

    pub fn get(&self, name: &str) -> Option<&PatternSpec> {
        self.patterns.get(name)
    }

    pub fn names(&self) -> impl Iterator<Item = &str> {
        self.patterns.keys().map(String::as_str)
    }
}
