use std::error::Error;
use std::fmt;
use std::sync::Arc;

use crate::core::{DspyError, Prediction};

type Predicate = Arc<dyn Fn(&Prediction) -> bool + Send + Sync>;

/// A hard runtime constraint over a manufactured prediction.
#[derive(Clone)]
pub struct Assert {
    name: String,
    message: String,
    predicate: Predicate,
}

impl Assert {
    pub fn new(
        name: impl Into<String>,
        message: impl Into<String>,
        predicate: impl Fn(&Prediction) -> bool + Send + Sync + 'static,
    ) -> Self {
        Self {
            name: name.into(),
            message: message.into(),
            predicate: Arc::new(predicate),
        }
    }

    pub fn field_nonempty(field: impl Into<String>) -> Self {
        let field = field.into();
        let name = format!("field_nonempty:{field}");
        let message = format!("field `{field}` must not be empty");
        Self::new(name, message, move |prediction| {
            prediction
                .get(&field)
                .map(str::trim)
                .is_some_and(|value| !value.is_empty())
        })
    }

    pub fn check(&self, prediction: &Prediction) -> Result<(), AssertionError> {
        if (self.predicate)(prediction) {
            Ok(())
        } else {
            Err(AssertionError {
                name: self.name.clone(),
                message: self.message.clone(),
                advisory: false,
            })
        }
    }
}

/// A soft constraint. Failure is evidence the caller may use for repair/retry, never authority.
#[derive(Clone)]
pub struct Suggest {
    name: String,
    message: String,
    predicate: Predicate,
}

impl Suggest {
    pub fn new(
        name: impl Into<String>,
        message: impl Into<String>,
        predicate: impl Fn(&Prediction) -> bool + Send + Sync + 'static,
    ) -> Self {
        Self {
            name: name.into(),
            message: message.into(),
            predicate: Arc::new(predicate),
        }
    }

    pub fn check(&self, prediction: &Prediction) -> Result<(), AssertionError> {
        if (self.predicate)(prediction) {
            Ok(())
        } else {
            Err(AssertionError {
                name: self.name.clone(),
                message: self.message.clone(),
                advisory: true,
            })
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AssertionError {
    pub name: String,
    pub message: String,
    pub advisory: bool,
}

impl fmt::Display for AssertionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let kind = if self.advisory { "suggest" } else { "assert" };
        write!(f, "{kind}:{}: {}", self.name, self.message)
    }
}

impl Error for AssertionError {}

impl From<AssertionError> for DspyError {
    fn from(value: AssertionError) -> Self {
        DspyError::Assertion(value.to_string())
    }
}
