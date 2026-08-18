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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::Values;

    fn prediction_with(field: &str, value: &str) -> Prediction {
        let mut outputs = Values::new();
        outputs.insert(field.to_string(), value.to_string());
        Prediction::new(outputs)
    }

    #[test]
    fn field_nonempty_passes_when_field_present_and_nonblank() {
        let assertion = Assert::field_nonempty("answer");
        let prediction = prediction_with("answer", "42");

        assert!(assertion.check(&prediction).is_ok());
    }

    #[test]
    fn field_nonempty_fails_when_field_missing() {
        let assertion = Assert::field_nonempty("answer");
        let prediction = prediction_with("other", "42");

        let err = assertion.check(&prediction).unwrap_err();
        assert_eq!(err.name, "field_nonempty:answer");
        assert!(!err.advisory);
    }

    #[test]
    fn field_nonempty_fails_when_value_is_whitespace_only() {
        let assertion = Assert::field_nonempty("answer");
        let prediction = prediction_with("answer", "   \t  ");

        assert!(assertion.check(&prediction).is_err());
    }

    #[test]
    fn field_nonempty_trims_surrounding_whitespace_before_checking() {
        let assertion = Assert::field_nonempty("answer");
        let prediction = prediction_with("answer", "  42  ");

        assert!(assertion.check(&prediction).is_ok());
    }

    #[test]
    fn assert_check_failure_is_not_advisory() {
        let assertion = Assert::new("always_fail", "nope", |_| false);
        let prediction = Prediction::new(Values::new());

        let err = assertion.check(&prediction).unwrap_err();
        assert_eq!(err.name, "always_fail");
        assert_eq!(err.message, "nope");
        assert!(!err.advisory);
    }

    #[test]
    fn suggest_check_failure_is_advisory() {
        let suggestion = Suggest::new("soft_check", "consider retrying", |_| false);
        let prediction = Prediction::new(Values::new());

        let err = suggestion.check(&prediction).unwrap_err();
        assert_eq!(err.name, "soft_check");
        assert_eq!(err.message, "consider retrying");
        assert!(err.advisory);
    }

    #[test]
    fn suggest_check_passes_when_predicate_true() {
        let suggestion = Suggest::new("soft_check", "consider retrying", |_| true);
        let prediction = Prediction::new(Values::new());

        assert!(suggestion.check(&prediction).is_ok());
    }

    #[test]
    fn assertion_error_display_distinguishes_assert_from_suggest() {
        let hard = AssertionError {
            name: "n".to_string(),
            message: "m".to_string(),
            advisory: false,
        };
        let soft = AssertionError {
            name: "n".to_string(),
            message: "m".to_string(),
            advisory: true,
        };

        assert_eq!(hard.to_string(), "assert:n: m");
        assert_eq!(soft.to_string(), "suggest:n: m");
    }

    #[test]
    fn assertion_error_converts_into_dspy_error() {
        let err = AssertionError {
            name: "n".to_string(),
            message: "m".to_string(),
            advisory: false,
        };

        let dspy_err: DspyError = err.into();
        match dspy_err {
            DspyError::Assertion(msg) => assert_eq!(msg, "assert:n: m"),
            other => panic!("expected DspyError::Assertion, got {other:?}"),
        }
    }
}
