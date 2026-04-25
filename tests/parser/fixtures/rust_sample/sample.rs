fn add(a: i32, b: i32) -> i32 {
    a + b
}
pub struct Calculator {
    value: i32,
}
impl Calculator {
    pub fn new() -> Self {
        Calculator { value: 0 }
    }
    pub fn increment(&mut self) {
        self.value += 1
    }
}
fn main() {
    let mut c = Calculator::new();
    c.increment();
    println!("{}", add(c.value, 1));
}
