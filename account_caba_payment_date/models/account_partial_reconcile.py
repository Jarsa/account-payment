# Copyright 2024 Jarsa (https://www.jarsa.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import timedelta

from odoo import models
from odoo.exceptions import UserError


class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"

    def _caba_get_payment_date(self):
        """Return the date of the cash basis entry of the reconciliation: the
        date of the bank/cash journal entry when there is one, the newest date
        otherwise. For vendor bills, the company can choose to use the bill
        date when it is after the payment (creditable VAT needs the CFDI)."""
        self.ensure_one()
        payment_date = False
        other_line = self.env["account.move.line"]
        for line in (self.debit_move_id, self.credit_move_id):
            if line.journal_id.type in ("bank", "cash", "credit"):
                payment_date = line.date
            else:
                other_line = line
        if not payment_date:
            return self.max_date
        if (
            other_line.move_id.is_purchase_document(include_receipts=True)
            and other_line.company_id.caba_purchase_date_policy == "latest"
        ):
            return max(payment_date, other_line.date)
        return payment_date

    def _caba_get_lock_date(self):
        """Return the lock date of the cash basis entry of the reconciliation,
        tax lock date included (see :meth:`res.company._get_user_fiscal_lock_date`).
        """
        self.ensure_one()
        return self.company_id.with_context(
            cash_basis_check_tax_lock=True
        )._get_user_fiscal_lock_date(self.company_id.tax_cash_basis_journal_id)

    def _caba_get_policy_date(self):
        """Return the date of the cash basis entry according to the company
        policies, or ``None`` to keep the standard date."""
        self.ensure_one()
        date = self._caba_get_payment_date()
        # The tax lock date also applies: the cash basis entry affects the
        # tax report, so it cannot be dated inside a tax-locked period.
        lock_date = self._caba_get_lock_date()
        if date > lock_date:
            return date
        policy = self.company_id.caba_payment_date_lock_policy
        if policy == "standard":
            return None
        if policy == "next_open":
            return lock_date + timedelta(days=1)
        # block
        raise UserError(
            self.env._(
                "The cash basis entry of this reconciliation must be "
                "dated on the payment date %(date)s, but that period "
                "is locked "
                "(lock date: %(lock_date)s).\n"
                "Reopen the period, or change the cash basis lock policy "
                "in the accounting settings.",
                date=date,
                lock_date=lock_date,
            )
        )

    def _collect_tax_cash_basis_values(self):
        """Replace the date of the cash basis entries by the one given by the
        company policies.

        Odoo does not allow to change the date of a posted entry, so the date
        is set here, before ``_create_tax_cash_basis_moves`` creates the
        entries. The standard method then still dates them on the first day
        after the lock date when that date is locked.
        """
        values_per_move = super()._collect_tax_cash_basis_values()
        if not self.env.context.get("cash_basis_check_tax_lock"):
            return values_per_move
        date_per_partial = {}
        for move_values in values_per_move.values():
            for partial_values in move_values.get("partials", []):
                partial = partial_values["partial"]
                if partial.id not in date_per_partial:
                    date_per_partial[partial.id] = partial._caba_get_policy_date()
                if date_per_partial[partial.id]:
                    partial_values["payment_date"] = date_per_partial[partial.id]
        return values_per_move

    def _create_tax_cash_basis_moves(self):
        """Create the cash basis entries honoring the lock dates and date them
        on the payment date according to the company policies.

        The ``cash_basis_check_tax_lock`` context key makes the effective lock
        date (see :meth:`res.company._get_user_fiscal_lock_date`) also account
        for the tax lock date. As a result, the standard fallback of
        ``_create_tax_cash_basis_moves`` dates the entry on the first day after
        the lock date when the payment date is in a closed period, instead of
        dating it inside the tax-locked period. The context key also enables
        the policy date in ``_collect_tax_cash_basis_values``.

        The partials whose expected date falls in a locked period are recorded
        before creation to post a traceability message on the resulting
        entries and their source documents.
        """
        expected_date_per_partial = {}
        for partial in self:
            expected_date = partial._caba_get_payment_date()
            if expected_date and expected_date <= partial._caba_get_lock_date():
                expected_date_per_partial[partial.id] = expected_date

        moves = super(
            AccountPartialReconcile,
            self.with_context(cash_basis_check_tax_lock=True),
        )._create_tax_cash_basis_moves()

        if expected_date_per_partial:
            moves._log_cash_basis_lock_shift(expected_date_per_partial)
        return moves
