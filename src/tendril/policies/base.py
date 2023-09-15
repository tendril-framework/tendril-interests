

from inflection import titleize


class PolicyBase(object):
    name = 'default_content'

    @property
    def title(self):
        return titleize(self.name + '_policy')

    def __repr__(self):
        return f"<{self.title}>"
