pub struct Store {
    entries: Vec<String>,
}

pub enum Backend {
    Memory,
    Disk,
}

pub trait Persist {
    fn flush(&self);
}

impl Store {
    pub fn open(_path: &str) -> Store {
        Store { entries: Vec::new() }
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }
}
