"""Analyzer fixture — source from which nothing can be derived.

The negative fixture, and it is not an afterthought. An analyzer scored only
against a repository where it succeeds cannot be distinguished from one that
emits something for every function it sees, and *fluent, plausible and wrong*
is the failure this project has measured twice by two different mechanisms
(finding 004's confidently-wrong docstrings, finding 007's alias-generator
result: 15 of 69 endpoints with a contract wrong about every field name on the
wire, and nothing in the output indicating it).

So: no annotations, no guards, no asserts, no raises, no aggregate bindings.
The correct derivation is **empty**, and `expected.json` says so.
"""


def transform(payload):
    result = payload
    for step in _STEPS:
        result = step(result)
    return result


def _double(value):
    return value * 2


def _stringify(value):
    return str(value)


_STEPS = (_double, _stringify)


class Pipeline:
    def __init__(self, steps):
        self.steps = steps

    def run(self, payload):
        out = payload
        for step in self.steps:
            out = step(out)
        return out
