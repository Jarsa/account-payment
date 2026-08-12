# Copyright 2026 Jarsa (https://www.jarsa.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestCabaLockDate(AccountTestInvoicingCommon):
    """Document-vs-document reconciliation (e.g. credit note applied to an
    invoice) when the period of the source documents is closed.

    These flows have no bank/cash entry, so the payment-date rewrite keeps the
    standard date. With the ``standard`` lock policy, the cash basis entry must
    be generated on the operation date (today) instead of being refused."""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        company = cls.company_data["company"]
        # Enable cash basis at company level, otherwise no cash basis entry is
        # generated on reconciliation (see account_move_line.is_cash_basis_needed).
        company.tax_exigibility = True
        company.caba_payment_date_lock_policy = "standard"

        cls.cash_basis_base_account = cls.env["account.account"].create(
            {
                "code": "cb.base.account",
                "name": "cash_basis_base_account",
                "account_type": "income",
                "company_id": company.id,
            }
        )
        company.account_cash_basis_base_account_id = cls.cash_basis_base_account

        cls.cash_basis_transfer_account = cls.env["account.account"].create(
            {
                "code": "cb.transfer.account",
                "name": "cash_basis_transfer_account",
                "account_type": "income",
                "reconcile": True,
                "company_id": company.id,
            }
        )
        cls.tax_account = cls.env["account.account"].create(
            {
                "code": "cb.tax.account",
                "name": "cash_basis_tax_account",
                "account_type": "income",
                "company_id": company.id,
            }
        )
        company.tax_cash_basis_journal_id = cls.company_data["default_journal_misc"]

        cls.cash_basis_tax = cls.env["account.tax"].create(
            {
                "name": "cash_basis_16",
                "amount": 16.0,
                "amount_type": "percent",
                "company_id": company.id,
                "tax_exigibility": "on_payment",
                "cash_basis_transition_account_id": cls.cash_basis_transfer_account.id,
                "invoice_repartition_line_ids": [
                    (0, 0, {"repartition_type": "base"}),
                    (
                        0,
                        0,
                        {
                            "repartition_type": "tax",
                            "account_id": cls.tax_account.id,
                        },
                    ),
                ],
                "refund_repartition_line_ids": [
                    (0, 0, {"repartition_type": "base"}),
                    (
                        0,
                        0,
                        {
                            "repartition_type": "tax",
                            "account_id": cls.tax_account.id,
                        },
                    ),
                ],
            }
        )

        # Dates relative to "today" so the test is independent from the run date.
        cls.today = fields.Date.context_today(cls.env.user)
        cls.invoice_date = cls.today - relativedelta(days=40)
        cls.refund_date = cls.today - relativedelta(days=20)
        # Lock date between the most recent document and today: the period of
        # both documents is closed, but today is still postable.
        cls.lock_date = cls.today - relativedelta(days=5)

        cls.invoice = cls.init_invoice(
            "out_invoice",
            invoice_date=cls.invoice_date,
            amounts=[1000.0],
            taxes=cls.cash_basis_tax,
            post=True,
        )
        cls.refund = cls.init_invoice(
            "out_refund",
            invoice_date=cls.refund_date,
            amounts=[1000.0],
            taxes=cls.cash_basis_tax,
            post=True,
        )

    def _get_cash_basis_moves(self):
        return self.env["account.move"].search(
            [
                (
                    "tax_cash_basis_origin_move_id",
                    "in",
                    (self.invoice + self.refund).ids,
                )
            ]
        )

    def _reconcile_receivables(self):
        lines = (self.invoice + self.refund).line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )
        lines.reconcile()

    def test_cash_basis_date_shifted_when_period_closed(self):
        """The cash basis entry is generated on the operation date (today) when
        the tax period of the source documents is closed."""
        self.company_data["company"].tax_lock_date = self.lock_date

        self._reconcile_receivables()

        cash_basis_moves = self._get_cash_basis_moves()
        self.assertTrue(cash_basis_moves, "No cash basis entry was generated")
        for move in cash_basis_moves:
            self.assertEqual(
                move.date,
                self.today,
                "The cash basis entry should use the operation date (today)",
            )

    def test_cash_basis_date_standard_when_period_open(self):
        """Without a lock date, Odoo's standard behaviour is preserved: the
        cash basis entry keeps the date of the most recent document."""
        self._reconcile_receivables()

        cash_basis_moves = self._get_cash_basis_moves()
        self.assertTrue(cash_basis_moves, "No cash basis entry was generated")
        for move in cash_basis_moves:
            self.assertNotEqual(
                move.date,
                self.today,
                "Without a lock date the standard document date must be kept",
            )

    def test_chatter_traceability_messages(self):
        """A traceability message is posted on the source documents and on the
        cash basis entry when the date is shifted."""
        self.company_data["company"].tax_lock_date = self.lock_date

        invoice_messages_before = len(self.invoice.message_ids)
        self._reconcile_receivables()

        cash_basis_moves = self._get_cash_basis_moves()
        self.assertTrue(cash_basis_moves)

        self.assertGreater(
            len(self.invoice.message_ids),
            invoice_messages_before,
            "A traceability message should be posted on the invoice",
        )
        for move in cash_basis_moves:
            bodies = move.message_ids.mapped("body")
            self.assertTrue(
                any("Expected date" in (body or "") for body in bodies),
                "The cash basis entry should carry the traceability message",
            )
