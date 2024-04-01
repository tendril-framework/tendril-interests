

from pydantic.schema import schema
from inflection import titleize


class PolicyBase(object):
    name = 'base'
    context_spec = None
    write_requires = None
    schema = None
    hints = None

    def __init__(self, actual):
        self._actual = actual

    @property
    def attached_to(self):
        return self._actual

    def validate(self, data):
        return

    @classmethod
    def can_assign_to(cls):
        rv = {'interest_types':set()}
        for spec in cls.context_spec:
            if spec['domain'] == 'interests':
                rv['interest_types'].add(spec['interest_type'])
                if spec['inherits_from'] == 'ancestors':
                    from tendril.interests import possible_parents
                    for parent in possible_parents[spec['interest_type']]:
                        rv['interest_types'].add(parent)
        return rv

    @classmethod
    def applies_to(cls):
        rv = {'interest_types': set()}
        for spec in cls.context_spec:
            if spec['domain'] == 'interests':
                rv['interest_types'].add(spec['interest_type'])
        return rv

    @classmethod
    def title(cls):
        return titleize(cls.name + '_policy')

    @classmethod
    def render_spec(cls):
        if cls.schema:
            schema_spec = schema([cls.schema])
        else:
            schema_spec = ""
        return {
            'title': cls.title(),
            'applies_to': cls.applies_to(),
            'can_assign_to': cls.can_assign_to(),
            'schema': schema_spec,
            'hints': cls.hints,
            'write_requires': cls.write_requires,
        }

    def __repr__(self):
        return f"<{self.title}>"
