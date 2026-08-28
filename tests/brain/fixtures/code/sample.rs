//! Fixture module for code_chunking tests.

const VERSION: &str = "1.0";

fn helper(x: i32) -> i32 {
    x + 1
}

struct Widget {
    name: String,
}

impl Widget {
    fn new(name: String) -> Self {
        Widget { name }
    }

    fn render(&self) -> String {
        format!("<{}>", self.name)
    }
}
