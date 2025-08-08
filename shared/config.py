from dataclasses import dataclass

@dataclass
class GenSpec:
    choices: int = 5
    count_math: int = 5
    count_thinking: int = 5
    count_reading: int = 5