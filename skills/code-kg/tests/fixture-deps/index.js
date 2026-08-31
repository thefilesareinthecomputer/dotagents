const leftpad = require("leftpad");

function banner(text) {
  return leftpad(text, 20);
}

console.log(banner("deps fixture"));
