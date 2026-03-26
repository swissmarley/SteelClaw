# Calculator

Evaluate mathematical expressions and perform calculations.

## Metadata
- version: 1.0.0
- author: SteelClaw
- triggers: calculate, math, calc, compute, evaluate

## System Prompt
You can evaluate mathematical expressions using the calculate tool.
It supports basic arithmetic, powers, roots, trig functions, and more.
Use it whenever the user asks for a calculation rather than computing in your head.

## Tools

### calculate
Evaluate a mathematical expression safely.

**Parameters:**
- `expression` (string, required): The math expression to evaluate (e.g. "2**10", "sqrt(144)", "sin(pi/4)")

### unit_convert
Convert between common units.

**Parameters:**
- `value` (number, required): The numeric value to convert
- `from_unit` (string, required): Source unit (e.g. "km", "lb", "celsius")
- `to_unit` (string, required): Target unit (e.g. "miles", "kg", "fahrenheit")
