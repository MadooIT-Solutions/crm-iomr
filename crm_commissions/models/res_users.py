from lxml import etree

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    show_repasse_table = fields.Boolean(related='partner_id.show_repasse_table', readonly=False)
    show_all_values = fields.Boolean(related='partner_id.show_all_values', readonly=False)

    crm_role = fields.Selection(
        selection=[
            ("sdr", "SDR"),
            ("orientadora", "Orientadora"),
            ("coordenadora", "Coordenadora"),
            ("commission_user", "CRM Commission User"),
            ("manager", "Commission Manager"),
            ("doctor", "Doctor (Portal)"),
            ("readonly", "Visualização Total (CRM/Vendas)"),
            ("salesman", "Vendedor"),
            ("sale_manager", "Gerente de Vendas"),
        ],
        string="Função CRM",
        compute="_compute_crm_role",
        inverse="_inverse_crm_role",
    )

    @api.depends("groups_id")
    def _compute_crm_role(self):
        for user in self:
            if user.has_group("crm_commissions.group_crm_commission_manager"):
                user.crm_role = "manager"
            elif user.has_group("crm_commissions.group_crm_commission_orientadora"):
                user.crm_role = "orientadora"
            elif user.has_group("crm_commissions.group_crm_commission_sdr"):
                user.crm_role = "sdr"
            elif user.has_group("crm_commissions.group_crm_commission_user"):
                user.crm_role = "commission_user"
            elif user.has_group("crm_commissions.group_crm_commission_doctor"):
                user.crm_role = "doctor"
            elif user.has_group("crm_commissions.group_crm_readonly"):
                user.crm_role = "readonly"
            elif user.has_group("sales_team.group_sale_manager"):
                user.crm_role = "sale_manager"
            elif user.has_group("sales_team.group_sale_salesman"):
                user.crm_role = "salesman"
            else:
                user.crm_role = False

    def _inverse_crm_role(self):
        crm_groups_xml_ids = {
            "crm_commissions.group_crm_commission_user",
            "crm_commissions.group_crm_commission_manager",
            "crm_commissions.group_crm_commission_orientadora",
            "crm_commissions.group_crm_commission_sdr",
            "crm_commissions.group_crm_commission_doctor",
            "crm_commissions.group_crm_readonly",
            "crm_commissions.group_commission_manager",
            "crm_commissions.group_commission_coordinator",
            "sales_team.group_sale_salesman",
            "sales_team.group_sale_manager",
        }
        role_group_map = {
            "sdr": {"crm_commissions.group_crm_commission_sdr"},
            "orientadora": {
                "crm_commissions.group_crm_commission_orientadora",
            },
            "coordenadora": {"crm_commissions.group_commission_coordinator"},
            "commission_user": {"crm_commissions.group_crm_commission_user"},
            "manager": {
                "crm_commissions.group_crm_commission_manager",
                "crm_commissions.group_commission_manager",
            },
            "doctor": {"crm_commissions.group_crm_commission_doctor"},
            "readonly": {"crm_commissions.group_crm_readonly"},
            "salesman": {"sales_team.group_sale_salesman"},
            "sale_manager": {"sales_team.group_sale_manager"},
        }
        for user in self:
            if not user.crm_role:
                continue
            target_xml_ids = role_group_map.get(user.crm_role, set())
            current_group_ids = set(user.groups_id.ids)
            groups_to_remove = []
            groups_to_add = []
            for xml_id in target_xml_ids:
                group = self.env.ref(xml_id, raise_if_not_found=False)
                if group and group.id not in current_group_ids:
                    groups_to_add.append(group.id)
            for xml_id in crm_groups_xml_ids:
                if xml_id in target_xml_ids:
                    continue
                group = self.env.ref(xml_id, raise_if_not_found=False)
                if group and group.id in current_group_ids:
                    groups_to_remove.append(group.id)
            if groups_to_remove:
                user.write({"groups_id": [(3, gid) for gid in groups_to_remove]})
            if groups_to_add:
                user.write({"groups_id": [(4, gid) for gid in groups_to_add]})

    def write(self, vals):
        if "groups_id" in vals and isinstance(vals["groups_id"], list):
            doctor_group = self.env.ref(
                "crm_commissions.group_crm_commission_doctor", raise_if_not_found=False
            )
            if doctor_group:
                dg_id = doctor_group.id
                ig_id = self.env.ref("base.group_user").id
                pg_id = self.env.ref("base.group_portal").id

                commands = list(vals["groups_id"])
                for user in self:
                    old_ids = set(user.groups_id.ids)
                    new_ids = self._resolve_groups_commands(old_ids, commands)
                    doctor_added = dg_id in new_ids and dg_id not in old_ids
                    doctor_removed = dg_id not in new_ids and dg_id in old_ids

                    if doctor_added and ig_id in old_ids:
                        commands.append((3, ig_id))
                    elif doctor_removed and ig_id not in new_ids and pg_id in new_ids:
                        commands.append((3, pg_id))
                        commands.append((4, ig_id))

                vals["groups_id"] = commands

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


class ResGroups(models.Model):
    _inherit = "res.groups"

    @api.model
    def _update_user_groups_view(self):
        super()._update_user_groups_view()

        if self._context.get('install_filename') or self._context.get('_force_unlink'):
            return

        view = self.env.ref('base.user_groups_view', raise_if_not_found=False)
        if not (view and view._name == 'ir.ui.view'):
            return

        managed_xml_ids = {
            "crm_commissions.group_crm_commission_user",
            "crm_commissions.group_crm_commission_manager",
            "crm_commissions.group_crm_commission_orientadora",
            "crm_commissions.group_crm_commission_sdr",
            "crm_commissions.group_crm_commission_doctor",
            "crm_commissions.group_crm_readonly",
            "crm_commissions.group_commission_manager",
            "crm_commissions.group_commission_coordinator",
        }

        managed_group_ids = set()
        for xml_id in managed_xml_ids:
            group = self.env.ref(xml_id, raise_if_not_found=False)
            if group:
                managed_group_ids.add(group.id)

        if not managed_group_ids:
            return

        tree = etree.fromstring(view.arch)

        modified = False
        for field_elem in list(tree.iter('field')):
            name = field_elem.get('name', '')
            if name.startswith('in_group_'):
                try:
                    gid = int(name[9:])
                    if gid in managed_group_ids:
                        field_elem.getparent().remove(field_elem)
                        modified = True
                except ValueError:
                    pass
            elif name.startswith('sel_groups_'):
                try:
                    ids = [int(v) for v in name[11:].split('_')]
                    if any(gid in managed_group_ids for gid in ids):
                        field_elem.getparent().remove(field_elem)
                        modified = True
                except ValueError:
                    pass

        if modified:
            xml_content = etree.tostring(tree, pretty_print=True, encoding="unicode")
            if xml_content != view.arch:
                view.with_context(lang=None).write({'arch': xml_content})
