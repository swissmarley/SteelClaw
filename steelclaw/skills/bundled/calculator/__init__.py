"""Calculator skill — safe math evaluation and unit conversion."""

from __future__ import annotations

import math


# Allowed names for safe eval
_SAFE_NAMES = {
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "int": int, "float": float, "pow": pow, "len": len,
    # math constants
    "pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf,
    # math functions
    "sqrt": math.sqrt, "cbrt": lambda x: x ** (1/3),
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "log": math.log, "log2": math.log2, "log10": math.log10,
    "exp": math.exp, "ceil": math.ceil, "floor": math.floor,
    "factorial": math.factorial, "gcd": math.gcd,
    "radians": math.radians, "degrees": math.degrees,
    "hypot": math.hypot,
}


async def tool_calculate(expression: str) -> str:
    """Evaluate a mathematical expression safely."""
    try:
        # Block dangerous builtins
        result = eval(expression, {"__builtins__": {}}, _SAFE_NAMES)  # noqa: S307
        if isinstance(result, float) and result == int(result) and abs(result) < 1e15:
            result = int(result)
        return f"{expression} = {result}"
    except ZeroDivisionError:
        return "Error: Division by zero"
    except Exception as e:
        return f"Error evaluating '{expression}': {e}"


# Unit conversion tables
_CONVERSIONS = {
    # Length (base: meters)
    "m": ("length", 1.0), "km": ("length", 1000.0), "cm": ("length", 0.01),
    "mm": ("length", 0.001), "miles": ("length", 1609.344), "mi": ("length", 1609.344),
    "feet": ("length", 0.3048), "ft": ("length", 0.3048),
    "inches": ("length", 0.0254), "in": ("length", 0.0254),
    "yards": ("length", 0.9144), "yd": ("length", 0.9144),
    # Weight (base: kg)
    "kg": ("weight", 1.0), "g": ("weight", 0.001), "mg": ("weight", 0.000001),
    "lb": ("weight", 0.453592), "lbs": ("weight", 0.453592),
    "oz": ("weight", 0.0283495), "ton": ("weight", 907.185),
    "tonne": ("weight", 1000.0),
    # Temperature (special)
    "celsius": ("temp", None), "c": ("temp", None),
    "fahrenheit": ("temp", None), "f": ("temp", None),
    "kelvin": ("temp", None), "k": ("temp", None),
    # Volume (base: liters)
    "l": ("volume", 1.0), "ml": ("volume", 0.001),
    "gal": ("volume", 3.78541), "gallon": ("volume", 3.78541),
    "cup": ("volume", 0.236588), "tbsp": ("volume", 0.0147868),
    "tsp": ("volume", 0.00492892),
    # Speed (base: m/s)
    "m/s": ("speed", 1.0), "km/h": ("speed", 0.277778), "kph": ("speed", 0.277778),
    "mph": ("speed", 0.44704), "knots": ("speed", 0.514444),
}


def _convert_temp(value: float, from_u: str, to_u: str) -> float:
    """Convert temperature units."""
    from_u = from_u.lower()
    to_u = to_u.lower()
    # Normalize
    if from_u in ("celsius", "c"):
        c = value
    elif from_u in ("fahrenheit", "f"):
        c = (value - 32) * 5 / 9
    elif from_u in ("kelvin", "k"):
        c = value - 273.15
    else:
        raise ValueError(f"Unknown temperature unit: {from_u}")

    if to_u in ("celsius", "c"):
        return c
    elif to_u in ("fahrenheit", "f"):
        return c * 9 / 5 + 32
    elif to_u in ("kelvin", "k"):
        return c + 273.15
    else:
        raise ValueError(f"Unknown temperature unit: {to_u}")


async def tool_unit_convert(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between units."""
    from_u = from_unit.lower().strip()
    to_u = to_unit.lower().strip()

    from_info = _CONVERSIONS.get(from_u)
    to_info = _CONVERSIONS.get(to_u)

    if not from_info:
        return f"Unknown unit: {from_unit}"
    if not to_info:
        return f"Unknown unit: {to_unit}"

    from_category, from_factor = from_info
    to_category, to_factor = to_info

    if from_category != to_category:
        return f"Cannot convert between {from_category} and {to_category}"

    if from_category == "temp":
        result = _convert_temp(value, from_u, to_u)
    else:
        # Convert via base unit
        base_value = value * from_factor
        result = base_value / to_factor

    result = round(result, 6)
    return f"{value} {from_unit} = {result} {to_unit}"
