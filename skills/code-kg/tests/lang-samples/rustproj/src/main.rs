mod store;

use crate::store::Store;

fn main() {
    let s = Store::open("agent.db");
    println!("{}", s.len());
}
