"""场景断言。"""

__all__ = ["AssertRunner"]


def __getattr__(name: str):
    if name == "AssertRunner":
        from auth_harness.assertions.runner import AssertRunner

        return AssertRunner
    raise AttributeError(name)
