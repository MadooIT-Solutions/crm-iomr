# Copyright 2026 IOMR - Rodrigo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestCommissionMassSettle(TransactionCase):
    """Mass commission settlement wizard.

    The wizard is a TransientModel: its record can be removed (expiration /
    automatic cleaning, or a stale client reference) between opening the dialog
    and clicking the button. In that case the ORM raises ``MissingError`` when a
    stored field is read, which is cryptic for the user. ``action_settle`` must
    fail politely instead, and must not read the wizard fields after the settle
    loop starts.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env["res.partner"].create(
            {"name": "Mass Settle Agent", "agent": True}
        )

    def test_02_deleted_wizard_raises_user_error(self):
        """A removed wizard record gives a friendly UserError, not MissingError."""
        wizard = self.env["commission.mass.settle"].create(
            {"date_to": fields.Date.today(), "settlement_type": "all"}
        )
        wizard_id = wizard.id
        wizard.unlink()
        stale = self.env["commission.mass.settle"].browse(wizard_id)
        self.assertFalse(stale.exists())
        with self.assertRaises(UserError):
            stale.action_settle()

    def test_03_empty_period_returns_notification(self):
        """With no lines in the period, a notification is returned, no crash."""
        wizard = self.env["commission.mass.settle"].create(
            {
                "date_from": fields.Date.to_date("2000-01-01"),
                "date_to": fields.Date.to_date("2000-01-31"),
                "settlement_type": "all",
                "agent_ids": [(6, 0, self.agent.ids)],
            }
        )
        result = wizard.action_settle()
        self.assertEqual(result.get("type"), "ir.actions.client")
        self.assertEqual(result.get("tag"), "display_notification")
        # The wizard must still be usable after a settle run.
        self.assertTrue(wizard.exists())
