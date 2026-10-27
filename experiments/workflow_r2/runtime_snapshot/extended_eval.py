"""Keep original benchmark predicates immutable; add separately named coverage."""
from .bank_runner import test_bank


def evaluate(source,question_id):
    if question_id in ('07','17'):
        from .struct_checks import test_struct
        return test_struct(source,question_id)
    return test_bank(source,question_id)
