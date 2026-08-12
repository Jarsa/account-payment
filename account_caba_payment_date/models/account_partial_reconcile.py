# Copyright 2024 Jarsa (https://www.jarsa.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import date as date_lib
from datetime import timedelta

from odoo import _, models
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
            if line.journal_id.type in ("bank", "cash"):
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

    def _create_tax_cash_basis_moves(self):
        """Create the cash basis entries honoring the lock dates and date them
        on the payment date according to the company policies.

        The ``cash_basis_check_tax_lock`` context key makes the effective lock
        date (see :meth:`res.company._get_user_fiscal_lock_date`) also account
        for the tax lock date. As a result, the standard fallback of
        ``_create_tax_cash_basis_moves`` dates the entry on the operation date
        (today) when the period of the most recent source document is closed,
        instead of refusing to post inside the locked period.

        The partials whose natural date falls in a locked period are recorded
        before creation (using the very same condition as the standard method)
        to post a traceability message on the resulting entries and their
        source documents.
        """
        expected_date_per_partial = {}
        for partial in self:
            lock_date = partial.company_id.with_context(
                cash_basis_check_tax_lock=True
            )._get_user_fiscal_lock_date()
            if partial.max_date and partial.max_date <= (lock_date or date_lib.min):
                expected_date_per_partial[partial.id] = partial.max_date

        moves = super(
            AccountPartialReconcile,
            self.with_context(cash_basis_check_tax_lock=True),
        )._create_tax_cash_basis_moves()

        for move in moves:
            partial = move.tax_cash_basis_rec_id
            if not partial:
                continue
            date = partial._caba_get_payment_date()
            # The tax lock date also applies: the cash basis entry affects the
            # tax report, so it cannot be dated inside a tax-locked period.
            lock_date = move.company_id.with_context(
                cash_basis_check_tax_lock=True
            )._get_user_fiscal_lock_date()
            if date <= lock_date:
                policy = move.company_id.caba_payment_date_lock_policy
                if policy == "standard":
                    continue
                if policy == "next_open":
                    date = lock_date + timedelta(days=1)
                else:  # block
                    raise UserError(
                        _(
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
            if date != move.date:
                month_changed = (date.year, date.month) != (
                    move.date.year,
                    move.date.month,
                )
                vals = {"date": date}
                if month_changed:
                    # Clear the name so the date-sequence constraint does not
                    # reject the write, then resequence for the new period.
                    vals["name"] = False
                move.write(vals)
                if month_changed:
                    move._compute_name()
        if expected_date_per_partial:
            moves._log_cash_basis_lock_shift(expected_date_per_partial)
        return moves
