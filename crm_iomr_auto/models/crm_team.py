################################################################################
#
#    Madooit IT Solutions.
#
#    Copyright (C) 2026-TODAY https://www.madooit.com>).
#    Author:  Rodrigo A. Madureira (rodrigo@madooit.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
################################################################################
from odoo import models


class CrmTeam(models.Model):
    _inherit = "crm.team"

    def _action_update_to_pipeline(self, action):
        """Load all stages of the user's sales team.

        The CRM kanban relies on the ``default_team_id`` context key to expand
        the stage columns (``crm.lead._read_group_stage_ids``).  The standard
        "My Pipeline" action does not provide it, so stages without
        opportunities are hidden.  Adding the current user's sales team keeps
        the empty stages visible without restricting the action domain.
        """
        action = super()._action_update_to_pipeline(action)
        user_team_id = self.env.user.sale_team_id.id
        if user_team_id and isinstance(action.get("context"), dict):
            action["context"].setdefault("default_team_id", user_team_id)
        return action
