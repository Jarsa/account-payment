# Copyright 2026 Jarsa (https://www.jarsa.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from datetime import date

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    def _get_user_fiscal_lock_date(self):
        """Include the tax lock date in the effective lock date used to decide
        the cash basis / exchange difference move date.

        The standard ``_get_user_fiscal_lock_date`` only considers the fiscal
        year and period lock dates. The cash basis entry, however, also impacts
        the tax report and is therefore validated against ``max_tax_lock_date``.
        When the closing is done through the tax lock date, the standard cash
        basis fallback (date the entry on the reconciliation date) never
        triggers and posting is refused.

        We only extend the behaviour when the ``cash_basis_check_tax_lock``
        context key is set, so the regular accounting flow keeps Odoo's
        standard behaviour untouched.
        """
        lock_date = super()._get_user_fiscal_lock_date()
        if self.env.context.get("cash_basis_check_tax_lock"):
            lock_date = max(lock_date, self.max_tax_lock_date or date.min)
        return lock_date

    caba_payment_date_lock_policy = fields.Selection(
        [
            ("block", "Block the reconciliation"),
            ("next_open", "Use the first open date"),
            ("standard", "Keep the standard behavior"),
        ],
        default="block",
        required=True,
        string="Cash Basis Lock Policy",
        help="What to do when the payment date of a cash basis entry falls in a "
        "locked period:\n"
        "- Block the reconciliation: raise an error asking to reopen the period.\n"
        "- Use the first open date: date the entry on the first day after the lock.\n"
        "- Keep the standard behavior: let Odoo date the entry on the "
        "reconciliation date.",
    )
    caba_purchase_date_policy = fields.Selection(
        [
            ("payment", "Payment date"),
            ("latest", "Latest of payment and bill dates"),
        ],
        default="payment",
        required=True,
        string="Cash Basis Purchase Date",
        help="Date of the cash basis entry of vendor bills:\n"
        "- Payment date: always the date of the bank/cash entry.\n"
        "- Latest of payment and bill dates: use the bill date when the bill "
        "is dated after the payment (e.g. Mexican creditable VAT, which is "
        "only deductible once the CFDI exists).",
    )
