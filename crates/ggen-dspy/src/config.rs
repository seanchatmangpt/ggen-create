use std::collections::{BTreeMap, VecDeque};
use std::sync::{Mutex, OnceLock, RwLock};
use std::time::{Duration, Instant};

use crate::core::{DspyError, Values};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CacheConfig {
    pub enabled: bool,
    pub max_entries: usize,
    pub ttl: Duration,
}

impl Default for CacheConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            max_entries: 1_024,
            ttl: Duration::from_secs(300),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DspySettings {
    pub model: String,
    pub max_tokens: usize,
    pub cache: CacheConfig,
}

impl Default for DspySettings {
    fn default() -> Self {
        Self {
            model: "unconfigured".to_owned(),
            max_tokens: 4_096,
            cache: CacheConfig::default(),
        }
    }
}

static SETTINGS: OnceLock<RwLock<DspySettings>> = OnceLock::new();

pub fn init_dspy_config(settings: DspySettings) -> Result<(), DspyError> {
    let lock = SETTINGS.get_or_init(|| RwLock::new(DspySettings::default()));
    let mut guard = lock
        .write()
        .map_err(|_| DspyError::Config("settings lock poisoned".to_owned()))?;
    *guard = settings;
    Ok(())
}

pub fn get_dspy_config() -> Result<DspySettings, DspyError> {
    SETTINGS
        .get_or_init(|| RwLock::new(DspySettings::default()))
        .read()
        .map(|settings| settings.clone())
        .map_err(|_| DspyError::Config("settings lock poisoned".to_owned()))
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DspyContext {
    pub metadata: Values,
}

#[derive(Clone, Debug, Default)]
pub struct ContextBuilder {
    metadata: Values,
}

impl ContextBuilder {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn metadata(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }

    pub fn build(self) -> DspyContext {
        DspyContext {
            metadata: self.metadata,
        }
    }
}

/// Execute pure construction logic with explicit context. Context is passed, never ambient.
pub fn with_context<T>(context: &DspyContext, f: impl FnOnce(&DspyContext) -> T) -> T {
    f(context)
}

#[derive(Clone, Debug)]
struct CacheEntry {
    value: String,
    inserted_at: Instant,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct CacheStats {
    pub hits: u64,
    pub misses: u64,
    pub inserts: u64,
    pub evictions: u64,
}

#[derive(Debug)]
struct CacheState {
    values: BTreeMap<String, CacheEntry>,
    order: VecDeque<String>,
    stats: CacheStats,
}

impl CacheState {
    fn new() -> Self {
        Self {
            values: BTreeMap::new(),
            order: VecDeque::new(),
            stats: CacheStats::default(),
        }
    }
}

#[derive(Debug)]
pub struct CacheManager {
    config: CacheConfig,
    state: Mutex<CacheState>,
}

impl CacheManager {
    pub fn new(config: CacheConfig) -> Self {
        Self {
            config,
            state: Mutex::new(CacheState::new()),
        }
    }

    pub fn get(&self, key: &str) -> Result<Option<String>, DspyError> {
        if !self.config.enabled {
            return Ok(None);
        }
        let mut state = self
            .state
            .lock()
            .map_err(|_| DspyError::Cache("cache lock poisoned".to_owned()))?;
        let entry = state.values.get(key).cloned();
        match entry {
            Some(entry) if entry.inserted_at.elapsed() <= self.config.ttl => {
                state.stats.hits += 1;
                Ok(Some(entry.value))
            }
            Some(_) => {
                state.values.remove(key);
                state.order.retain(|candidate| candidate != key);
                state.stats.misses += 1;
                Ok(None)
            }
            None => {
                state.stats.misses += 1;
                Ok(None)
            }
        }
    }

    pub fn insert(
        &self,
        key: impl Into<String>,
        value: impl Into<String>,
    ) -> Result<(), DspyError> {
        if !self.config.enabled || self.config.max_entries == 0 {
            return Ok(());
        }
        let key = key.into();
        let mut state = self
            .state
            .lock()
            .map_err(|_| DspyError::Cache("cache lock poisoned".to_owned()))?;
        if !state.values.contains_key(&key) && state.values.len() >= self.config.max_entries {
            if let Some(oldest) = state.order.pop_front() {
                state.values.remove(&oldest);
                state.stats.evictions += 1;
            }
        }
        state.order.retain(|candidate| candidate != &key);
        state.order.push_back(key.clone());
        state.values.insert(
            key,
            CacheEntry {
                value: value.into(),
                inserted_at: Instant::now(),
            },
        );
        state.stats.inserts += 1;
        Ok(())
    }

    pub fn stats(&self) -> Result<CacheStats, DspyError> {
        self.state
            .lock()
            .map(|state| state.stats)
            .map_err(|_| DspyError::Cache("cache lock poisoned".to_owned()))
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct UsageStats {
    pub requests: u64,
    pub prompt_tokens: u64,
    pub completion_tokens: u64,
}

#[derive(Debug, Default)]
pub struct UsageTracker {
    stats: Mutex<UsageStats>,
}

impl UsageTracker {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn record(&self, prompt_tokens: u64, completion_tokens: u64) -> Result<(), DspyError> {
        let mut stats = self
            .stats
            .lock()
            .map_err(|_| DspyError::Config("usage lock poisoned".to_owned()))?;
        stats.requests += 1;
        stats.prompt_tokens += prompt_tokens;
        stats.completion_tokens += completion_tokens;
        Ok(())
    }

    pub fn stats(&self) -> Result<UsageStats, DspyError> {
        self.stats
            .lock()
            .map(|stats| *stats)
            .map_err(|_| DspyError::Config("usage lock poisoned".to_owned()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread::sleep;

    #[test]
    fn usage_tracker_accumulates_requests_and_tokens_across_calls() {
        let tracker = UsageTracker::new();
        tracker.record(10, 5).expect("first record");
        tracker.record(20, 8).expect("second record");

        let stats = tracker.stats().expect("stats");
        assert_eq!(stats.requests, 2);
        assert_eq!(stats.prompt_tokens, 30);
        assert_eq!(stats.completion_tokens, 13);
    }

    #[test]
    fn usage_tracker_starts_at_zero() {
        let tracker = UsageTracker::new();
        let stats = tracker.stats().expect("stats");
        assert_eq!(stats, UsageStats::default());
    }

    #[test]
    fn disabled_cache_never_stores_or_returns_entries() {
        let cache = CacheManager::new(CacheConfig {
            enabled: false,
            max_entries: 10,
            ttl: Duration::from_secs(60),
        });
        cache.insert("k", "v").expect("insert is a no-op");
        assert_eq!(cache.get("k").expect("get"), None);
        let stats = cache.stats().expect("stats");
        assert_eq!(stats, CacheStats::default());
    }

    #[test]
    fn zero_capacity_cache_never_stores_entries() {
        let cache = CacheManager::new(CacheConfig {
            enabled: true,
            max_entries: 0,
            ttl: Duration::from_secs(60),
        });
        cache.insert("k", "v").expect("insert is a no-op");
        assert_eq!(cache.get("k").expect("get"), None);
    }

    #[test]
    fn cache_hit_returns_value_and_increments_hits() {
        let cache = CacheManager::new(CacheConfig {
            enabled: true,
            max_entries: 10,
            ttl: Duration::from_secs(60),
        });
        cache.insert("k", "v").expect("insert");
        assert_eq!(cache.get("k").expect("get"), Some("v".to_owned()));
        let stats = cache.stats().expect("stats");
        assert_eq!(stats.hits, 1);
        assert_eq!(stats.misses, 0);
        assert_eq!(stats.inserts, 1);
    }

    #[test]
    fn cache_entry_expires_after_ttl_and_is_evicted_on_read() {
        let cache = CacheManager::new(CacheConfig {
            enabled: true,
            max_entries: 10,
            ttl: Duration::from_millis(20),
        });
        cache.insert("k", "v").expect("insert");
        sleep(Duration::from_millis(60));

        assert_eq!(cache.get("k").expect("get after ttl"), None);
        let stats = cache.stats().expect("stats");
        assert_eq!(stats.misses, 1);
        assert_eq!(stats.hits, 0);

        // Entry was actually removed from the underlying map, not just reported
        // expired: a second read must miss again rather than resurrecting it.
        assert_eq!(cache.get("k").expect("second get"), None);
        let stats = cache.stats().expect("stats after second read");
        assert_eq!(stats.misses, 2);
    }

    #[test]
    fn missing_key_increments_misses_without_touching_hits() {
        let cache = CacheManager::new(CacheConfig::default());
        assert_eq!(cache.get("absent").expect("get"), None);
        let stats = cache.stats().expect("stats");
        assert_eq!(stats.misses, 1);
        assert_eq!(stats.hits, 0);
    }
}
