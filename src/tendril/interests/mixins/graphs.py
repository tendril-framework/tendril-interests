

from tendril.core.topology.grafana.teams import ensure_graphs_team
from tendril.core.topology.grafana.folders import ensure_graphs_folder
from tendril.connectors.grafana.actions.dashboards import get_dashboard
from tendril.connectors.grafana.actions.dashboards import upsert_dashboard
from tendril.connectors.grafana.models.dashboard import generate_dashboard

from .base import InterestMixinBase
from tendril.config import GRAFANA_TEAM_COMPOSITION
from tendril.config import GRAFANA_BASE_URL

from tendril.utils import log
logger = log.get_logger(__name__)


class InterestGraphsMixin(InterestMixinBase):
    graphs_specs = []

    def _graphs_owner(self):
        candidate_types = [x[0] for x in GRAFANA_TEAM_COMPOSITION]
        if self.type_name in candidate_types:
            return self
        for candidate in self.ancestors():
            if candidate.type_name in candidate_types:
                return candidate

    async def _graphs_get(self, team_id, folder_uid):
        response = {}
        for spec_class in self.graphs_specs:
            spec = spec_class(actual=self)
            dashboard_uid = spec.uid

            logger.debug(f"Searching for dashboard {dashboard_uid}")
            dashboard_info = await get_dashboard(dashboard_uid)
            url = None

            if not dashboard_info:
                logger.info(f"Creating dashboard {dashboard_uid}")
                payload = await generate_dashboard(spec)
                payload.setdefault('uid', dashboard_uid)
                dashboard_info = await upsert_dashboard(
                    payload, team_id=team_id, folder_uid=folder_uid,
                    commit_msg="Generated from spec"
                )
                url = GRAFANA_BASE_URL + dashboard_info['url']
            else:
                url = f"{GRAFANA_BASE_URL}{dashboard_info['meta']['url']}"

            if not url:
                return {}

            params = {}
            for name, value in spec.variables_url.items():
                params[f'var-{name}']= value
            response[spec.name] = {'url': url, 'params': params}
        return response

    async def graphs(self):
        if not self.graphs_specs:
            return {}
        owner = self._graphs_owner()
        graphs_team_id = await ensure_graphs_team(interest_type=owner.type_name, interest_name=owner.name)
        folder_uid = await ensure_graphs_folder(interest_type=owner.type_name, interest_name=owner.name,
                                                descriptive_name=owner.descriptive_name)
        response = await self._graphs_get(graphs_team_id, folder_uid)
        return response
