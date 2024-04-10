

from tendril.core.topology.grafana.teams import ensure_graphs_team
from tendril.core.topology.grafana.folders import ensure_graphs_folder
from .base import InterestMixinBase
from tendril.config import GRAFANA_TEAM_COMPOSITION

from tendril.utils.db import with_db
from tendril.utils import log
logger = log.get_logger(__name__)


class InterestGraphsMixin(InterestMixinBase):
    def _graphs_owner(self):
        candidate_types = [x[0] for x in GRAFANA_TEAM_COMPOSITION]
        if self.type_name in candidate_types:
            return self
        for candidate in self.ancestors():
            if candidate.type_name in candidate_types:
                return candidate

    async def graphs(self):
        owner = self._graphs_owner()
        graphs_team_id = await ensure_graphs_team(interest_type=owner.type_name, interest_name=owner.name)
        folder_uid = await ensure_graphs_folder(interest_type=owner.type_name, interest_name=owner.name,
                                                descriptive_name=owner.descriptive_name)
        return {}
