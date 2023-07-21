

import polars
from typing import Any
from typing import List
from typing import NamedTuple
from pydantic import create_model_from_namedtuple
from tendril.common.states import LifecycleStatus
from tendril.utils.pydantic import TendrilTBaseModel


class ApprovalRequirement(NamedTuple):
    name: str
    role: str
    spread: int  # -1 : All, 0: No Minimum
    states: List[LifecycleStatus]
    context_type: str


ApprovalRequirementTModel = create_model_from_namedtuple(ApprovalRequirement)


class ApprovalTModel(TendrilTBaseModel):
    user: str
    timestamp: Any

class ApprovalContextStatusTModel(TendrilTBaseModel):
    name: str
    context: int
    approvals: List[ApprovalTModel]
    rejections: List[ApprovalTModel]


class InterestApprovalStatusTModel(TendrilTBaseModel):
    subject: int
    contexts: List[ApprovalContextStatusTModel]


class ApprovalCollector(object):
    def __init__(self):
        self._raw_data = []
        self.df = None

    def add_approval(self, approval):
        # TODO Dedup?
        self._raw_data.append({
            'subject': approval.interest_id,
            'context': approval.context_id,
            'approval': approval.approval_type.name,
            'approved': approval.approved,
            'user': approval.user.puid,
            'timestamp': (approval.updated_at or approval.created_at).for_json()
        })

    def add_approvals(self, approvals):
        for approval in approvals:
            self.add_approval(approval)

    def process(self):
        self.df = polars.DataFrame(self._raw_data)

    def apply_approval_filter(self, include_approvals):
        # TODO This will mess with caching!
        self.df = self.df.filter(polars.col('approval').is_in(include_approvals))

    def subjects(self):
        if not self.df.select(polars.count()).item():
            return []
        return list(self.df.select(polars.col('subject').unique()).get_column(name='subject'))

    def contexts(self, subject=None):
        if not subject:
            df = self.df
        else:
            df = self.df.filter(polars.col("subject") == subject)
        if not df.select(polars.count()).item():
            return []
        return list(df.select(['context', 'approval']).unique().rows())

    def approvals(self, subject, context, name, approved=True):
        if not self.df.select(polars.count()).item():
            return []
        df = self.df.filter((polars.col("subject") == subject) &
                            (polars.col("context") == context) &
                            (polars.col("approval") == name) &
                            (polars.col("approved") == approved))
        if not df.select(polars.count()).item():
            return []
        return df.select(['user', 'timestamp']).to_dicts()

    def render_subject_perspective(self):
        rv = []
        for subject in self.subjects():
            subject_rv = {'subject': subject, 'contexts': []}
            for context, approval_name in self.contexts(subject=subject):
                context_rv = {'name': approval_name,
                              'context': context,
                              'approvals': self.approvals(subject, context, approval_name),
                              'rejections': self.approvals(subject, context, approval_name, approved=False)}
                subject_rv['contexts'].append(context_rv)
            rv.append(subject_rv)
        return rv

    def render_context_perspective(self):
        return self.render_subject_perspective()

    def render_user_perspective(self):
        return {}
