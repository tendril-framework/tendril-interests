

from enum import IntEnum


class ExportLevel(IntEnum):
    ID_ONLY = 0
    STUB = 1
    NORMAL = 2
    DETAILED = 3
    EVERYTHING = 4


def rewrap_interest(model):
    from tendril import interests
    type_name = model.type
    return interests.type_codes[type_name](model)


def get_interest_stub(interest):
    return interest.export(export_level=ExportLevel.STUB)
