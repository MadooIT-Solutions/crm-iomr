from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def write(self, vals):
        if "groups_id" in vals and isinstance(vals["groups_id"], list):
            doctor_group = self.env.ref(
                "crm_commissions.group_crm_commission_doctor", raise_if_not_found=False
            )
            if doctor_group:
                dg_id = doctor_group.id
                ig_id = self.env.ref("base.group_user").id
                pg_id = self.env.ref("base.group_portal").id

                for user in self:
                    old_ids = set(user.groups_id.ids)
                    new_ids = self._resolve_groups_commands(old_ids, vals["groups_id"])
                    doctor_added = dg_id in new_ids and dg_id not in old_ids
                    doctor_removed = dg_id not in new_ids and dg_id in old_ids

                    if doctor_added and ig_id in old_ids:
                        vals["groups_id"].append((3, ig_id))
                    elif doctor_removed and ig_id not in new_ids and pg_id in new_ids:
                        vals["groups_id"].append((3, pg_id))
                        vals["groups_id"].append((4, ig_id))

        return super().write(vals)

    @staticmethod
    def _resolve_groups_commands(current_ids, commands):
        ids = set(current_ids)
        for cmd in commands:
            if not isinstance(cmd, list | tuple):
                continue
            if cmd[0] == 4:
                ids.add(cmd[1])
            elif cmd[0] == 3:
                ids.discard(cmd[1])
            elif cmd[0] == 5:
                ids.clear()
            elif cmd[0] == 6:
                ids = set(cmd[2])
        return ids
