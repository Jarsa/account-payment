# Copyright 2026 Jarsa (https://www.jarsa.com)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

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
