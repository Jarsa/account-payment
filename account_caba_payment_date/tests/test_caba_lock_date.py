# Copyright 2026 Jarsa (https://www.jarsa.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestCabaLockDate(AccountTestInvoicingCommon):
    """Payment of an invoice when the period of the payment is closed
    through the tax lock date.

    With the ``standard`` lock policy, the cash basis entry must be generated
    on the first day after the lock date instead of inside the tax-locked
    period. Since Odoo 20.0, reconciling two documents without payment (e.g.
    a credit note applied to an invoice) no longer generates cash basis
    entries."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
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
                "company_ids": [Command.set(company.ids)],
            }
        )
        company.account_cash_basis_base_account_id = cls.cash_basis_base_account

        cls.cash_basis_transfer_account = cls.env["account.account"].create(
            {
                "code": "cb.transfer.account",
                "name": "cash_basis_transfer_account",
                "account_type": "income",
                "reconcile": True,
                "company_ids": [Command.set(company.ids)],
            }
        )
        cls.tax_account = cls.env["account.account"].create(
            {
                "code": "cb.tax.account",
                "name": "cash_basis_tax_account",
                "account_type": "income",
                "company_ids": [Command.set(company.ids)],
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
        cls.payment_date = cls.today - relativedelta(days=20)
        # Lock date between the payment and today: the period of the invoice
        # and the payment is closed, but today is still postable.
        cls.lock_date = cls.today - relativedelta(days=5)

        cls.invoice = cls.init_invoice(
            "out_invoice",
            invoice_date=cls.invoice_date,
            amounts=[1000.0],
            taxes=cls.cash_basis_tax,
            post=True,
        )

    def _get_cash_basis_moves(self):
        return self.env["account.move"].search(
            [("tax_cash_basis_origin_move_id", "=", self.invoice.id)]
        )

    def _register_payment(self):
        return (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=self.invoice.ids)
            .create({"payment_date": self.payment_date})
            ._create_payments()
        )

    def test_cash_basis_date_shifted_when_period_closed(self):
        """The cash basis entry is generated on the first day after the lock
        date when the tax period of the payment is closed."""
        self.company_data["company"].tax_lock_date = self.lock_date

        self._register_payment()

        cash_basis_moves = self._get_cash_basis_moves()
        self.assertTrue(cash_basis_moves, "No cash basis entry was generated")
        for move in cash_basis_moves:
            self.assertEqual(
                move.date,
                self.lock_date + relativedelta(days=1),
                "The cash basis entry should use the first open date",
            )

    def test_cash_basis_date_standard_when_period_open(self):
        """Without a lock date, the cash basis entry is dated on the payment
        date."""
        self._register_payment()

        cash_basis_moves = self._get_cash_basis_moves()
        self.assertTrue(cash_basis_moves, "No cash basis entry was generated")
        for move in cash_basis_moves:
            self.assertEqual(
                move.date,
                self.payment_date,
                "Without a lock date the payment date must be kept",
            )

    def test_chatter_traceability_messages(self):
        """A traceability message is posted on the source documents and on the
        cash basis entry when the date is shifted."""
        self.company_data["company"].tax_lock_date = self.lock_date

        invoice_messages_before = len(self.invoice.message_ids)
        self._register_payment()

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
